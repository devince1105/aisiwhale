"""coin_accounts, coin_wallets, coin_txns, coin_entries: the Whale Coin ledger (P3-A)

D-223: coins are given by the platform and spent on it — never sold, moved between readers or
cashed. ``logs/platform/18_MONETIZATION_BLUEPRINT.md`` §8, as specified for P3-A:

- double entry in whole coins: every movement is a ``coin_txns`` row and, unless a grant was
  capped to nothing, two ``coin_entries`` that sum to zero — the reader's account and one of the
  platform's three (ISSUANCE, BURN, ADJUSTMENT, written here);
- ``coin_wallets`` keeps each reader's balance, and is the row an operation locks;
- a cap stops a movement from raising a balance past it (``amount <= 0 OR balance_after <=
  cap``); a balance already above it — kept after a downgrade (D-219) or a refund (D-220) —
  stays, and a grant there is written as 0;
- accounts, transactions and entries are never changed or deleted (``autora_forbid_mutation``);
  a wallet is never deleted, and only its balance, last transaction and time may change;
- when a transaction commits, a deferred check proves it: its legs balance and land on the
  right accounts, a refund matches the spend it reverses, and the reader's wallet equals the sum
  of their entries and the balance after their last transaction.

No API, no grant policy and no spending yet (P3-B, P3-C, P4). HOLD, CAPTURE, RELEASE and ESCROW
come with P6a.

Revision ID: 0072
Revises: 0071
Create Date: 2026-10-07 10:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0072"
down_revision: str | None = "0071"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS = "'MONTHLY_GRANT', 'PROMOTION_GRANT', 'ADMIN_ADJUSTMENT', 'SPEND', 'REFUND'"
SYSTEM_ACCOUNTS = ("ISSUANCE", "BURN", "ADJUSTMENT")
APPEND_ONLY = ("coin_accounts", "coin_txns", "coin_entries")

CHECK_FUNCTIONS = """
CREATE FUNCTION autora_coin_check_wallet(reader uuid) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE
    w coin_wallets%ROWTYPE;
    ledger bigint;
    last_after bigint;
BEGIN
    SELECT * INTO w FROM coin_wallets WHERE reader_id = reader;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'reader % has coin transactions but no wallet', reader
            USING ERRCODE = 'check_violation';
    END IF;
    SELECT coalesce(sum(amount), 0) INTO ledger FROM coin_entries WHERE account_id = w.account_id;
    IF ledger <> w.balance THEN
        RAISE EXCEPTION 'wallet of reader % says %, its entries sum to %', reader, w.balance, ledger
            USING ERRCODE = 'check_violation';
    END IF;
    IF w.last_txn_id IS NOT NULL THEN
        SELECT balance_after INTO last_after FROM coin_txns WHERE id = w.last_txn_id;
        IF last_after <> w.balance THEN
            RAISE EXCEPTION 'wallet of reader % says %, its last transaction left %',
                reader, w.balance, last_after
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
END;
$$;

CREATE FUNCTION autora_coin_check_txn(txn uuid) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE
    t coin_txns%ROWTYPE;
    original coin_txns%ROWTYPE;
    reader_account uuid;
    legs integer;
    total bigint;
    reader_leg bigint;
    other_key text;
    expected text;
BEGIN
    SELECT * INTO t FROM coin_txns WHERE id = txn;
    SELECT id INTO reader_account FROM coin_accounts WHERE reader_id = t.reader_id;
    SELECT count(*), coalesce(sum(amount), 0) INTO legs, total
        FROM coin_entries WHERE txn_id = txn;
    IF t.amount = 0 THEN
        IF legs <> 0 THEN
            RAISE EXCEPTION 'coin transaction % moves nothing but has % entries', txn, legs
                USING ERRCODE = 'check_violation';
        END IF;
    ELSE
        IF legs <> 2 OR total <> 0 THEN
            RAISE EXCEPTION 'coin transaction % does not balance: % entries summing to %',
                txn, legs, total
                USING ERRCODE = 'check_violation';
        END IF;
        SELECT amount INTO reader_leg FROM coin_entries
            WHERE txn_id = txn AND account_id = reader_account;
        IF reader_leg IS DISTINCT FROM t.amount THEN
            RAISE EXCEPTION 'coin transaction % says %, the reader''s entry says %',
                txn, t.amount, reader_leg
                USING ERRCODE = 'check_violation';
        END IF;
        SELECT a.system_key INTO other_key
            FROM coin_entries e JOIN coin_accounts a ON a.id = e.account_id
            WHERE e.txn_id = txn AND e.account_id <> reader_account;
        expected := CASE t.kind
            WHEN 'MONTHLY_GRANT' THEN 'ISSUANCE'
            WHEN 'PROMOTION_GRANT' THEN 'ISSUANCE'
            WHEN 'ADMIN_ADJUSTMENT' THEN 'ADJUSTMENT'
            ELSE 'BURN'
        END;
        IF other_key IS DISTINCT FROM expected THEN
            RAISE EXCEPTION 'coin transaction % (%) must meet %, not %',
                txn, t.kind, expected, other_key
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    IF t.kind = 'REFUND' THEN
        SELECT * INTO original FROM coin_txns WHERE id = t.reverses_txn_id;
        IF original.kind <> 'SPEND' OR original.reader_id <> t.reader_id
                OR original.amount <> -t.amount THEN
            RAISE EXCEPTION 'refund % does not give back spend % in full', txn, t.reverses_txn_id
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    PERFORM autora_coin_check_wallet(t.reader_id);
END;
$$;

CREATE FUNCTION autora_coin_txn_committed() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    PERFORM autora_coin_check_txn(NEW.id);
    RETURN NULL;
END;
$$;

CREATE FUNCTION autora_coin_entry_committed() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    PERFORM autora_coin_check_txn(NEW.txn_id);
    RETURN NULL;
END;
$$;

CREATE FUNCTION autora_coin_wallet_committed() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    PERFORM autora_coin_check_wallet(NEW.reader_id);
    RETURN NULL;
END;
$$;

CREATE FUNCTION autora_coin_wallet_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'coin_wallets: a wallet is never deleted'
            USING ERRCODE = 'restrict_violation';
    END IF;
    IF NEW.reader_id <> OLD.reader_id OR NEW.account_id <> OLD.account_id
            OR NEW.created_at <> OLD.created_at THEN
        RAISE EXCEPTION 'coin_wallets: only balance, last_txn_id and updated_at may change'
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$;
"""

TRIGGERS = """
CREATE TRIGGER coin_wallets_guard BEFORE UPDATE OR DELETE ON coin_wallets
    FOR EACH ROW EXECUTE FUNCTION autora_coin_wallet_guard();
CREATE CONSTRAINT TRIGGER coin_txns_balanced AFTER INSERT ON coin_txns
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION autora_coin_txn_committed();
CREATE CONSTRAINT TRIGGER coin_entries_balanced AFTER INSERT ON coin_entries
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION autora_coin_entry_committed();
CREATE CONSTRAINT TRIGGER coin_wallets_match_ledger AFTER INSERT OR UPDATE ON coin_wallets
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION autora_coin_wallet_committed();
"""


def _statements(sql: str) -> list[str]:
    """Split on the ``$$;`` that ends a function, or the ``;`` that ends a trigger."""
    if "$$" in sql:
        return [part.strip() + "$$" for part in sql.split("$$;") if part.strip()]
    return [part.strip() for part in sql.split(";") if part.strip()]


def upgrade() -> None:
    op.create_table(
        "coin_accounts",
        sa.Column("owner_type", sa.Text(), nullable=False),
        sa.Column("reader_id", sa.UUID(), nullable=True),
        sa.Column("system_key", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "owner_type IN ('reader', 'system')", name=op.f("ck_coin_accounts_owner_type_valid")
        ),
        sa.CheckConstraint(
            "system_key IS NULL OR system_key IN ('ISSUANCE', 'BURN', 'ADJUSTMENT')",
            name=op.f("ck_coin_accounts_system_key_valid"),
        ),
        sa.CheckConstraint(
            "(owner_type = 'reader') = (reader_id IS NOT NULL)"
            " AND (owner_type = 'system') = (system_key IS NOT NULL)",
            name=op.f("ck_coin_accounts_owner_matches"),
        ),
        sa.ForeignKeyConstraint(
            ["reader_id"],
            ["readers.id"],
            name=op.f("fk_coin_accounts_reader_id_readers"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_coin_accounts")),
        sa.UniqueConstraint("reader_id", name=op.f("uq_coin_accounts_reader_id")),
        sa.UniqueConstraint("system_key", name=op.f("uq_coin_accounts_system_key")),
    )
    op.create_table(
        "coin_txns",
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("reader_id", sa.UUID(), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("requested", sa.BigInteger(), nullable=True),
        sa.Column("cap", sa.BigInteger(), nullable=True),
        sa.Column("balance_after", sa.BigInteger(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("reverses_txn_id", sa.UUID(), nullable=True),
        sa.Column("ref_type", sa.Text(), nullable=True),
        sa.Column("ref_id", sa.Text(), nullable=True),
        sa.Column("actor", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "meta",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.CheckConstraint(f"kind IN ({KINDS})", name=op.f("ck_coin_txns_kind_valid")),
        sa.CheckConstraint(
            "idempotency_key ~ '^[a-z]+:[A-Za-z0-9:_.-]{1,190}$'",
            name=op.f("ck_coin_txns_idempotency_key_format"),
        ),
        sa.CheckConstraint(
            "(kind = 'MONTHLY_GRANT' AND idempotency_key LIKE 'grant:%')"
            " OR (kind = 'PROMOTION_GRANT' AND idempotency_key LIKE 'promo:%')"
            " OR (kind = 'ADMIN_ADJUSTMENT' AND idempotency_key LIKE 'adj:%')"
            " OR (kind = 'SPEND' AND idempotency_key LIKE 'spend:%')"
            " OR (kind = 'REFUND' AND idempotency_key = 'refund:' || reverses_txn_id::text)",
            name=op.f("ck_coin_txns_key_names_its_kind"),
        ),
        sa.CheckConstraint(
            "(kind IN ('MONTHLY_GRANT', 'PROMOTION_GRANT') AND amount >= 0)"
            " OR (kind = 'SPEND' AND amount < 0)"
            " OR (kind = 'REFUND' AND amount > 0)"
            " OR (kind = 'ADMIN_ADJUSTMENT' AND amount <> 0)",
            name=op.f("ck_coin_txns_amount_sign_matches_kind"),
        ),
        sa.CheckConstraint(
            "(kind = 'REFUND') = (reverses_txn_id IS NOT NULL)",
            name=op.f("ck_coin_txns_only_a_refund_reverses"),
        ),
        sa.CheckConstraint(
            "(kind IN ('MONTHLY_GRANT', 'PROMOTION_GRANT'))"
            " = (requested IS NOT NULL AND cap IS NOT NULL)",
            name=op.f("ck_coin_txns_a_grant_says_what_and_up_to"),
        ),
        sa.CheckConstraint(
            "requested IS NULL OR (requested >= 0 AND amount <= requested)",
            name=op.f("ck_coin_txns_never_more_than_requested"),
        ),
        sa.CheckConstraint(
            "cap IS NULL OR (cap >= 0 AND (amount <= 0 OR balance_after <= cap))",
            name=op.f("ck_coin_txns_within_cap"),
        ),
        sa.CheckConstraint(
            "balance_after >= 0", name=op.f("ck_coin_txns_balance_after_not_negative")
        ),
        sa.CheckConstraint(
            "kind <> 'ADMIN_ADJUSTMENT' OR length(btrim(coalesce(reason, ''))) > 0",
            name=op.f("ck_coin_txns_adjustment_has_a_reason"),
        ),
        sa.CheckConstraint(
            "(ref_type IS NULL) = (ref_id IS NULL)", name=op.f("ck_coin_txns_ref_complete")
        ),
        sa.ForeignKeyConstraint(
            ["reader_id"],
            ["readers.id"],
            name=op.f("fk_coin_txns_reader_id_readers"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reverses_txn_id"],
            ["coin_txns.id"],
            name=op.f("fk_coin_txns_reverses_txn_id_coin_txns"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_coin_txns")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_coin_txns_idempotency_key")),
        sa.UniqueConstraint("reverses_txn_id", name=op.f("uq_coin_txns_reverses_txn_id")),
    )
    op.create_index("ix_coin_txns_reader_id_occurred_at", "coin_txns", ["reader_id", "occurred_at"])
    op.create_table(
        "coin_entries",
        sa.Column("txn_id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("amount <> 0", name=op.f("ck_coin_entries_amount_not_zero")),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["coin_accounts.id"],
            name=op.f("fk_coin_entries_account_id_coin_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["txn_id"], ["coin_txns.id"], name=op.f("fk_coin_entries_txn_id_coin_txns")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_coin_entries")),
        sa.UniqueConstraint("txn_id", "account_id", name=op.f("uq_coin_entries_txn_id_account_id")),
    )
    op.create_index("ix_coin_entries_account_id_id", "coin_entries", ["account_id", "id"])
    op.create_table(
        "coin_wallets",
        sa.Column("reader_id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("balance", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_txn_id", sa.UUID(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("balance >= 0", name=op.f("ck_coin_wallets_balance_not_negative")),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["coin_accounts.id"],
            name=op.f("fk_coin_wallets_account_id_coin_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["last_txn_id"],
            ["coin_txns.id"],
            name=op.f("fk_coin_wallets_last_txn_id_coin_txns"),
        ),
        sa.ForeignKeyConstraint(
            ["reader_id"],
            ["readers.id"],
            name=op.f("fk_coin_wallets_reader_id_readers"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("reader_id", name=op.f("pk_coin_wallets")),
        sa.UniqueConstraint("account_id", name=op.f("uq_coin_wallets_account_id")),
    )

    for key in SYSTEM_ACCOUNTS:
        op.execute(
            "INSERT INTO coin_accounts (id, owner_type, system_key) "
            f"VALUES (gen_random_uuid(), 'system', '{key}')"
        )
    for table in APPEND_ONLY:
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION autora_forbid_mutation()"
        )
    # asyncpg takes one statement at a time
    for statement in _statements(CHECK_FUNCTIONS) + _statements(TRIGGERS):
        op.execute(statement)


def downgrade() -> None:
    # a coin that moved is a record: going back would have to delete it
    moved = op.get_bind().scalar(sa.text("SELECT count(*) FROM coin_txns"))
    if moved:
        raise RuntimeError(f"{moved} coin transactions exist; refusing to drop the ledger")
    op.execute("DROP TRIGGER coin_wallets_match_ledger ON coin_wallets")
    op.execute("DROP TRIGGER coin_entries_balanced ON coin_entries")
    op.execute("DROP TRIGGER coin_txns_balanced ON coin_txns")
    op.execute("DROP TRIGGER coin_wallets_guard ON coin_wallets")
    for table in APPEND_ONLY:
        op.execute(f"DROP TRIGGER {table}_append_only ON {table}")
    for function in (
        "autora_coin_wallet_guard()",
        "autora_coin_wallet_committed()",
        "autora_coin_entry_committed()",
        "autora_coin_txn_committed()",
        "autora_coin_check_txn(uuid)",
        "autora_coin_check_wallet(uuid)",
    ):
        op.execute(f"DROP FUNCTION {function}")
    op.drop_table("coin_wallets")
    op.drop_index("ix_coin_entries_account_id_id", table_name="coin_entries")
    op.drop_table("coin_entries")
    op.drop_index("ix_coin_txns_reader_id_occurred_at", table_name="coin_txns")
    op.drop_table("coin_txns")
    op.drop_table("coin_accounts")
