from __future__ import annotations

from dataclasses import asdict, dataclass
from threading import Lock


@dataclass
class SessionContext:
    category: str | None = None
    merchant: str | None = None
    period: str | None = None
    intent: str | None = None

    def has_context(self) -> bool:
        return any([self.category, self.merchant, self.period, self.intent])

    def to_dict(self) -> dict:
        return asdict(self)


class SessionContextStore:
    def __init__(self) -> None:
        self._sessions: dict[str, SessionContext] = {}
        self._lock = Lock()

    def get(self, session_id: str) -> SessionContext:
        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = SessionContext()
            return self._sessions[session_id]

    def update(self, session_id: str, **kwargs: str | None) -> SessionContext:
        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = SessionContext()
            ctx = self._sessions[session_id]
            for key, value in kwargs.items():
                if value is not None and hasattr(ctx, key):
                    setattr(ctx, key, value)
            return ctx
