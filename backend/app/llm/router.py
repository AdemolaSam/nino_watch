import os
from dataclasses import dataclass

from app.core.config import settings

TASKS = ("extract", "verify_signal", "advisory", "translate", "outlet")

TASK_ENV_VARS = {
    "extract": "LLM_EXTRACT",
    "verify_signal": "LLM_VERIFY_SIGNAL",
    "advisory": "LLM_ADVISORY",
    "translate": "LLM_TRANSLATE",
    "outlet": "LLM_OUTLET",
}


@dataclass(frozen=True)
class Route:
    provider: str
    model: str


class LlmConfigError(ValueError):
    pass


def _raw_for(task: str) -> str:
    env_var = TASK_ENV_VARS[task]
    raw = os.environ.get(env_var)
    if raw is None:
        raw = getattr(settings, env_var.lower(), "") or ""
    if task == "outlet" and not raw.strip():
        return _raw_for("advisory")
    return raw


def resolve(task: str) -> list[Route]:
    """Route a task to an ordered provider:model chain (primary + fallbacks).

    Env format per task, e.g. ``LLM_EXTRACT=openweights:muse-spark-open,meta:muse-spark-1.3``.
    Reads the live environment first so tests can re-point tasks with monkeypatch.
    """
    if task not in TASK_ENV_VARS:
        raise LlmConfigError(f"unknown LLM task {task!r}; expected one of {sorted(TASKS)}")
    routes = []
    for part in _raw_for(task).split(","):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            raise LlmConfigError(
                f"bad route {part!r} for task {task!r}; expected 'provider:model'"
            )
        provider, model = part.split(":", 1)
        routes.append(Route(provider=provider.strip(), model=model.strip()))
    if not routes:
        raise LlmConfigError(f"no route configured for task {task!r}")
    return routes
