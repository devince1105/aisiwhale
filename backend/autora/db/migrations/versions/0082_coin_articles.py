"""articles.coin_price, article_unlocks: articles read for Whale Coins (P4, D-249)

An article may be COIN: ``access = 'coin'`` with a price of 1 to 100 coins, and only then a
price. A reader who pays has an ``article_unlocks`` row, written with the spend that paid for it
(``coin_txn_id``), one per reader and article, and never changed (0002's trigger).

Going back refuses while anybody has paid for an article or any article is COIN: dropping
either would lose what readers paid for, or leave an article no reader can be shown.

Revision ID: 0082
Revises: 0081
Create Date: 2026-10-08 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0082"
down_revision: str | None = "0081"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_articles_access_valid"), "articles", type_="check")
    op.create_check_constraint(
        op.f("ck_articles_access_valid"), "articles", "access IN ('free', 'members', 'coin')"
    )
    op.add_column("articles", sa.Column("coin_price", sa.Integer(), nullable=True))
    op.create_check_constraint(
        op.f("ck_articles_coin_price_iff_coin"),
        "articles",
        "(access = 'coin') = (coin_price IS NOT NULL)"
        " AND (coin_price IS NULL OR coin_price BETWEEN 1 AND 100)",
    )
    op.create_table(
        "article_unlocks",
        sa.Column("reader_id", sa.UUID(), nullable=False),
        sa.Column("article_id", sa.UUID(), nullable=False),
        sa.Column("coin_txn_id", sa.UUID(), nullable=False),
        sa.Column("price_paid", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("price_paid >= 1", name=op.f("ck_article_unlocks_price_paid_positive")),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["articles.id"],
            name=op.f("fk_article_unlocks_article_id_articles"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["coin_txn_id"], ["coin_txns.id"], name=op.f("fk_article_unlocks_coin_txn_id_coin_txns")
        ),
        sa.ForeignKeyConstraint(
            ["reader_id"],
            ["readers.id"],
            name=op.f("fk_article_unlocks_reader_id_readers"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_article_unlocks")),
        sa.UniqueConstraint("coin_txn_id", name=op.f("uq_article_unlocks_coin_txn_id")),
        sa.UniqueConstraint(
            "reader_id", "article_id", name=op.f("uq_article_unlocks_reader_id_article_id")
        ),
    )
    op.create_index("ix_article_unlocks_article_id", "article_unlocks", ["article_id"])
    op.execute(
        "CREATE TRIGGER article_unlocks_append_only BEFORE UPDATE OR DELETE "
        "ON article_unlocks FOR EACH ROW EXECUTE FUNCTION autora_forbid_mutation()"
    )


def downgrade() -> None:
    op.execute(
        "DO $$ BEGIN"
        " IF EXISTS (SELECT 1 FROM article_unlocks) THEN"
        "  RAISE EXCEPTION 'readers have paid for articles: refusing to drop article_unlocks';"
        " END IF;"
        " IF EXISTS (SELECT 1 FROM articles WHERE access = 'coin') THEN"
        "  RAISE EXCEPTION 'articles are COIN: refusing to drop their prices';"
        " END IF;"
        " END $$"
    )
    op.execute("DROP TRIGGER IF EXISTS article_unlocks_append_only ON article_unlocks")
    op.drop_index("ix_article_unlocks_article_id", table_name="article_unlocks")
    op.drop_table("article_unlocks")
    op.drop_constraint(op.f("ck_articles_coin_price_iff_coin"), "articles", type_="check")
    op.drop_column("articles", "coin_price")
    op.drop_constraint(op.f("ck_articles_access_valid"), "articles", type_="check")
    op.create_check_constraint(
        op.f("ck_articles_access_valid"), "articles", "access IN ('free', 'members')"
    )
