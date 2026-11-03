from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

EventType = Literal[
    "heat_death",
    "heat_illness",
    "crop_failure",
    "flood",
    "drought",
    "wildfire",
    "disease",
    "other",
]


class EventPlace(BaseModel):
    name: str = ""
    country: str = ""


class ExtractionResult(BaseModel):
    """Structured event extraction; see BACKEND.md 8.4."""

    is_relevant: bool
    event_type: EventType | None = None
    place: EventPlace = Field(default_factory=EventPlace)
    event_date: str | None = None
    count: int | None = None
    stated_cause: str | None = None
    evidence_quote: str = ""
    language: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class MatchSignal(BaseModel):
    """Same-event / official-statement match signal. Never the final label."""

    match: bool
    reason: str = ""


class OfficialStance(BaseModel):
    """How an official text relates to an event: supports, refutes, or neither."""

    stance: Literal["match", "contradict", "unrelated"]
    reason: str = ""


class TranslationResult(BaseModel):
    """Translated advisory; same keys as the advisory JSON."""

    model_config = ConfigDict(populate_by_name=True)

    happening: str
    at_risk: str = Field(alias="atRisk")
    actions: str


# Advisory content uses the same three keys in English and in translation.
AdvisoryContent = TranslationResult


class RadioScript(BaseModel):
    script: str


class SmsText(BaseModel):
    sms: str


class LlmParseError(ValueError):
    pass


def strip_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned


def parse_json(text: str, model_cls: type[BaseModel]) -> BaseModel:
    try:
        return model_cls.model_validate_json(strip_fences(text))
    except ValidationError as e:
        raise LlmParseError(f"{model_cls.__name__} validation failed: {e}") from e
    except ValueError as e:
        raise LlmParseError(f"{model_cls.__name__} is not valid JSON: {e}") from e
