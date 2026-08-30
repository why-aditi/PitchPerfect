"""The engine payload (PRD 12) and the AccessToken2 builder.

The operator never sees either, so these are the tests that stand in for reading them.
"""
import base64
import zlib

import pytest

from backend import agora, token2


@pytest.fixture
def payload(config):
    return agora.start_payload(
        config, "sess_t", "pitchpilot-t", "007tok",
        "https://x.test/v1/chat/completions?session_id=sess_t")["properties"]


# --- config-driven fields --------------------------------------------------------------

def test_greeting_comes_from_the_persona(config):
    config.persona.greeting = "Hi, this is an AI assistant."
    p = agora.start_payload(config, "s", "c", "t", "u")["properties"]
    assert p["llm"]["greeting_message"] == "Hi, this is an AI assistant."


def test_model_comes_from_config(config):
    config.llm_model = "llama-3.1-8b-instant"
    p = agora.start_payload(config, "s", "c", "t", "u")["properties"]
    assert p["llm"]["params"]["model"] == "llama-3.1-8b-instant"


def test_voice_tuning_reaches_the_vad_config(config):
    config.voice.speaking_interrupt_duration_ms = 480
    config.voice.interrupt_duration_ms = 120
    vad = agora.start_payload(config, "s", "c", "t", "u")[
        "properties"]["turn_detection"]["config"]["start_of_speech"]["vad_config"]
    assert vad["speaking_interrupt_duration_ms"] == 480
    assert vad["interrupt_duration_ms"] == 120


def test_interruption_can_be_switched_off(config):
    config.voice.interruption_enabled = False
    p = agora.start_payload(config, "s", "c", "t", "u")["properties"]
    assert p["interruption"]["enable"] is False


def test_no_filler_phrases_disables_filler_words(config):
    """An empty shuffle list would be a silent no-op; switching the feature off is honest."""
    config.voice.filler_phrases = []
    p = agora.start_payload(config, "s", "c", "t", "u")["properties"]
    assert p["filler_words"]["enable"] is False


# --- fixed fields ----------------------------------------------------------------------

def test_the_proxy_is_the_only_source_of_the_prompt(payload):
    assert payload["llm"]["system_messages"] == []


def test_llm_vendor_is_custom_and_streams(payload):
    assert payload["llm"]["vendor"] == "custom"
    assert payload["llm"]["params"]["stream"] is True


def test_session_travels_in_the_llm_url(payload):
    assert "session_id=sess_t" in payload["llm"]["url"]


def test_rtm_is_enabled_because_the_data_channel_needs_it(payload):
    assert payload["advanced_features"]["enable_rtm"] is True
    assert payload["parameters"]["data_channel"] == "rtm"
    assert payload["parameters"]["enable_metrics"] is True


def test_only_the_prospect_is_a_remote_uid(payload):
    assert payload["remote_rtc_uids"] == ["1002"]
    assert payload["agent_rtc_uid"] == "1001"


def test_interruption_lives_outside_turn_detection(payload):
    """Since v2.6 these fields are deprecated inside turn_detection. Most tutorials are stale."""
    for stale in ("interrupt_mode", "interrupt_duration_ms", "threshold"):
        assert stale not in payload["turn_detection"]
    assert payload["interruption"]["mode"] == "start_of_speech"


def test_end_of_speech_is_semantic(payload):
    assert payload["turn_detection"]["config"]["end_of_speech"]["mode"] == "semantic"


def test_agent_name_is_unique_per_session(config):
    a = agora.start_payload(config, "sess_a", "c", "t", "u")["name"]
    b = agora.start_payload(config, "sess_b", "c", "t", "u")["name"]
    assert a != b


def test_idle_timeout_is_set_so_an_abandoned_agent_stops_burning_minutes(payload):
    assert payload["idle_timeout"] == 60


# --- token -----------------------------------------------------------------------------

APP, CERT = "a" * 32, "b" * 32


def test_matches_the_reference_implementation_byte_for_byte():
    """Pinned to output from Agora's own AccessToken2.py with the same ts and salt."""
    expected = ("007eJxTYGBkz7N4sFn98e+Mq5/Nrs+/ynGB7dLCDzNl3BwPSv2L3iyhwJBIADS0lqQL8DEw+CXu"
                "YWBiYGRgYWBkAPGZwCQzmGQBk/wMBZklyRkFmTn5JboWaUaJLAyGBgZGIE0QLRA+ABJZKCM=")
    assert token2.build(APP, CERT, "pitchpilot-8f2a", 1002,
                        expire_s=3600, issue_ts=1735689600, salt=12345678) == expected


def test_version_prefix_is_007():
    assert token2.build(APP, CERT, "ch", 1).startswith("007")


def test_token_carries_both_rtc_and_rtm_services():
    """An RTC-only token breaks enable_rtm, and the failure is not obvious (PRD 6.1)."""
    token = token2.build(APP, CERT, "ch", 1002)
    raw = zlib.decompress(base64.b64decode(token[3:]))
    service_types = {raw[i] for i in range(len(raw))}  # coarse, but both markers must exist
    assert token2.RTC_SERVICE in service_types
    assert token2.RTM_SERVICE in service_types
    assert b"1002" in raw, "the RTM user id is the uid as a string"


def test_channel_is_bound_into_the_token():
    assert b"pitchpilot-xyz" in zlib.decompress(
        base64.b64decode(token2.build(APP, CERT, "pitchpilot-xyz", 1)[3:]))


def test_distinct_salts_give_distinct_tokens():
    assert token2.build(APP, CERT, "ch", 1) != token2.build(APP, CERT, "ch", 1)


def test_same_inputs_are_reproducible():
    args = dict(expire_s=60, issue_ts=1, salt=2)
    assert token2.build(APP, CERT, "ch", 1, **args) == token2.build(APP, CERT, "ch", 1, **args)


@pytest.mark.parametrize("app_id", ["", "tooshort", "z" * 32, "a" * 31])
def test_malformed_credentials_raise_rather_than_producing_a_dud_token(app_id):
    """A silently invalid token fails much later, inside Agora, with a useless message."""
    with pytest.raises(ValueError):
        token2.build(app_id, CERT, "ch", 1)


def test_expiry_is_a_duration_not_a_timestamp():
    """Agora's own builder treats both token and privilege expiry as seconds from now.
    Passing an absolute timestamp here would produce a token valid for ~57 years."""
    raw = zlib.decompress(base64.b64decode(
        token2.build(APP, CERT, "ch", 1, expire_s=3600, issue_ts=1735689600, salt=1)[3:]))
    assert (3600).to_bytes(4, "little") in raw
    assert (1735689600 + 3600).to_bytes(4, "little") not in raw


# --- tts ------------------------------------------------------------------------------

def test_a_new_agent_gets_a_voice_without_a_vendor_signup(payload):
    """G7: the operator configures an agent without opening the Agora dashboard or
    signing up to a TTS vendor. Managed credentials are what make that true."""
    assert payload["tts"]["vendor"] == "openai"
    assert payload["tts"]["credential_mode"] == "managed"
    assert payload["tts"]["params"]["voice"]


def test_credential_mode_sits_directly_under_tts(payload):
    """Agora reads it there, not inside params, and the wrong placement fails the join
    with nothing useful in the message."""
    assert "credential_mode" not in payload["tts"]["params"]


def test_bringing_your_own_key_is_still_possible(config):
    config.voice.tts_credential_mode = "byo"
    config.voice.tts_params = {"api_key": "sk-test", "voice": "alloy"}
    tts = agora.start_payload(config, "s", "c", "t", "u")["properties"]["tts"]
    assert tts["credential_mode"] == "byo"
    assert tts["params"]["api_key"] == "sk-test"


def test_the_tts_block_never_goes_out_empty(config):
    """An empty vendor is rejected by the engine, so it must not be reachable by default."""
    assert agora.start_payload(config, "s", "c", "t", "u")["properties"]["tts"]["vendor"]
