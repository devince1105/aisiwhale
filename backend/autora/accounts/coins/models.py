"""The Whale Coin ledger's tables (P3-A, D-223, ``logs/platform/18_MONETIZATION_BLUEPRINT.md`` §8).

Double entry, in whole coins:

- ``coin_accounts``: one per reader (made the first time their wallet is written) and three
  for the platform — ISSUANCE (where grants come from), BURN (where spending goes) and
  ADJUSTMENT (an admin's corrections). Never changed once written.
- ``coin_txns``: one movement, as the reader sees it — its kind, the signed change to their
  wallet, the balance after it, its idempotency key. Append-only.
- ``coin_entries``: the movement's two legs, one on the reader's account and one on a platform
  account, summing to zero. A grant capped to nothing is a transaction with no legs. Append-only.
- ``coin_wallets``: a reader's balance, kept with every transaction and checked against their
  entries when the transaction commits; and the row each operation locks.

The entries are the truth; the wallet is their sum, kept where a ``FOR UPDATE`` can reach it.
What a reader's tier, month or address means is not known here: the caller says how much and
up to what cap (P3-B).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from autora.db.base import Base, CreatedAtMixin, IdMixin, check_in, check_regex


class OwnerType(StrEnum):
    READER = "reader"
    SYSTEM = "system"


class SystemAccount(StrEnum):
    """The platform's side of every movement. ESCROW joins with P6a's held research coins."""

    ISSUANCE = "ISSUANCE"
    BURN = "BURN"
    ADJUSTMENT = "ADJUSTMENT"


class TxnKind(StrEnum):
    """What may move coins (D-223): no PURCHASE, TRANSFER or WITHDRAW. HOLD, CAPTURE and RELEASE
    join with P6a."""

    MONTHLY_GRANT = "MONTHLY_GRANT"
    PROMOTION_GRANT = "PROMOTION_GRANT"
    ADMIN_ADJUSTMENT = "ADMIN_ADJUSTMENT"
    SPEND = "SPEND"
    REFUND = "REFUND"


GRANTS = (TxnKind.MONTHLY_GRANT, TxnKind.PROMOTION_GRANT)

KEY_PATTERN = "^[a-z]+:[A-Za-z0-9:_.-]{1,190}$"
"""An idempotency key: a lowercase prefix that names the kind, a colon, and the caller's own
identity for the movement (``grant:vip:<reader>:2026-10``)."""

COUNTERPART = {
    TxnKind.MONTHLY_GRANT: SystemAccount.ISSUANCE,
    TxnKind.PROMOTION_GRANT: SystemAccount.ISSUANCE,
    TxnKind.ADMIN_ADJUSTMENT: SystemAccount.ADJUSTMENT,
    TxnKind.SPEND: SystemAccount.BURN,
    TxnKind.REFUND: SystemAccount.BURN,
}
"""The platform account on the other side of each kind. The commit-time check enforces it."""


class CoinAccount(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "coin_accounts"
    __table_args__ = (
        check_in("owner_type", OwnerType),
        check_in("system_key", SystemAccount, nullable=True),
        CheckConstraint(
            "(owner_type = 'reader') = (reader_id IS NOT NULL)"
            " AND (owner_type = 'system') = (system_key IS NOT NULL)",
            name="owner_matches",
        ),
        UniqueConstraint("reader_id"),
        UniqueConstraint("system_key"),
    )

    owner_type: Mapped[str]
    reader_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("readers.id", ondelete="RESTRICT")
    )
    system_key: Mapped[str | None]


class CoinWallet(CreatedAtMixin, Base):
    __tablename__ = "coin_wallets"
    __table_args__ = (
        CheckConstraint("balance >= 0", name="balance_not_negative"),
        UniqueConstraint("account_id"),
    )

    reader_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("readers.id", ondelete="RESTRICT"), primary_key=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("coin_accounts.id"))
    balance: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))
    last_txn_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("coin_txns.id", use_alter=True)
    )
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


class CoinTxn(IdMixin, Base):
    __tablename__ = "coin_txns"
    __table_args__ = (
        check_in("kind", TxnKind),
        check_regex("idempotency_key", KEY_PATTERN, name="idempotency_key_format"),
        CheckConstraint(
            "(kind = 'MONTHLY_GRANT' AND idempotency_key LIKE 'grant:%')"
            " OR (kind = 'PROMOTION_GRANT' AND idempotency_key LIKE 'promo:%')"
            " OR (kind = 'ADMIN_ADJUSTMENT' AND idempotency_key LIKE 'adj:%')"
            " OR (kind = 'SPEND' AND idempotency_key LIKE 'spend:%')"
            " OR (kind = 'REFUND' AND idempotency_key = 'refund:' || reverses_txn_id::text)",
            name="key_names_its_kind",
        ),
        CheckConstraint(
            "(kind IN ('MONTHLY_GRANT', 'PROMOTION_GRANT') AND amount >= 0)"
            " OR (kind = 'SPEND' AND amount < 0)"
            " OR (kind = 'REFUND' AND amount > 0)"
            " OR (kind = 'ADMIN_ADJUSTMENT' AND amount <> 0)",
            name="amount_sign_matches_kind",
        ),
        CheckConstraint(
            "(kind = 'REFUND') = (reverses_txn_id IS NOT NULL)", name="only_a_refund_reverses"
        ),
        CheckConstraint(
            "(kind IN ('MONTHLY_GRANT', 'PROMOTION_GRANT'))"
            " = (requested IS NOT NULL AND cap IS NOT NULL)",
            name="a_grant_says_what_and_up_to",
        ),
        CheckConstraint(
            "requested IS NULL OR (requested >= 0 AND amount <= requested)",
            name="never_more_than_requested",
        ),
        CheckConstraint(
            "cap IS NULL OR (cap >= 0 AND (amount <= 0 OR balance_after <= cap))",
            name="within_cap",
        ),
        CheckConstraint("balance_after >= 0", name="balance_after_not_negative"),
        CheckConstraint(
            "kind <> 'ADMIN_ADJUSTMENT' OR length(btrim(coalesce(reason, ''))) > 0",
            name="adjustment_has_a_reason",
        ),
        CheckConstraint("(ref_type IS NULL) = (ref_id IS NULL)", name="ref_complete"),
        UniqueConstraint("idempotency_key"),
        UniqueConstraint("reverses_txn_id"),
        Index("ix_coin_txns_reader_id_occurred_at", "reader_id", "occurred_at"),
    )

    kind: Mapped[str]
    reader_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("readers.id", ondelete="RESTRICT"))
    amount: Mapped[int] = mapped_column(BigInteger)
    """The signed change to the reader's wallet."""
    requested: Mapped[int | None] = mapped_column(BigInteger)
    """A grant: what the caller asked for, before the cap."""
    cap: Mapped[int | None] = mapped_column(BigInteger)
    """The cap this movement was held to; None when none applied (a refund, a debit, an
    admin's explicit override). A cap stops a movement from *raising* the balance past it; it
    says nothing about a balance already above it — kept after a downgrade (D-219) or a refund
    (D-220) — so a grant capped to nothing there is written all the same."""
    balance_after: Mapped[int] = mapped_column(BigInteger)
    idempotency_key: Mapped[str]
    reverses_txn_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("coin_txns.id"))
    ref_type: Mapped[str | None]
    ref_id: Mapped[str | None]
    actor: Mapped[dict[str, Any]] = mapped_column(JSONB)
    reason: Mapped[str | None]
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    occurred_at: Mapped[datetime] = mapped_column(server_default=func.now())


class CoinEntry(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "coin_entries"
    __table_args__ = (
        CheckConstraint("amount <> 0", name="amount_not_zero"),
        UniqueConstraint("txn_id", "account_id"),
        Index("ix_coin_entries_account_id_id", "account_id", "id"),
    )

    txn_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("coin_txns.id"))
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("coin_accounts.id"))
    amount: Mapped[int] = mapped_column(BigInteger)
    """Signed: positive raises the account's balance, negative lowers it."""
