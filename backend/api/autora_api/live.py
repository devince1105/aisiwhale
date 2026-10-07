"""The settings the back office changes (AD-11), as this API process holds them: in memory,
read once at its start — the deploy's migrations just woke the database — and changed with each
save here. /api/office-hours and its worker call (D-205) answer from memory and never wake the
database; 聯絡我們 reads its cap the same way. One API process: the save it made is what it has.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from autora.infra.settings import Settings
from autora.runtime.live_settings import DEFINITIONS, default, stored

log = logging.getLogger(__name__)


class LiveValues:
    def __init__(self) -> None:
        self.overrides: dict[str, Any] = {}

    def value(self, settings: Settings, key: str) -> Any:
        return self.overrides.get(key, default(settings, key))

    def set(self, key: str, value: Any | None) -> None:
        """A saved value, or None: back to the environment's."""
        if value is None:
            self.overrides.pop(key, None)
        else:
            self.overrides[key] = value

    async def recall(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        try:
            async with session_factory() as session:
                self.overrides = await stored(session)
        except Exception:  # noqa: BLE001 - a start without them runs on the environment's
            log.warning(
                "cannot read the back office's settings; the environment's for now", exc_info=True
            )


LIVE = LiveValues()
__all__ = ["DEFINITIONS", "LIVE", "LiveValues"]
