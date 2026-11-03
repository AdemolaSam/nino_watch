from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


def to_camel(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:])


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class HealthResponse(CamelModel):
    status: str
    db: str
    redis: str
    last_ingest_at: datetime | None


class LanguageRef(CamelModel):
    code: str
    label: str


class HeatPoint(CamelModel):
    lat: float
    lng: float
    value: float


class CountryValue(CamelModel):
    name: str
    value: float


class RegionResponse(CamelModel):
    id: str
    name: str
    names: list[str]
    bbox: list[float]
    risk: str
    lat: float
    lng: float
    intensity: float
    heat: list[HeatPoint]
    countries: list[CountryValue] | None = None
    languages: list[LanguageRef]


class IncidentResponse(CamelModel):
    id: str
    region_id: str
    lat: float
    lng: float
    title: str
    status: str
    evidence: str


class AdvisoryResponse(CamelModel):
    region_id: str
    lang: str
    available: bool
    happening: str
    at_risk: str
    actions: str
    review_status: str = "unavailable"
    source_english: dict[str, str] | None = None


class OutlookResponse(CamelModel):
    region_id: str
    hazard: str
    summary: str
    source: str
    source_url: str
    issued_at: date
    valid_through: date


class OutletPackResponse(CamelModel):
    region_id: str
    lang: str
    available: bool
    radio_script: str
    sms: str


class ClimateCellResponse(CamelModel):
    lat: float
    lng: float
    temp: float
    anomaly: float | None


class ClimateResponse(CamelModel):
    bbox: list[float]
    cols: int
    rows: int
    baseline_years: str
    generated_at: datetime
    cells: list[ClimateCellResponse]
