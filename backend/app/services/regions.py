from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import LanguageRef, RegionResponse
from app.repos import regions as regions_repo
from app.repos.models import Region

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"
REGIONS_DIR = CONFIG_DIR / "regions"
LANGUAGES_FILE = CONFIG_DIR / "languages.yaml"


class RegionConfig(BaseModel):
    id: str
    name: str
    names: list[str] = Field(default_factory=list)
    risk: str = "moderate"
    intensity: float = 0.5
    pilot: bool = False
    center: dict = Field(default_factory=lambda: {"lat": 0, "lng": 0})
    bbox: list[float] = Field(default_factory=lambda: [0, 0, 0, 0])
    countries: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=lambda: ["en"])
    news_sources: list[dict] = Field(default_factory=list)
    official_sources: list[dict] = Field(default_factory=list)
    weather: dict = Field(default_factory=dict)

    @property
    def display_names(self) -> list[str]:
        return self.names or [self.name]


class LanguageInfo(BaseModel):
    code: str
    label: str
    tested: bool = False


def load_region_config(region_id: str) -> RegionConfig:
    path = REGIONS_DIR / f"{region_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"unknown region {region_id!r}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return RegionConfig.model_validate(raw)


def load_all_region_configs() -> list[RegionConfig]:
    configs = []
    for path in sorted(REGIONS_DIR.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        configs.append(RegionConfig.model_validate(raw))
    return configs


@lru_cache(maxsize=1)
def load_languages() -> dict[str, LanguageInfo]:
    raw = yaml.safe_load(LANGUAGES_FILE.read_text(encoding="utf-8"))
    return {
        entry["code"]: LanguageInfo(
            code=entry["code"],
            label=entry["label"],
            tested=bool(entry.get("tested")),
        )
        for entry in raw["languages"]
    }


def to_region_response(row: Region) -> RegionResponse:
    """Build the API shape from the DB row (config JSONB mirrors the YAML)."""
    config = row.config or {}
    languages = load_languages()
    codes = list(config.get("languages", ["en"]))
    if config.get("pilot"):
        codes = list(languages)
    refs = [
        LanguageRef(code=code, label=languages[code].label if code in languages else code)
        for code in codes
    ]
    return RegionResponse(
        id=row.id,
        name=row.name,
        names=config.get("names") or [row.name],
        bbox=list(row.bbox),
        risk=row.risk,
        lat=row.center_lat,
        lng=row.center_lng,
        intensity=row.intensity,
        heat=[],  # B6 fills the heat layer from the climate grid
        countries=None,  # per-country values undefined until B6; field stays optional
        languages=refs,
    )


async def list_region_responses(session: AsyncSession) -> list[RegionResponse]:
    rows = await regions_repo.list_regions(session)
    return [to_region_response(row) for row in rows]


async def get_region_response(session: AsyncSession, region_id: str) -> RegionResponse | None:
    row = await regions_repo.get_region(session, region_id)
    return to_region_response(row) if row else None
