"""Lead capture beside the reply, not in front of it.

Until 2026-09-03 the prompt told the speaking model to call update_lead_state "before you
reply, every time", which made every turn two LLM round trips (~1s each on Mistral) before
the first word of the answer existed. The prospect sat through the filler phrase on turns
that needed no tool at all.

Now the speaking model is not offered update_lead_state. After each turn a second, smaller
model reads the newest transcript and the current state and is forced to call the tool
with whatever is new. It runs as a background task while TTS is already playing, so the
lead panel and the CRM stay current at the cost of lagging the conversation by one turn
rather than delaying it by one round trip.

One extractor per session, coalesced: a turn that lands while a run is in flight marks the
session dirty and the run goes again with the newest history once it finishes. A run that
fails is logged and forgotten — this path must never touch the spoken side.
"""
import asyncio
import json
import logging

from . import agents, playbook, state, tools

log = logging.getLogger("pitchpilot.extract")

INSTRUCTIONS = """You maintain the CRM record for a live sales call. You are given the lead
state recorded so far and the latest turns of the transcript. Call update_lead_state with
only what is NEW or CHANGED in these turns: name, company, email, industry, use case, seat
count, budget signal, timeline, objections, competitors named, BANT scores (0-3 each),
notes. Leave out anything already recorded and unchanged. Never invent a value; if the
prospect did not say it, leave it out. An email is only an email if the prospect said
one. bant.authority is your judgement of whether this person can decide."""

TURNS = 6            # the newest turns are enough: earlier ones were extracted already
_running: dict[str, asyncio.Task] = {}
_latest: dict[str, list[dict]] = {}   # the newest history a run has been asked for
_dirty: set[str] = set()      # newer history landed mid-run; go again when it finishes
_deferred: set[str] = set()   # history nobody has extracted and nothing is going to


def schedule(sid: str, history: list[dict], defer: bool = False) -> None:
    """Fire-and-forget from the turn. Safe with no running loop (sync tests).

    defer records the history without starting a run. A tool-using turn already spent two
    or three LLM requests out of the same 8000 TPM bucket the extractor draws on, and a
    live call died on exactly that: four 429s in 82 seconds, two of them silencing a reply.
    The facts are not lost — TURNS covers the newest six turns either way, so the next
    plain turn extracts them, and drain() starts a run if the call ends first.
    """
    _latest[sid] = history
    if defer:
        # Not _dirty: that flag means "re-run when the current run finishes", so setting
        # it here would wake a run in flight and spend the request we just declined to
        # spend. _deferred only tells drain() there is history nothing has read.
        _deferred.add(sid)
        return
    _deferred.discard(sid)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    task = _running.get(sid)
    if task is not None and not task.done():
        _dirty.add(sid)      # the run in flight will go again with _latest[sid]
        return
    _running[sid] = loop.create_task(_worker(sid))


async def _worker(sid: str) -> None:
    while True:
        history = _latest.get(sid)
        if history is None:
            return
        _dirty.discard(sid)
        _deferred.discard(sid)
        await run(sid, history)
        if sid not in _dirty:
            return


async def drain(sid: str, timeout_s: float = 3.0) -> None:
    """Wait for the session's extractor to finish — the last turn's facts have to reach
    the CRM sync that /stop-call does. Bounded: a hung provider must not hang the hangup."""
    task = _running.get(sid)
    if task is None or task.done():
        # Deferred turns leave history with no run behind it. The hangup is the last
        # chance those facts have to reach the CRM sync, so start one rather than
        # waiting on a task that was never created.
        if sid in _deferred and _latest.get(sid) is not None:
            try:
                task = _running[sid] = asyncio.get_running_loop().create_task(_worker(sid))
            except RuntimeError:
                task = None
    try:
        if task is not None and not task.done():
            # The worker re-runs while the session is dirty, so waiting on it covers
            # every turn scheduled so far, not only the one in flight.
            await asyncio.wait_for(asyncio.shield(task), timeout_s)
    except (asyncio.TimeoutError, Exception):  # noqa: BLE001
        pass
    finally:
        _running.pop(sid, None)
        _latest.pop(sid, None)
        _dirty.discard(sid)
        _deferred.discard(sid)


async def run(sid: str, history: list[dict]) -> None:
    """One extraction round trip. Never raises."""
    from . import proxy   # local import: proxy imports this module

    bound = agents.for_session(sid)
    if bound is None:
        return
    _, config, _ = bound
    recent = [m for m in history if m.get("role") in ("user", "assistant")][-TURNS:]
    if not any(m.get("role") == "user" for m in recent):
        return
    transcript = "\n".join(f"{m['role']}: {m.get('content') or ''}" for m in recent)
    messages = [
        {"role": "system", "content": INSTRUCTIONS},
        {"role": "user", "content": f"Lead state so far: {playbook.compact_state(state.get(sid))}\n\n"
                                    f"Latest turns:\n{transcript}"},
    ]
    try:
        reply = await proxy.complete(
            config, messages, [tools.LEAD_STATE_SPEC], resamples=0,
            model=config.extract_model,
            tool_choice={"type": "function", "function": {"name": "update_lead_state"}})
    except Exception as exc:  # noqa: BLE001 — capture is best-effort by design
        log.warning("%s extraction failed: %r", sid, exc)
        return
    for call in reply.get("tool_calls") or []:
        if call["function"]["name"] != "update_lead_state":
            continue
        try:
            args = json.loads(call["function"].get("arguments") or "{}")
        except json.JSONDecodeError:
            continue
        args = {k: v for k, v in args.items() if v not in (None, "", [], {})}
        if args:
            # run_tool is synchronous down to httpx, and the CRM write hangs off this
            # tool: HubSpot, then Notion, which spends two more requests resolving a
            # database the first time it sees one. On the loop that is up to 24 s of
            # stalled audio for every session on this process, after every turn. The
            # turn loop already offloads run_tool the same way (proxy.run_turn).
            await asyncio.to_thread(proxy.run_tool, sid, "update_lead_state", args, history)
