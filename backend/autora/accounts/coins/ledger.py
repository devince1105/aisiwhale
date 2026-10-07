"""Moving Whale Coins: grant, spend, refund, adjust, and reading a balance (P3-A).

Every operation follows the same steps, inside the caller's transaction (nothing here commits):

1. make sure the reader has an account and a wallet (``INSERT … ON CONFLICT DO NOTHING``, so
   two first operations at once make one of each);
2. lock the reader's wallet row, ``FOR UPDATE`` — the only lock taken. Platform accounts keep
   no balance row and are never locked, and nothing here touches two readers' wallets (coins are
   never moved between readers, D-223), so operations on one reader queue and different readers
   never wait for each other;
3. look the idempotency key up, after the lock, so a repeat waits for the first and then finds
   it: the same movement again returns the first transaction (``created=False``); a different
   one under the same key is ``IdempotencyConflict``;
4. work out the amount and check it — a spend the balance cannot cover is
   ``InsufficientCoins``, an adjustment over the cap without an explicit override is
   ``CapExceeded``, and nothing is written;
5. write the transaction, its two entries (none for a grant capped to nothing) and the wallet.

The database checks it all again: the CHECK constraints, and — when the transaction commits —
that its entries balance and the wallet equals the reader's entries.

Grants never pass the cap the caller gives: ``min(requested, max(0, cap − balance))``. A cap
only stops a movement that raises the balance: a balance already above it (kept after a
downgrade, D-219, or raised by a refund, D-220) stays, and the month's grant there is 0. What the
cap and the request are (a tier's, a month's), and who is eligible, is P3-B's to say.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from autora.accounts.coins.models import (
    COUNTERPART,
    GRANTS,
    CoinAccount,
    CoinEntry,
    CoinTxn,
    CoinWallet,
    OwnerType,
    SystemAccount,
    TxnKind,
)
from autora.infra.ids import uuid7
from autora.runtime.actor import Actor


class CoinError(Exception):
    pass


class InsufficientCoins(CoinError):
    """The balance cannot cover it. Nothing was written."""


class IdempotencyConflict(CoinError):
    """This key already names a different movement. If raised from a write, the session's
    transaction is spoilt and the caller rolls it back."""


class CapExceeded(CoinError):
    """An adjustment would pass the cap, and the admin did not say to override it."""


class NotRefundable(CoinError):
    """Only a spend can be refunded, and only in full, once (D-220)."""


@dataclass(frozen=True)
class Posted:
    txn: CoinTxn
    created: bool
    """False when the key was already used for this movement: the first one, returned again."""


async def balance(session: AsyncSession, reader_id: uuid.UUID) -> int:
    """What the reader holds now. A reader whose wallet was never written holds nothing."""
    held = await session.scalar(select(CoinWallet.balance).where(CoinWallet.reader_id == reader_id))
    return held or 0


async def grant(
    session: AsyncSession,
    reader_id: uuid.UUID,
    *,
    requested: int,
    cap: int,
    idempotency_key: str,
    actor: Actor,
    kind: TxnKind = TxnKind.MONTHLY_GRANT,
    meta: dict[str, Any] | None = None,
) -> Posted:
    """Give up to ``requested`` coins, never past ``cap``. A grant capped to nothing is still
    written (amount 0, no entries), so its key is spent: the month was given, as nothing."""
    if kind not in GRANTS:
        raise CoinError(f"{kind} is not a grant")
    if requested < 0 or cap < 0:
        raise CoinError("a grant and its cap are never negative")
    wallet = await _lock_wallet(session, reader_id)
    if (txn := await _replay(session, idempotency_key, kind, reader_id)) is not None:
        return Posted(txn, created=False)
    amount = min(requested, max(0, cap - wallet.balance))
    txn = await _post(
        session, wallet, kind=kind, amount=amount, idempotency_key=idempotency_key, actor=actor,
        requested=requested, cap=cap, meta=meta,
    )  # fmt: skip
    return Posted(txn, created=True)


async def spend(
    session: AsyncSession,
    reader_id: uuid.UUID,
    *,
    amount: int,
    idempotency_key: str,
    actor: Actor,
    ref_type: str | None = None,
    ref_id: str | None = None,
    meta: dict[str, Any] | None = None,
) -> Posted:
    """Take ``amount`` coins for something on the platform. ``InsufficientCoins`` when the
    balance cannot cover it; the balance never goes below zero."""
    if amount <= 0:
        raise CoinError(f"a spend takes coins, got {amount}")
    wallet = await _lock_wallet(session, reader_id)
    existing = await _replay(session, idempotency_key, TxnKind.SPEND, reader_id)
    if existing is not None:
        if existing.amount != -amount or (existing.ref_type, existing.ref_id) != (ref_type, ref_id):
            raise IdempotencyConflict(f"{idempotency_key!r} was a different spend")
        return Posted(existing, created=False)
    if wallet.balance < amount:
        raise InsufficientCoins(f"{amount} needed, {wallet.balance} held")
    txn = await _post(
        session, wallet, kind=TxnKind.SPEND, amount=-amount, idempotency_key=idempotency_key,
        actor=actor, ref_type=ref_type, ref_id=ref_id, meta=meta,
    )  # fmt: skip
    return Posted(txn, created=True)


async def refund(
    session: AsyncSession,
    spend_txn_id: uuid.UUID,
    *,
    actor: Actor,
    meta: dict[str, Any] | None = None,
) -> Posted:
    """Give a spend back in full, whatever the cap (D-220). Once: refunding it again returns
    the first refund."""
    original = await session.get(CoinTxn, spend_txn_id)
    if original is None or original.kind != TxnKind.SPEND.value:
        raise NotRefundable("only a spend can be refunded")
    wallet = await _lock_wallet(session, original.reader_id)
    key = f"refund:{original.id}"
    if (txn := await _replay(session, key, TxnKind.REFUND, original.reader_id)) is not None:
        return Posted(txn, created=False)
    txn = await _post(
        session, wallet, kind=TxnKind.REFUND, amount=-original.amount, idempotency_key=key,
        actor=actor, reverses_txn_id=original.id, ref_type=original.ref_type,
        ref_id=original.ref_id, meta=meta,
    )  # fmt: skip
    return Posted(txn, created=True)


async def adjust(
    session: AsyncSession,
    reader_id: uuid.UUID,
    *,
    amount: int,
    reason: str,
    idempotency_key: str,
    actor: Actor,
    cap: int | None = None,
    override_cap: bool = False,
    meta: dict[str, Any] | None = None,
) -> Posted:
    """An admin's correction, up (``amount`` > 0) or down (< 0), with a reason.

    Up is held to ``cap`` unless ``override_cap`` says otherwise, which is written on the
    transaction (D-220); one of the two must be given. Down never leaves the balance below zero.
    """
    if amount == 0:
        raise CoinError("an adjustment moves coins")
    if not reason.strip():
        raise CoinError("an adjustment needs a reason")
    if amount > 0 and cap is None and not override_cap:
        raise CoinError("adding coins needs a cap, or an explicit override")
    wallet = await _lock_wallet(session, reader_id)
    existing = await _replay(session, idempotency_key, TxnKind.ADMIN_ADJUSTMENT, reader_id)
    if existing is not None:
        if existing.amount != amount:
            raise IdempotencyConflict(f"{idempotency_key!r} was a different adjustment")
        return Posted(existing, created=False)
    after = wallet.balance + amount
    if after < 0:
        raise InsufficientCoins(f"{-amount} to take, {wallet.balance} held")
    held_to = None
    if amount > 0 and not override_cap:
        if after > cap:  # type: ignore[operator]  (cap is given: checked above)
            raise CapExceeded(f"{after} would pass the cap of {cap}")
        held_to = cap
    txn = await _post(
        session, wallet, kind=TxnKind.ADMIN_ADJUSTMENT, amount=amount,
        idempotency_key=idempotency_key, actor=actor, cap=held_to, reason=reason.strip(),
        meta={**(meta or {}), "override_cap": bool(override_cap and amount > 0)},
    )  # fmt: skip
    return Posted(txn, created=True)


# --- the steps every operation shares ------------------------------------------------------------


async def _lock_wallet(session: AsyncSession, reader_id: uuid.UUID) -> CoinWallet:
    await session.execute(
        pg_insert(CoinAccount)
        .values(id=uuid7(), owner_type=OwnerType.READER.value, reader_id=reader_id)
        .on_conflict_do_nothing(index_elements=["reader_id"])
    )
    account_id = await session.scalar(
        select(CoinAccount.id).where(CoinAccount.reader_id == reader_id)
    )
    await session.execute(
        pg_insert(CoinWallet)
        .values(reader_id=reader_id, account_id=account_id)
        .on_conflict_do_nothing(index_elements=["reader_id"])
    )
    wallet = await session.scalar(
        select(CoinWallet)
        .where(CoinWallet.reader_id == reader_id)
        .with_for_update()
        .execution_options(populate_existing=True)  # the balance as of the lock, not as loaded
    )
    assert wallet is not None
    return wallet


async def _replay(
    session: AsyncSession, key: str, kind: TxnKind, reader_id: uuid.UUID
) -> CoinTxn | None:
    txn = await session.scalar(select(CoinTxn).where(CoinTxn.idempotency_key == key))
    if txn is None:
        return None
    if txn.kind != kind.value or txn.reader_id != reader_id:
        raise IdempotencyConflict(f"{key!r} already names another movement")
    return txn


async def _system_account(session: AsyncSession, key: SystemAccount) -> uuid.UUID:
    account_id = await session.scalar(
        select(CoinAccount.id).where(CoinAccount.system_key == key.value)
    )
    assert account_id is not None, f"the {key} account is written by migration 0072"
    return account_id


async def _post(
    session: AsyncSession,
    wallet: CoinWallet,
    *,
    kind: TxnKind,
    amount: int,
    idempotency_key: str,
    actor: Actor,
    requested: int | None = None,
    cap: int | None = None,
    reverses_txn_id: uuid.UUID | None = None,
    ref_type: str | None = None,
    ref_id: str | None = None,
    reason: str | None = None,
    meta: dict[str, Any] | None = None,
) -> CoinTxn:
    after = wallet.balance + amount
    txn = CoinTxn(
        id=uuid7(),
        kind=kind.value,
        reader_id=wallet.reader_id,
        amount=amount,
        requested=requested,
        cap=cap,
        balance_after=after,
        idempotency_key=idempotency_key,
        reverses_txn_id=reverses_txn_id,
        ref_type=ref_type,
        ref_id=ref_id,
        actor=actor.model_dump(),
        reason=reason,
        meta=meta or {},
    )
    session.add(txn)
    try:
        await session.flush()
    except IntegrityError as exc:
        if "uq_coin_txns_idempotency_key" in str(exc.orig):
            raise IdempotencyConflict(f"{idempotency_key!r} was taken meanwhile") from exc
        raise
    if amount:
        counterpart = await _system_account(session, COUNTERPART[kind])
        session.add_all(
            [
                CoinEntry(txn_id=txn.id, account_id=wallet.account_id, amount=amount),
                CoinEntry(txn_id=txn.id, account_id=counterpart, amount=-amount),
            ]
        )
    wallet.balance = after
    wallet.last_txn_id = txn.id
    wallet.updated_at = func.now()
    await session.flush()
    return txn
