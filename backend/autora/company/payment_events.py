"""Every payment notification, written down before it is dealt with (P2-B).

A provider's notification is the one message from outside that can grant anything, and the one
the site most needs to be able to explain afterwards. So it is kept first — ``receive``, in a
transaction of its own that the caller commits straight away — and only then opened and acted
on; ``record`` says how that went. When dealing with it fails, the row is still there, with the
error, for whoever has to work out what happened and for replaying it.

``record`` updates by id rather than through a loaded row, so it can be called after the
caller has rolled back whatever the notification tried to do.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from autora.db.models import PaymentEvent, PaymentEventOutcome
from autora.infra.ids import uuid7

PAYLOAD_MAX = 64 * 1024
"""The largest posted body kept as it was. A provider's form is a few hundred bytes; anything
this big is not one, and is kept as its size only."""

ERROR_MAX = 2000

AMOUNT_MAX = Decimal("1e12")
"""An amount the column can hold. A sealed notification is the provider's, so this is only a
guard against a number that would make writing the record fail."""


def payload_of(body: bytes, form: dict[str, str]) -> dict[str, Any]:
    """What to keep of a posted body: the form, or only its size when it is far too big."""
    if len(body) > PAYLOAD_MAX:
        return {"_oversize": len(body)}
    return dict(form)


async def receive(session: AsyncSession, *, provider: str, payload: dict[str, Any]) -> uuid.UUID:
    """Write a notification down as it arrived. Does not commit: the caller commits it alone,
    before doing anything else with the notification."""
    event_id = uuid7()
    session.add(PaymentEvent(id=event_id, provider=provider, payload=payload))
    await session.flush()
    return event_id


def opened(
    *,
    fields: dict[str, Any],
    mer_trade_no: str,
    external_ref: str,
    trade_status: str,
    amount: Decimal,
) -> dict[str, Any]:
    """What the envelope said, as ``record``'s keyword arguments."""
    keep = amount.is_finite() and abs(amount) < AMOUNT_MAX
    return {
        "fields": dict(fields),
        "mer_trade_no": mer_trade_no or None,
        "external_ref": external_ref or None,
        "trade_status": trade_status or None,
        "amount": amount if keep else None,
    }


async def record(
    session: AsyncSession,
    event_id: uuid.UUID,
    outcome: PaymentEventOutcome,
    *,
    error: str | None = None,
    order_id: uuid.UUID | None = None,
    payment_id: uuid.UUID | None = None,
    **envelope: Any,
) -> None:
    """Say what became of a notification. ``envelope`` is ``opened(...)``, when it could be."""
    values: dict[str, Any] = {
        "outcome": outcome.value,
        "error": error[:ERROR_MAX] if error else None,
        "order_id": order_id,
        "payment_id": payment_id,
        "processed_at": datetime.now(UTC),
        **envelope,
    }
    await session.execute(update(PaymentEvent).where(PaymentEvent.id == event_id).values(values))
