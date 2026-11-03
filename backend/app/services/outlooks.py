"""Published seasonal outlooks, kept distinct from observed incident reports."""

from functools import lru_cache

import yaml

from app.services.regions import CONFIG_DIR


@lru_cache(maxsize=1)
def load_outlooks() -> list[dict]:
    data = yaml.safe_load((CONFIG_DIR / "outlooks.yaml").read_text(encoding="utf-8"))
    return data["outlooks"]


def outlook_for(region_id: str) -> dict | None:
    return next((item for item in load_outlooks() if item["region_id"] == region_id), None)
