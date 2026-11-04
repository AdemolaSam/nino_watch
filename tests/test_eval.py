import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def load_labels() -> list[dict]:
    lines = (BACKEND_DIR / "evals" / "extraction" / "labels.jsonl").read_text().splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def test_label_count_and_mix():
    labels = load_labels()
    assert len(labels) == 30
    real = [lab for lab in labels if lab["source"] == "real"]
    syn = [lab for lab in labels if lab["source"] == "synthetic"]
    assert len(real) == 20
    assert len(syn) == 10


def test_label_schema():
    for lab in load_labels():
        assert lab["id"] and lab["title"] and lab["excerpt"] and lab["today"]
        exp = lab["expected"]
        assert isinstance(exp["is_relevant"], bool)
        if exp["is_relevant"]:
            assert exp["event_type"] and exp["place"] and exp["event_date"]
        else:
            assert exp["event_type"] is None


def test_real_labels_all_negative_and_synthetic_all_positive():
    for lab in load_labels():
        if lab["source"] == "real":
            assert lab["expected"]["is_relevant"] is False, lab["id"]
        else:
            assert lab["expected"]["is_relevant"] is True, lab["id"]


def test_scoring_math():
    sys.path.insert(0, str(BACKEND_DIR / "scripts"))
    import extraction_eval

    pos = {
        "is_relevant": True, "event_type": "flood", "place": "Lagos", "event_date": "2026-10-20",
    }
    neg = {"is_relevant": False, "event_type": None, "place": None, "event_date": None}
    pred_pos = {
        "is_relevant": True, "event_type": "flood", "place": {"name": "lagos "},
        "event_date": "2026-10-20",
    }
    pred_wrong = {
        "is_relevant": True, "event_type": "flood", "place": {"name": "X"},
        "event_date": "2026-01-01",
    }
    scored = [
        {"expected": dict(pos), "predicted": pred_pos},
        {"expected": dict(pos), "predicted": {"is_relevant": False}},
        {"expected": dict(neg), "predicted": {"is_relevant": False}},
        {"expected": dict(neg), "predicted": pred_wrong},
    ]
    m = extraction_eval.score_predictions(scored)
    assert m["n"] == 4
    assert m["relevance_accuracy"] == 0.5
    assert m["type_precision"] == 0.5
    assert m["type_recall"] == 0.5
    assert m["place_precision"] == 0.5
    assert m["place_recall"] == 0.5
    assert m["errors"] == 0


def test_scoring_counts_errors():
    sys.path.insert(0, str(BACKEND_DIR / "scripts"))
    import extraction_eval

    exp = {"is_relevant": True, "event_type": "flood", "place": "L", "event_date": "d"}
    scored = [{"expected": exp, "predicted": None}]
    m = extraction_eval.score_predictions(scored)
    assert m["errors"] == 1
    assert m["relevance_accuracy"] == 0.0
    assert m["type_recall"] == 0.0
