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
    greeting: str = ("Hi, you're speaking with an AI sales assistant. This call is "
                     "transcribed. What can I help you with?")
    goal_hierarchy: list[str] = ["book a demo", "qualify with BANT",
                                 "create a follow-up", "escalate to a human"]
    objection_strategies: dict[str, str] = Field(default_factory=lambda: dict(DEFAULT_STRATEGIES))
    escalation_triggers: list[str] = ["asks for a human", "legal or security questions",
                                      "repeated frustration"]
    escalation_seat_threshold: int = 500


class Voice(BaseModel):
    """Maps onto the Agora payload. Defaults are the PRD 12 reference values."""
    tts_vendor: str = ""
    tts_params: dict = {}
    speech_threshold: float = 0.5
    interrupt_duration_ms: int = 160
    speaking_interrupt_duration_ms: int = 320   # raise this if "mm-hmm" cuts the agent off
    prefix_padding_ms: int = 800
    silence_duration_ms: int = 320
    max_wait_ms: int = 3000
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
    llm_model: str = "llama-3.3-70b-versatile"


class AgentSecrets(BaseModel):
    """Write-only across the API. masked() is the only shape a console read may see."""
    calcom_api_key: str | None = None
    calcom_event_type_id: str | None = None
    hubspot_token: str | None = None
    hubspot_pipeline: str = "default"
    hubspot_deal_stage: str = "appointmentscheduled"
    slack_webhook_url: str | None = None

    SECRET_FIELDS: ClassVar[tuple[str, ...]] = ("calcom_api_key", "hubspot_token", "slack_webhook_url")

    def masked(self) -> dict:
        out = self.model_dump()
        for field in self.SECRET_FIELDS:
            out[field] = "set" if out.get(field) else None
        return out
