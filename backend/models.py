"""The contract between the console and the call runtime.

The console cannot save a shape the runtime cannot read, because both sides validate
against these models. Config is stored as a single jsonb column, so adding a field
here is the whole migration.
"""
from typing import ClassVar, Literal

from pydantic import BaseModel, Field

Objection = Literal["pricing", "trust", "product", "competitor"]

DEFAULT_STRATEGIES: dict[str, str] = {
    # Trade-shaped rather than defensive. "Reframe, probe, offer a pilot" left the agent
    # with nothing to do on a second push but repeat itself, and the models this runs on
    # have a documented accommodation reflex — they concede quickly and give things away
    # for nothing in return. Naming what comes back before anything goes out is the whole
    # difference between negotiating and caving, and the third-push rule gives it
    # somewhere to go that is not a discount. The last sentence is unchanged and
    # load-bearing: propose_concession is what may move terms, never the model's own words.
    #
    # Byte-identical in console/app/agents/[id]/page.tsx. A new agent starts from the
    # console's copy and a seeded one from here, so editing one and not the other makes
    # two agents differ by an oversight rather than by anyone's decision.
    "pricing": "Anchor on per-seat value before any total. Probe the real budget and the "
               "real blocker — it is usually the annual number, not the rate. Concede only "
               "in trades, never in gifts: name what you need back before you give "
               "anything, and give one thing at a time. If they push a third time, hold "
               "the line and offer a human rather than a better price. "
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


class Concession(BaseModel):
    """One rung of the negotiation ladder: what may be given, and what has to come back.

    `require` is not decoration. A concession with nothing asked in return is a discount
    with extra steps, and the whole reason this is config rather than prose is that the
    trade has to be decided by a person in advance, not improvised mid-call by a model
    that wants the conversation to go well.

    Deliberately not a price. The only number that may move is the volume_break already
    published on a Tier, which every prospect gets whether they push or not. Everything
    here is a term — pilot, onboarding, support, payment schedule — so the worst case of
    a wrongly-offered rung is an operational cost somebody agreed to beforehand, not
    margin given away on a call nobody reviewed.
    """
    give: str
    require: str
    # Some rungs only make sense at scale — included onboarding on a ten-seat deal costs
    # more than the deal. Rungs the seat count rules out are skipped, not refused.
    min_seats: int = 1


class Knowledge(BaseModel):
    currency: str = "USD"
    tiers: list[Tier] = []
    battlecards: dict[str, Battlecard] = {}
    # Ordered: cheapest first. The list *is* the ladder — propose_concession walks it and
    # never reorders, so an operator changes what gets offered first by moving a row.
    concessions: list[Concession] = []


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
        # nova on request: coral read as too flat on a live call. Changing this default
        # only reaches new agents — an existing one carries its own copy in the config
        # column and has to be changed on the Voice tab.
        "url": "https://api.openai.com/v1/audio/speech", "model": "tts-1", "voice": "nova"})
    # Raised from Agora's 0.5 / 160 / 320 after a call whose turns were cut at 0ms of
    # playback by "start_of_speech" twenty times in thirty: interrupt_duration_ms is the
    # only guard while the agent is still thinking, and at 160ms a breath or a keyboard
    # clears it. Agora's own guidance for noisy lines is 300-500 / 0.6-0.7.
    speech_threshold: float = 0.6
    interrupt_duration_ms: int = 300
    # 500 -> 700 after the operator reported the agent being cut off mid-sentence on live
    # calls. This is the only knob that fires while the agent is already speaking, so it is
    # the one lever for over-eager barge-in that costs nothing anywhere else: it is not
    # consulted at end-of-turn, so raising it cannot make the agent slower to reply. An
    # interruption now needs ~700ms of continuous speech — two or three words — while a
    # backchannel "mm-hmm" or "right" no longer stops playback. Ceiling is about 900ms:
    # past that someone who genuinely wants the floor has to talk over the agent for a full
    # second, which reads as the agent ignoring them. speech_threshold and
    # interrupt_duration_ms deliberately stay put — both are shared with start-of-turn
    # detection, so raising either to calm barge-in also makes the agent slower to notice
    # the prospect has started, which is the opposite of the second complaint.
    speaking_interrupt_duration_ms: int = 700   # raise this if "mm-hmm" cuts the agent off
    prefix_padding_ms: int = 800
    # Both raised after a live call where the agent talked over the prospect repeatedly.
    # 480ms still cut people off mid-thought — someone counting seats aloud, or saying an
    # email address, pauses longer than that. And max_wait is the harder of the two: it is
    # a hard cap that makes the agent reply even when end-of-turn is ambiguous, so at 3s it
    # was barging in on any sentence that took longer than three seconds to say. Tune per
    # deployment — a noisy line wants more, a brisk one less. Cut 700 → 550 on request:
    # this sits on every turn, so it is the honest lever for "slow to reply". 480 is the
    # known floor — below that it clipped people saying an email address aloud — so 550
    # keeps a 70ms margin over a failure we have actually seen.
    # Left at 550 when the operator next asked for a shorter gap before the agent replies.
    # The [turn]/[hops] lines for sess_303d and sess_ff5b say that gap is not endpointing:
    # a turn the model answers straight from text reaches first token in 250-1100ms, and
    # every turn that costs seconds is tool hops, with ttft almost exactly the sum of them
    # (sess_303d turn 9, ttft 7431ms against hops 2751 + 4590; sess_ff5b turn 6, ttft
    # 2122ms against 702 + 603 + 841). Endpointing is ~550ms of a 2-7s wait, so going to
    # the 480 floor buys 70ms and spends the entire margin over a clip we have already
    # shipped once. filler_wait_ms is the honest lever for "slow to reply" now.
    silence_duration_ms: int = 550
    # 5000 was the hard cap on the slowest turns of a live call (asr_ttlw 5065ms twice):
    # every ambiguous end-of-sentence cost five seconds before the LLM was even asked.
    # Agora's default is 3000, and semantic detection usually settles long before it.
    # Stays at 3000 under the same "slow to reply" complaint. It is a cap on an ambiguous
    # end-of-turn, not a cost paid on every turn — the slow turns in the logs above all
    # ended cleanly on silence and never reached it — so lowering it would not shorten a
    # single one of them, and it would put back the barging-in on any sentence that takes
    # longer than three seconds to say, which is the over-eager barge-in complaint again.
    max_wait_ms: int = 3000
    interruption_enabled: bool = True
    # These play only when the LLM has produced nothing for filler_wait_ms, which after
    # the streaming proxy means a tool hop, not an ordinary turn. Short reactions rather
    # than "one moment": a prospect who is told to wait on every turn hears a broken
    # agent, which is exactly what one live call sounded like.
    filler_phrases: list[str] = ["Right.", "Let me look.", "Sure."]
    # 1800 -> 1400 for the operator's "too long between the prospect finishing and the
    # agent starting". The wait is LLM and tool time, not VAD (see silence_duration_ms),
    # so this is the only knob that changes what the prospect hears during it. At 1800 the
    # filler landed on top of the reply on the common two-hop turn — sess_ff5b turn 2 came
    # back at ttft 1998ms, i.e. 1.8s of dead air and then "Right." colliding with the real
    # sentence. 1400 gets the acknowledgement out while the wait is still happening. 1200
    # is the floor: ordinary text-only turns answer in 250-1100ms, and firing on those is
    # how the agent starts sounding like it is stalling on every turn.
    filler_wait_ms: int = 1400


class ToolsEnabled(BaseModel):
    pricing: bool = True
    battlecards: bool = True
    calendar: bool = True
    crm: bool = True
    escalation: bool = True
    # Off leaves the agent able to reframe a price objection but with nothing to trade,
    # which is the behaviour it had before the ladder existed.
    negotiation: bool = True


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
    # Groq, not Mistral: the Mistral key went to zero quota (429 with
    # x-ratelimit-limit-req-minute: 0) on 2026-09-04. These defaults have to match whatever
    # LLM_URL points at in .env, because a config saved by the console without an explicit
    # value silently lands here — which is how a live call ended up asking Groq for
    # mistral-medium-latest and getting a 404 on every turn.
    llm_model: str = "openai/gpt-oss-20b"
    # The lead extractor (extract.py) runs beside the reply, so it can be the smaller and
    # faster model: it only has to fill a form from six turns of transcript. Same model for
    # now — Groq's free tier is one 8000 TPM bucket shared across both, so a second model
    # buys nothing here.
    extract_model: str = "openai/gpt-oss-20b"


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

    SECRET_FIELDS: ClassVar[tuple[str, ...]] = ("calcom_api_key", "hubspot_token",
                                                "slack_webhook_url", "notion_token")

    def masked(self) -> dict:
        out = self.model_dump()
        for field in self.SECRET_FIELDS:
            out[field] = "set" if out.get(field) else None
        return out
