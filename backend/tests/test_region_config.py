import pytest

from app.services.regions import (
    load_all_region_configs,
    load_languages,
    load_region_config,
)


def test_load_sahel_nigeria():
    cfg = load_region_config("sahel-nigeria")
    assert cfg.name == "Nigeria and the Sahel"
    assert cfg.risk == "extreme"
    assert cfg.pilot is True
    assert cfg.center == {"lat": 12, "lng": 8}
    assert cfg.bbox == [-17, 2, 40, 24]
    assert "ha" in cfg.languages
    assert cfg.display_names == ["Nigeria and the Sahel"]


def test_load_all_regions():
    configs = load_all_region_configs()
    ids = sorted(c.id for c in configs)
    assert ids == [
        "andean-coast", "central-america", "east-africa", "sahel-nigeria",
        "southeast-asia", "southern-africa",
    ]
    pilots = [c.id for c in configs if c.pilot]
    assert sorted(pilots) == ["sahel-nigeria", "southeast-asia"]


def test_unknown_region_raises():
    with pytest.raises(FileNotFoundError):
        load_region_config("atlantis")


def test_languages_have_labels():
    languages = load_languages()
    assert languages["ha"].label == "Hausa"
    assert languages["en"].tested is True
    assert languages["ha"].tested is False
