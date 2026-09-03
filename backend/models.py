"""The contract between the console and the call runtime.

The console cannot save a shape the runtime cannot read, because both sides validate
against these models. Config is stored as a single jsonb column, so adding a field
here is the whole migration.
"""
from typing import ClassVar, Literal

from pydantic import BaseModel, Field

Objection = Literal["pricing", "trust", "product", "competitor"]

DEFAULT_STRATEGIES: dict[str, str] = {
    "pricing": "Reframe to per-seat value, probe the actual budget, offer a pilot. "
               "Never discount unprompted.",
    "trust": "Offer a relevant proof point, a small pilot, or a human rep.",
    "product": "Answer from tool data only. If the capability does not exist, say so "
               "plainly and pivot to what does.",
    "competitor": "Call get_battlecard first, acknowledge one genuine strength, then position.",
}


class Tier(BaseModel):
    name: str
    per_seat_month: float
    min_seats: int = 1
    max_seats: int | None = None
    volume_break: dict | None = None
    features: list[str] = []


class Battlecard(BaseModel):
    positioning: str
    we_win: list[str] = []
    we_concede: list[str] = []
    proof_point: str = ""


class Knowledge(BaseModel):
    currency: str = "USD"
    tiers: list[Tier] = []
    battlecards: dict[str, Battlecard] = {}


class Persona(BaseModel):
    identity: str
    # The first thing anyone hears, and it sets the register for the whole call — a stiff
    # greeting makes every warm line after it sound like a script.
    #
    # The transcription notice was dropped on the operator's instruction. PRD 11 asks for
    # both "AI-handled and transcribed" and this greeting is the only place either is said,
    # so the spec and the default now disagree by one half. The AI disclosure stays.
    # Not opened with a short interjection: "Hi there," on its own gets flushed to TTS as
    # its own clause and lands as an abrupt bare "Hi!" before the real sentence starts.
    greeting: str = ("Thanks for reaching out — I'm an AI assistant here on the sales team. "
                     "What can I help you with today?")
    goal_hierarchy: list[str] = ["book a demo", "qualify with BANT",
                                 "create a follow-up", "escalate to a human"]
    objection_strategies: dict[str, str] = Field(default_factory=lambda: dict(DEFAULT_STRATEGIES))
    escalation_triggers: list[str] = ["asks for a human", "legal or security questions",
                                      "repeated frustration"]
    escalation_seat_threshold: int = 500


class Voice(BaseModel):
    """Maps onto the Agora payload. Defaults are the PRD 12 reference values."""
    # Defaults to managed credentials so a brand-new agent produces a valid join payload
    # with no voice-vendor signup, which is what G7 promises. Set tts_credential_mode to
    # "byo" and put an api_key in tts_params to bring your own.
    tts_vendor: str = "openai"
    tts_credential_mode: str = "managed"
    # url is required by the engine even under managed credentials, and it validates the
    # value: only the vendor's real speech endpoint is accepted for the current SKU.
    tts_params: dict = Field(default_factory=lambda: {
        "url": "https://api.openai.com/v1/audio/speech", "model": "tts-1", "voice": "coral"})
    speech_threshold: float = 0.5
    interrupt_duration_ms: int = 160
    speaking_interrupt_duration_ms: int = 320   # raise this if "mm-hmm" cuts the agent off
    prefix_padding_ms: int = 800
    # Both raised after a live call where the agent talked over the prospect repeatedly.
    # 480ms still cut people off mid-thought — someone counting seats aloud, or saying an
    # email address, pauses longer than that. And max_wait is the harder of the two: it is
    # a hard cap that makes the agent reply even when end-of-turn is ambiguous, so at 3s it
    # was barging in on any sentence that took longer than three seconds to say. Tune per
    # deployment — a noisy line wants more, a brisk one less.
    silence_duration_ms: int = 700
    max_wait_ms: int = 5000
    interruption_enabled: bool = True
    filler_phrases: list[str] = ["One moment.", "Let me check that.", "Pulling that up."]


class ToolsEnabled(BaseModel):
    pricing: bool = True
    battlecards: bool = True
    calendar: bool = True
    crm: bool = True
    escalation: bool = True


class AgentConfig(BaseModel):
    persona: Persona
    voice: Voice = Voice()
    knowledge: Knowledge = Knowledge()
    tools_enabled: ToolsEnabled = ToolsEnabled()
    # Must name a model the provider behind LLM_URL actually serves — the id is not
    # portable, and Groq's "openai/gpt-oss-20b" is Cerebras's "gpt-oss-120b". Default
    # tracks Cerebras because Groq's free tier is 8000 TPM, about two tool-using turns a
    # minute, which is not enough to finish a call.
    # Change this with LLM_URL, never on its own — a model id from the wrong provider fails
    # every turn of a call. Groq's equivalent is "openai/gpt-oss-20b", but Groq's free tier
    # is 8000 tokens/minute, about two tool-using turns, and a real call died on it.
    # mistral-large is a 403 on the free tier; small is the most capable one it serves.
    # Picked by measurement against the other three the free tier serves: on the same four
    # turns it was the only one to record the lead as it went (4 update_lead_state calls,
    # reaching warm) rather than arriving at the booking with an empty panel. mistral-large
    # is a 403 here, and ministral-8b looped itself into a spurious escalation.
    llm_model: str = "mistral-medium-latest"


class AgentSecrets(BaseModel):
    """Write-only across the API. masked() is the only shape a console read may see."""
    calcom_api_key: str | None = None
    calcom_event_type_id: str | None = None
    hubspot_token: str | None = None
    hubspot_pipeline: str = "default"
    hubspot_deal_stage: str = "appointmentscheduled"
    slack_webhook_url: str | None = None
    notion_token: str | None = None
    # Database ids as they appear in a Notion URL. The write actually needs the data
    # source inside the database; tools/notion.py resolves that, so an operator never
    # has to find an id that no page in the Notion UI shows them.
    notion_leads_db: str | None = None
    notion_pricing_db: str | None = None

    SECRET_FIELDS: ClassVar[tuple[str, ...]] = ("calcom_api_key", "hubspot_token",
                                                "slack_webhook_url", "notion_token")

    def masked(self) -> dict:
        out = self.model_dump()
        for field in self.SECRET_FIELDS:
            out[field] = "set" if out.get(field) else None
        return out
