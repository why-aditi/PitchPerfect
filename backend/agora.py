"""Agora: token generation + Conversational AI Engine lifecycle (PRD 12).

The operator never sees this payload and never opens the Agora dashboard. Fields marked
[cfg] in the PRD come from the agent record; the rest are fixed.
"""
import base64
import os

import httpx

from . import token2
from .models import AgentConfig

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
    return token2.build(APP_ID, APP_CERTIFICATE, channel, uid, expire_s)


def start_payload(config: AgentConfig, session_id: str, channel: str, token: str, llm_url: str,
                  agent_uid: str = "1001", prospect_uid: str = "1002") -> dict:
    voice = config.voice
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
            # credential_mode sits directly under tts, not inside params. Under "managed"
            # Agora supplies the vendor credentials and api_key is not needed, which is how
            # an operator gets a voice without signing up to a TTS vendor (PRD 19 q1).
            "tts": {"vendor": voice.tts_vendor,
                    "credential_mode": voice.tts_credential_mode,
                    "params": voice.tts_params},
            "llm": {
                "vendor": "custom",
                "url": llm_url,
                "api_key": os.getenv("LLM_PROXY_SECRET", ""),
                "style": "openai",
                "system_messages": [],          # the proxy owns the prompt
# Every one of these is resent on every request, and the whole payload counts
                # against the LLM's tokens-per-minute. 32 turns put a real call over Groq's
                # free-tier 8000 TPM about four turns in; the proxy collapses anything older
                # than its own keep_turns anyway, so the tail was being paid for twice.
                "max_history": 12,
                "greeting_message": config.persona.greeting,
                "failure_message": "Give me one moment.",
                "params": {"model": config.llm_model, "stream": True},
            },
            "turn_detection": {
                "mode": "default",
                "config": {
                    "speech_threshold": voice.speech_threshold,
                    "start_of_speech": {"mode": "vad", "vad_config": {
                        "interrupt_duration_ms": voice.interrupt_duration_ms,
                        "speaking_interrupt_duration_ms": voice.speaking_interrupt_duration_ms,
                        "prefix_padding_ms": voice.prefix_padding_ms}},
                    "end_of_speech": {"mode": "semantic", "semantic_config": {
                        "silence_duration_ms": voice.silence_duration_ms,
                        "max_wait_ms": voice.max_wait_ms,
                        "pause_state_enabled": True}},
                },
            },
            # Since v2.6 all interruption behaviour lives here, not in turn_detection.
            "interruption": {"enable": voice.interruption_enabled, "mode": "start_of_speech"},
            "filler_words": {
                "enable": bool(voice.filler_phrases),
                # A tool hop is two LLM round trips, so 1500ms landed after the answer often
                # enough to be useless. 1000 covers the gap the prospect actually hears.
                "trigger": {"mode": "fixed_time", "fixed_time_config": {"response_wait_ms": 1000}},
                "content": {"mode": "static", "static_config": {
                    "phrases": voice.filler_phrases, "selection_rule": "shuffle"}},
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
        if r.is_error:
            # The engine names the offending field in the body and nowhere else, so a bare
            # status code turns a one-line fix into an afternoon of guessing.
            raise RuntimeError(f"Agora join failed {r.status_code}: {r.text[:500]}")
        return r.json()


async def leave(agent_id: str) -> None:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(f"{BASE}/agents/{agent_id}/leave", headers=_auth())
        if r.status_code == 404:
            return  # already ended or never started; hanging up twice is not an error
        if r.is_error:
            raise RuntimeError(f"Agora leave failed {r.status_code}: {r.text[:300]}")


async def speak(agent_id: str, text: str, interrupt: bool = True) -> None:
    """Say a fixed line over TTS — used for the escalation hand-off line."""
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(f"{BASE}/agents/{agent_id}/speak",
                              json={"text": text, "interrupt": interrupt}, headers=_auth())
        if r.is_error:
            raise RuntimeError(f"Agora speak failed {r.status_code}: {r.text[:300]}")
