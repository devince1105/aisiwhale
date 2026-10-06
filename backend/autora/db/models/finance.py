"""Budgets and the transaction ledger (logs/platform/06_BUSINESS_REVENUE.md).

``transactions`` is the single financial fact table. Revenue and expenses are views over it.
Rows are append-only: a database trigger rejects UPDATE and DELETE (migration 0002), so a
correction is a new compensating transaction, never an edit.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from autora.db.base import (
    Base,
    CreatedAtMixin,
    IdMixin,
    TimestampMixin,
    check_in,
    check_regex,
)


class CustomerKind(StrEnum):
    """What a customer is to the company. The first three pay; ``comp`` does not (D-228)."""

    SUBSCRIBER = "subscriber"
    SPONSOR = "sponsor"
    CLIENT = "client"
    COMP = "comp"
    """Given access by an admin, for internal testing (D-228): no order, no payment, no revenue,
    and never counted as a paying customer."""


PAYING_KINDS = frozenset(
    {CustomerKind.SUBSCRIBER.value, CustomerKind.SPONSOR.value, CustomerKind.CLIENT.value}
)


class Customer(IdMixin, TimestampMixin, Base):
    """Somebody who pays a business of this company (ARCHITECTURE_V2_1 §7, T-612).

    **This table holds no personal data, by design.** No name, no email, no address, no card —
    only ``external_ref``, the id the payment provider knows them by. Everything a person could
    be identified by stays with the provider, which is where it is already protected and where
    a deletion request goes. What the company needs from a customer is what it earns from them
    and when they left, and neither of those needs a name.

    The row exists so that "what does each customer earn us" is answerable on the day the first
    payment arrives, rather than being a migration nobody has time for that week. It is small
    on purpose: invoices, tax, receivables and reconciliation are deliberately not here.
    """

    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("company_id", "external_ref"),
        check_in("kind", CustomerKind),
        CheckConstraint(
            "churned_at IS NULL OR churned_at >= acquired_at", name="churned_after_acquired"
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), index=True)
    business_unit_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("business_units.id"))
    """Which business they are a customer of. NULL only while a company has no businesses."""
    external_ref: Mapped[str]
    """The payment provider's id for them. The only identifier this company stores."""
    kind: Mapped[str]
    acquired_at: Mapped[datetime]
    churned_at: Mapped[datetime | None]
    """When they stopped paying. A churned customer is kept: what they earned still happened."""


class BudgetPeriod(StrEnum):
    CYCLE = "cycle"
    DAY = "day"
    MONTH = "month"


class TransactionKind(StrEnum):
    EXPENSE = "expense"
    REVENUE = "revenue"
    CAPITAL_IN = "capital_in"
    CAPITAL_OUT = "capital_out"
    TRANSFER = "transfer"


class TransactionSource(StrEnum):
    SYSTEM = "system"
    HUMAN = "human"
    INTEGRATION = "integration"


class Budget(IdMixin, TimestampMixin, Base):
    """A recurring spending envelope. ``project_id`` NULL means the company-wide cap."""

    __tablename__ = "budgets"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "business_unit_id",
            "project_id",
            "period",
            postgresql_nulls_not_distinct=True,
        ),
        check_in("period", BudgetPeriod),
        check_regex("currency", "^[A-Z]{3}$"),
        CheckConstraint("amount >= 0", name="amount_non_negative"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"))
    business_unit_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("business_units.id"))
    """The envelope's owner, between the company and a project: company (both NULL) -> business
    unit -> project. Four layers of cap, all checked by the same guard (T-600)."""
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"))
    period: Mapped[str]
    amount: Mapped[Decimal]
    currency: Mapped[str] = mapped_column(server_default="TWD")
    """The base currency (D-023). The cost guard converts it to the meter's USD to compare."""
    hard_cap: Mapped[bool] = mapped_column(server_default="true")


class Transaction(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("idempotency_key"),
        check_in("kind", TransactionKind),
        check_in("source", TransactionSource),
        check_regex("category", "^[a-z][a-z0-9_]*$"),
        check_regex("currency", "^[A-Z]{3}$"),
        # The sign lives in `kind`; amounts are always positive.
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint(
            "(source_amount IS NULL) = (source_currency IS NULL) "
            "AND (source_amount IS NULL) = (fx_rate IS NULL)",
            name="conversion_complete",
        ),
        CheckConstraint("fx_rate IS NULL OR fx_rate > 0", name="fx_rate_positive"),
        Index("ix_transactions_company_occurred", "company_id", "occurred_at"),
        Index("ix_transactions_project_occurred", "project_id", "occurred_at"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"))
    business_unit_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("business_units.id"))
    """Which business earned or spent it. Denormalised on purpose: a project implies its unit,
    but revenue from a product has no project, and a unit's P&L must be one query (T-600)."""
    product_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("products.id"))
    """Which offering earned it. Set on revenue, usually NULL on costs."""
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"))
    customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("customers.id"))
    """Who paid it (T-612). NULL on costs, and on revenue that came from nobody in particular."""
    kind: Mapped[str]
    category: Mapped[str]
    """model_cost, tool_cost, ads, subscription, sponsorship, ..."""
    amount: Mapped[Decimal]
    """In ``currency``, which is always the base (D-023): the ledger has one currency, so a
    balance is a sum and never a conversion."""
    currency: Mapped[str] = mapped_column(server_default="TWD")
    source_amount: Mapped[Decimal | None]
    """What arrived, before conversion — the model calls' USD, say. NULL when it arrived in
    the base. Kept so the row can be checked against the meter it came from."""
    source_currency: Mapped[str | None]
    fx_rate: Mapped[Decimal | None]
    """Base units per source unit, as used on this row. Changing ``FX_RATES`` later does not
    touch it: the past was converted at the rate of its day."""
    ref_type: Mapped[str | None]
    ref_id: Mapped[uuid.UUID | None]
    occurred_at: Mapped[datetime]
    source: Mapped[str]
    idempotency_key: Mapped[str]
    memo: Mapped[str | None]


class PriceInterval(StrEnum):
    MONTH = "month"
    YEAR = "year"


class PriceState(StrEnum):
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


class MembershipState(StrEnum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"


class GrantSource(StrEnum):
    """Where a stretch of membership came from (D-228)."""

    PAYMENT = "payment"
    """Bought (P8 writes these; until then a purchase's stretch is on its payment)."""
    ADMIN_COMP = "admin_comp"
    """Given by an admin, for internal testing: no order, no payment, no ledger row."""


class Price(IdMixin, TimestampMixin, Base):
    """What a product costs, and how long one payment of it lasts (T-701, D-024).

    Not a column on ``products``: a price changes and a product does not. Raising the yearly
    price retires one row and adds another, so every payment keeps pointing at the price it was
    sold at. The price is the company's own — with one-time payments there is nothing at the
    provider to point at, the amount goes out with each order.
    """

    __tablename__ = "prices"
    __table_args__ = (
        check_in("interval", PriceInterval),
        check_in("state", PriceState),
        check_regex("currency", "^[A-Z]{3}$"),
        CheckConstraint("amount > 0", name="amount_positive"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), index=True)
    amount: Mapped[Decimal]
    currency: Mapped[str] = mapped_column(server_default="TWD")
    interval: Mapped[str]
    """How long one payment buys: a month or a year of access."""
    state: Mapped[str] = mapped_column(server_default=PriceState.ACTIVE.value)


class Membership(IdMixin, TimestampMixin, Base):
    """A customer's access to a product, and until when it lasts (T-701, D-024).

    Bought, not billed: each payment extends ``expires_at`` by the price's interval, and nothing
    charges anybody again. One row per customer and product — renewing extends it, coming back
    after it lapsed reopens it; the periods each payment bought are on the payments.

    Whether somebody may read is ``expires_at > now``, answered at the moment it is asked.
    ``state`` is bookkeeping for the company: EXPIRED is written once a day by the cycle, and it
    is what churns the customer.
    """

    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("customer_id", "product_id"),
        check_in("state", MembershipState),
        CheckConstraint("expires_at > started_at", name="expires_after_start"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), index=True)
    business_unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("business_units.id"))
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"), index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"))
    state: Mapped[str] = mapped_column(server_default=MembershipState.ACTIVE.value)
    started_at: Mapped[datetime]
    """When the current unbroken stretch began: the first purchase, or the return after a lapse."""
    expires_at: Mapped[datetime]


class MembershipGrant(IdMixin, CreatedAtMixin, Base):
    """One stretch of membership given to a customer, and its history (D-228).

    ``memberships`` keeps where access stands today; this keeps how it got there, one row a
    grant. An admin's comp is ended by **revoking** it — ``revoked_at``, who and why are written
    on the row, nothing is deleted — and the membership's end is worked out again from what is
    still running.
    """

    __tablename__ = "membership_grants"
    __table_args__ = (
        check_in("source", GrantSource),
        CheckConstraint("expires_at > started_at", name="expires_after_start"),
        CheckConstraint(
            "(source = 'payment') = (payment_id IS NOT NULL)", name="payment_only_when_paid"
        ),
        CheckConstraint(
            "source <> 'admin_comp' OR length(btrim(coalesce(reason, ''))) > 0",
            name="comp_has_a_reason",
        ),
        CheckConstraint(
            "(revoked_at IS NULL) = (revoked_by IS NULL)"
            " AND (revoked_at IS NULL) = (revoke_reason IS NULL)",
            name="revocation_complete",
        ),
        CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= started_at", name="revoked_after_start"
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), index=True)
    membership_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("memberships.id"), index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"), index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"))
    source: Mapped[str]
    started_at: Mapped[datetime]
    expires_at: Mapped[datetime]
    """Until when this grant gives access. A comp gives exactly this, not "this long from the
    end of what they have"."""
    reason: Mapped[str | None]
    """Why it was given. Required for a comp."""
    actor: Mapped[dict[str, Any]] = mapped_column(JSONB)
    """Who gave it, as the company records anybody (``Actor``): ``admin:<reader id>``, never an
    address."""
    payment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("payments.id"))
    revoked_at: Mapped[datetime | None]
    revoked_by: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    revoke_reason: Mapped[str | None]


class Payment(IdMixin, CreatedAtMixin, Base):
    """Money a provider says arrived, the ledger row it became, and what it bought (D-024).

    Written only by an integration, never by an agent (platform/06 §1). Append-only like the
    ledger it feeds: a refund will be its own row, not an edit to this one. The unique
    ``(provider, external_ref)`` is what makes a notification delivered twice one payment.
    """

    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("provider", "external_ref"),
        UniqueConstraint("transaction_id"),
        check_regex("currency", "^[A-Z]{3}$"),
        check_regex("provider", "^[a-z][a-z0-9_]*$"),
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint(
            "(membership_id IS NULL) = (grants_from IS NULL) "
            "AND (membership_id IS NULL) = (grants_until IS NULL) "
            "AND (grants_until IS NULL OR grants_until > grants_from)",
            name="grant_complete",
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), index=True)
    business_unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("business_units.id"))
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"), index=True)
    price_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("prices.id"))
    membership_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("memberships.id"), index=True
    )
    """NULL for a payment that bought no access. Every payment today buys some, but the ledger
    should not have to change the day one does not."""
    grants_from: Mapped[datetime | None]
    grants_until: Mapped[datetime | None]
    """The stretch of access this payment bought. The history a membership row does not keep."""
    transaction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("transactions.id"))
    provider: Mapped[str]
    """Which provider took the money, as a token (``payuni``). The core never branches on it."""
    external_ref: Mapped[str]
    """The provider's id for the charge (PAYUNi's trade number). The idempotency key, in effect."""
    amount: Mapped[Decimal]
    currency: Mapped[str] = mapped_column(server_default="TWD")
    paid_at: Mapped[datetime]


class OrderState(StrEnum):
    PENDING = "PENDING"
    PAID = "PAID"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


class Order(IdMixin, TimestampMixin, Base):
    """What somebody said they wanted to buy, before any money moved (T-702, D-024).

    A one-time payment leaves the site and comes back through the provider, and the notification
    that comes back knows only its own trade number. The order is what that number means: which
    price, for which reader, for how much. Without it a payment is money from nobody for nothing.

    ``mer_trade_no`` is ours and unique per provider — it is what we send out and what comes
    back. ``external_ref`` is the provider's own number for the charge, known only afterwards.
    """

    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("provider", "mer_trade_no"),
        check_in("state", OrderState),
        check_regex("provider", "^[a-z][a-z0-9_]*$"),
        check_regex("currency", "^[A-Z]{3}$"),
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint(
            "(state <> 'PAID') = (payment_id IS NULL)", name="paid_order_has_its_payment"
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), index=True)
    price_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prices.id"))
    customer_ref: Mapped[str]
    """Who it is for, as the site knows them: ``reader:<id>`` (D-018 — never an address)."""
    amount: Mapped[Decimal]
    currency: Mapped[str] = mapped_column(server_default="TWD")
    provider: Mapped[str]
    mer_trade_no: Mapped[str]
    state: Mapped[str] = mapped_column(server_default=OrderState.PENDING.value)
    payment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("payments.id"))
    """The payment that settled it. Set with PAID, in the same transaction."""
