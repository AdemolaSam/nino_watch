"""Scriptable fake LLM provider for tests and offline runs.

Queue canned outputs (or exceptions) then point a task at it, e.g.
``LLM_TRANSLATE=fake:test``. Every call is recorded in ``calls``.
"""

from collections import deque
from dataclasses import dataclass


@dataclass
class FakeResult:
    text: str
    tokens_in: int = 0
    tokens_out: int = 0


@dataclass
class FakeCall:
    model: str
    system: str
    user: str
    effort: str
    max_tokens: int


class FakeExhausted(Exception):
    pass


class FakeProvider:
    def __init__(self) -> None:
        self._queue: deque[str | Exception] = deque()
        self.calls: list[FakeCall] = []

    def queue(self, *items: str | Exception) -> None:
        self._queue.extend(items)

    def reset(self) -> None:
        self._queue.clear()
        self.calls.clear()

    @property
    def queued(self) -> int:
        return len(self._queue)

    async def generate(
        self, *, model: str, system: str, user: str, effort: str, max_tokens: int
    ) -> FakeResult:
        self.calls.append(
            FakeCall(model=model, system=system, user=user, effort=effort, max_tokens=max_tokens)
        )
        if not self._queue:
            raise FakeExhausted("fake provider queue is empty")
        item = self._queue.popleft()
        if isinstance(item, Exception):
            raise item
        tokens_in = max(1, len(user) // 4)
        tokens_out = max(1, len(item) // 4)
        return FakeResult(text=item, tokens_in=tokens_in, tokens_out=tokens_out)


_default_fake = FakeProvider()


def get_fake() -> FakeProvider:
    return _default_fake


def echo_generate(*, user: str, task: str = "translate") -> FakeResult:
    """Deterministic offline stand-in: always valid-shaped, always labeled fake."""
    import json

    preview = user.replace("\n", " ")[:80]
    if task == "extract":
        payload = {
            "is_relevant": False,
            "event_type": None,
            "place": {"name": "", "country": ""},
            "event_date": None,
            "count": None,
            "stated_cause": None,
            "evidence_quote": f"[FAKE ECHO] {preview}",
            "language": "en",
            "confidence": 0.0,
        }
    elif task == "verify_signal":
        # Valid as both MatchSignal and OfficialStance (pydantic ignores extras).
        payload = {"match": False, "stance": "unrelated", "reason": "[FAKE ECHO]"}
    elif task == "outlet":
        # Valid as both RadioScript and SmsText; validators still reject it.
        payload = {"script": "[FAKE ECHO] pack", "sms": "[FAKE ECHO] pack"}
    else:
        payload = {
            "happening": f"[FAKE TRANSLATION] {preview}",
            "atRisk": "[FAKE TRANSLATION]",
            "actions": "[FAKE TRANSLATION]",
        }
    text = json.dumps(payload)
    return FakeResult(text=text, tokens_in=max(1, len(user) // 4), tokens_out=50)
