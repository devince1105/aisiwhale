"""stock_headlines: news headlines about the strip's stocks and their tone (D-091)

新聞情緒: each headline found for a stock (Finnhub's company news, Yahoo 股市's and 中央社's
feeds), the model's reading of its tone toward the company, and a line of why.

Revision ID: 0053
Revises: 0052
Create Date: 2026-09-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0053"
down_revision: str | None = "0052"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "stock_headlines",
        sa.Column("stock_key", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sentiment", sa.Text(), nullable=True),
        sa.Column("reason_zh", sa.Text(), nullable=True),
        sa.Column("reason_en", sa.Text(), nullable=True),
        sa.Column("classified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "sentiment in ('positive', 'neutral', 'negative')",
            name=op.f("ck_stock_headlines_sentiment"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stock_headlines")),
        sa.UniqueConstraint("stock_key", "url", name=op.f("uq_stock_headlines_stock_key_url")),
    )
    op.create_index(
        "ix_stock_headlines_stock_published", "stock_headlines", ["stock_key", "published_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_stock_headlines_stock_published", table_name="stock_headlines")
    op.drop_table("stock_headlines")
