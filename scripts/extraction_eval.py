"""Score extraction against hand labels (evals/extraction/labels.jsonl).

Writes evals/extraction/report.json and prints a one-line summary.
Uses the live router config; with LLM_EXTRACT=echo:... it runs offline
(plumbing check only — real numbers need the Meta API key).

Usage: uv run python scripts/extraction_eval.py
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.llm import router  # noqa: E402
from app.llm.client import LlmError, complete_json  # noqa: E402
from app.llm.prompts import PROMPT_VERSIONS, load_prompt  # noqa: E402
from app.llm.schemas import ExtractionResult, LlmParseError  # noqa: E402
from app.services.extract import build_extraction_user  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent.parent / "evals" / "extraction"


def norm_place(value: str | None) -> str:
    return (value or "").strip().lower()


def score_predictions(scored: list[dict]) -> dict:
    """Pure scoring over [{expected, predicted|None}]. predicted None = error."""
    n = len(scored)

    def pred_relevant(s: dict) -> bool:
        return bool((s["predicted"] or {}).get("is_relevant"))

    rel_ok = sum(1 for s in scored if pred_relevant(s) == bool(s["expected"]["is_relevant"]))
    exp_pos = [s for s in scored if s["expected"]["is_relevant"]]
    pred_pos = [s for s in scored if s["predicted"] and s["predicted"].get("is_relevant")]

    def pr(match_fn) -> tuple[float | None, float | None]:
        precision = (
            sum(1 for s in pred_pos if match_fn(s)) / len(pred_pos) if pred_pos else None
        )
        recall = (
            sum(1 for s in exp_pos if match_fn(s)) / len(exp_pos) if exp_pos else None
        )
        return precision, recall

    type_p, type_r = pr(
        lambda s: s["predicted"] and s["predicted"].get("event_type") == s["expected"]["event_type"]
    )
    place_p, place_r = pr(
        lambda s: s["predicted"]
        and norm_place((s["predicted"].get("place") or {}).get("name"))
        == norm_place(s["expected"]["place"])
    )
    date_p, date_r = pr(
        lambda s: s["predicted"] and s["predicted"].get("event_date") == s["expected"]["event_date"]
    )
    return {
        "n": n,
        "relevance_accuracy": rel_ok / n if n else None,
        "type_precision": type_p,
        "type_recall": type_r,
        "place_precision": place_p,
        "place_recall": place_r,
        "date_precision": date_p,
        "date_recall": date_r,
        "errors": sum(1 for s in scored if s["predicted"] is None),
    }


async def run_one(label: dict, system: str) -> dict:
    user = build_extraction_user(
        title=label["title"],
        excerpt=label["excerpt"],
        region_name="eval",
        language="en",
        today=label.get("today", "2026-11-01"),
    )
    try:
        result = await complete_json(
            "extract",
            system,
            user,
            ExtractionResult,
            prompt_version=PROMPT_VERSIONS["extract"],
            effort="low",
            max_tokens=2500,
        )
        assert isinstance(result, ExtractionResult)
        return {"expected": label["expected"], "predicted": result.model_dump(), "error": None}
    except (LlmParseError, LlmError) as e:
        err = f"{type(e).__name__}: {e}"
        return {"expected": label["expected"], "predicted": None, "error": err}


async def main() -> int:
    raw_lines = (EVAL_DIR / "labels.jsonl").read_text().splitlines()
    labels = [json.loads(line) for line in raw_lines if line.strip()]
    system = load_prompt("extract")
    route = router.resolve("extract")[0]
    details = []
    for label in labels:
        scored = await run_one(label, system)
        details.append({"id": label["id"], **scored})
        pred = scored["predicted"]
        status = "err" if pred is None else ("pos" if pred["is_relevant"] else "neg")
        exp = "pos" if label["expected"]["is_relevant"] else "neg"
        print(f"{label['id']}: expected={exp} predicted={status}", flush=True)
    report = {
        "provider": route.provider,
        "model": route.model,
        "prompt_version": PROMPT_VERSIONS["extract"],
        **score_predictions(details),
        "details": details,
    }
    (EVAL_DIR / "report.json").write_text(json.dumps(report, indent=2))
    m = report
    print(
        f"n={m['n']} acc={m['relevance_accuracy']} "
        f"type P/R={m['type_precision']}/{m['type_recall']} "
        f"place P/R={m['place_precision']}/{m['place_recall']} "
        f"date P/R={m['date_precision']}/{m['date_recall']} errors={m['errors']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
