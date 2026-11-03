from pathlib import Path

PROMPT_VERSIONS = {
    "translate": "v2",
    "extract": "v1",
    "official_match": "v1",
    "same_event": "v1",
    "advisory": "v2",
    "outlet_radio": "v1",
    "outlet_sms": "v1",
}

_PROMPT_DIR = Path(__file__).parent / "prompts"


def load_prompt(name: str) -> str:
    path = _PROMPT_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"unknown prompt {name!r}")
    return path.read_text(encoding="utf-8").strip()
