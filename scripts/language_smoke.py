"""Translate the same sample advisory into every candidate language.

Writes one JSON file per language to evals/language/ for fluent-reader review
(see BACKEND.md 8.6). Uses the live router config; with LLM_TRANSLATE=fake:...
it runs offline for testing.

Usage: uv run python scripts/language_smoke.py
"""

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml  # noqa: E402

from app.llm import router  # noqa: E402
from app.llm.client import complete  # noqa: E402
from app.llm.prompts import PROMPT_VERSIONS, load_prompt  # noqa: E402

SAMPLE_ADVISORY = {
    "happening": (
        "Very hot days are expected this week, above 40C in the afternoon. "
        "Hot nights will bring little relief."
    ),
    "atRisk": "Outdoor workers, farmers, older people, and young children.",
    "actions": (
        "Avoid heavy work from 11am to 4pm. Drink water often. "
        "Check on older neighbours twice a day."
    ),
}

EVAL_DIR = Path(__file__).resolve().parent.parent / "evals" / "language"


async def translate_one(lang: str, system: str, prompt_version: str) -> dict:
    user = f"Target language: {lang}\nAdvisory JSON:\n{json.dumps(SAMPLE_ADVISORY)}"
    started = time.perf_counter()
    try:
        output = await complete("translate", system, user, effort="low", max_tokens=1000)
        return {
            "lang": lang,
            "ok": True,
            "output": output,
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }
    except Exception as e:
        return {
            "lang": lang,
            "ok": False,
            "error": f"{type(e).__name__}: {e}",
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }


async def main() -> int:
    with open(Path(__file__).resolve().parent.parent / "config" / "languages.yaml") as f:
        candidates = [
            lang["code"]
            for lang in yaml.safe_load(f)["languages"]
            if lang["code"] != "en"
        ]
    system = load_prompt("translate")
    prompt_version = PROMPT_VERSIONS["translate"]
    model = router.resolve("translate")[0].model
    EVAL_DIR.mkdir(parents=True, exist_ok=True)

    failures = 0
    for lang in candidates:
        result = await translate_one(lang, system, prompt_version)
        result["model"] = model
        result["prompt_version"] = prompt_version
        result["source"] = SAMPLE_ADVISORY
        (EVAL_DIR / f"{lang}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
        status = "ok" if result["ok"] else f"FAILED: {result['error']}"
        print(f"{lang}: {status}", flush=True)
        failures += 0 if result["ok"] else 1
    print(f"wrote {len(candidates)} files to {EVAL_DIR}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
