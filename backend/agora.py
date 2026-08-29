"""Agora: token generation + Conversational AI Engine lifecycle (PRD 12)."""
import base64
import os

import httpx

APP_ID = os.getenv("AGORA_APP_ID", "")
APP_CERTIFICATE = os.getenv("AGORA_APP_CERTIFICATE", "")
CUSTOMER_ID = os.getenv("AGORA_CUSTOMER_ID", "")
CUSTOMER_SECRET = os.getenv("AGORA_CUSTOMER_SECRET", "")
BASE = f"https://api.agora.io/api/conversational-ai-agent/v2/projects/{APP_ID}"


def _auth() -> dict:
    raw = base64.b64encode(f"{CUSTOMER_ID}:{CUSTOMER_SECRET}".encode()).decode()
    return {"Authorization": f"Basic {raw}", "Content-Type": "application/json"}


def build_token(channel: str, uid: int, expire_s: int = 3600) -> str:
    """RTC + RTM privileges in one token — an RTC-only token breaks enable_rtm (PRD 6.1)."""
    raise NotImplementedError("agora-token-builder: RtcTokenBuilder with RTM privilege")


def start_payload(session_id: str, channel: str, token: str, llm_url: str,
                  agent_uid: str = "1001", prospect_uid: str = "1002") -> dict:
    return {
        "name": f"pitchpilot-{session_id}",
        "properties": {
            "channel": channel,
            "token": token,
            "agent_rtc_uid": agent_uid,
            "remote_rtc_uids": [prospect_uid],
            "enable_string_uid": False,
            "idle_timeout": 60,
            "advanced_features": {"enable_rtm": True},
            "asr": {"vendor": "ares", "language": "en-US", "params": {}},
            "tts": {"vendor": "", "params": {}},
            "llm": {
                "vendor": "custom",
                "url": llm_url,
                "api_key": os.getenv("LLM_PROXY_SECRET", ""),
                "style": "openai",
                "system_messages": [],
                "max_history": 32,
                "greeting_message": "Hi, you're speaking with an AI sales assistant. This call is transcribed. What can I help you with?",
                "failure_message": "Give me one moment.",
                "params": {"model": "llama-3.3-70b-versatile", "stream": True},
            },
            "turn_detection": {
                "mode": "default",
                "config": {
                    "speech_threshold": 0.5,
                    "start_of_speech": {"mode": "vad", "vad_config": {
                        "interrupt_duration_ms": 160,
                        "speaking_interrupt_duration_ms": 320,
                        "prefix_padding_ms": 800}},
                    "end_of_speech": {"mode": "semantic", "semantic_config": {
                        "silence_duration_ms": 320, "max_wait_ms": 3000, "pause_state_enabled": True}},
                },
            },
            # Since v2.6 all interruption behaviour lives here, not in turn_detection.
            "interruption": {"enable": True, "mode": "start_of_speech"},
            "filler_words": {
                "enable": True,
                "trigger": {"mode": "fixed_time", "fixed_time_config": {"response_wait_ms": 1500}},
                "content": {"mode": "static", "static_config": {
                    "phrases": ["One moment.", "Let me check that.", "Pulling that up."],
                    "selection_rule": "shuffle"}},
            },
            "parameters": {
                "data_channel": "rtm",
                "enable_metrics": True,
                "enable_error_message": True,
                "audio_scenario": "aiserver",
                "farewell_config": {"graceful_enabled": True, "graceful_timeout_seconds": 20},
            },
        },
    }


async def join(payload: dict) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(f"{BASE}/join", json=payload, headers=_auth())
        r.raise_for_status()
        return r.json()


async def leave(agent_id: str) -> None:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(f"{BASE}/agents/{agent_id}/leave", headers=_auth())
        r.raise_for_status()


async def speak(agent_id: str, text: str, interrupt: bool = True) -> None:
    """Say a fixed line over TTS — used for the escalation hand-off line."""
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(f"{BASE}/agents/{agent_id}/speak",
                              json={"text": text, "interrupt": interrupt}, headers=_auth())
        r.raise_for_status()
