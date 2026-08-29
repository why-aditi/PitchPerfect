"""Human hand-off: summarise, ping Slack, publish over RTM."""
import os

import httpx

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")


def summarise(state: dict, reason: str) -> str:
    bant = ", ".join(f"{k}={v}" for k, v in state["bant"].items())
    return (f"{state.get('company') or 'Unknown company'} · {state.get('seat_count') or '?'} seats · "
            f"{state['qualification']} ({bant})\n"
            f"Use case: {state.get('use_case') or '—'}\n"
            f"Objections: {', '.join(state['objections_raised']) or 'none'} · "
            f"Competitors: {', '.join(state['competitor_mentions']) or 'none'}\n"
            f"Reason for escalation: {reason}")


def escalate_to_human(reason: str, state: dict, channel: str = "") -> dict:
    summary = summarise(state, reason)
    if SLACK_WEBHOOK_URL:
        try:
            httpx.post(SLACK_WEBHOOK_URL, json={"text": f"*Escalation on {channel}*\n{summary}"}, timeout=3)
        except httpx.HTTPError as exc:
            print(f"[escalation] slack failed: {exc}")  # degrade to a logged outcome, never break the call
    else:
        print(f"[escalation] {channel}\n{summary}")
    return {"summary": summary, "channel": channel, "rep_eta": "A rep is joining this call in under a minute."}
