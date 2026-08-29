"""Human hand-off: summarise, ping Slack, publish over the event stream."""
import httpx

from ..models import AgentSecrets


def summarise(state: dict, reason: str) -> str:
    bant = ", ".join(f"{k}={v}" for k, v in state["bant"].items())
    objections = ", ".join(state["objections_raised"]) or "none"
    competitors = ", ".join(state["competitor_mentions"]) or "none"
    return (f"{state.get('company') or 'Unknown company'} · "
            f"{state.get('seat_count') or '?'} seats · {state['qualification']} ({bant})\n"
            f"Use case: {state.get('use_case') or '-'}\n"
            f"Objections: {objections} · Competitors: {competitors}\n"
            f"Reason for escalation: {reason}")


def escalate_to_human(secrets: AgentSecrets, reason: str, state: dict, channel: str = "") -> dict:
    summary = summarise(state, reason)
    if secrets.slack_webhook_url:
        try:
            httpx.post(secrets.slack_webhook_url, timeout=3,
                       json={"text": f"*Escalation on {channel}*\n{summary}"})
        except httpx.HTTPError as exc:
            print(f"[escalation] slack failed: {exc}")  # degrade to a log, never break the call
    else:
        print(f"[escalation] {channel}\n{summary}")
    return {"summary": summary, "channel": channel,
            "rep_eta": "A rep is joining this call in under a minute."}
