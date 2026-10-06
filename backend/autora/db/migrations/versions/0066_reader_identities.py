"""reader_identities, oauth_states, auth_rate_limits, and a purpose for login_tokens (D-230)

Readers sign in with an address and a password, or with Google; the emailed sign-in link
(D-025) is retired as a way in. One person is still one ``readers`` row: the ways they prove who
they are become ``reader_identities`` — ``email`` (the address and, once set, an Argon2id hash)
and ``google`` (the account's ``sub``) — unique by ``(provider, subject)``.

Every reader already here gets an ``email`` identity for their own address and **no password**:
nobody's password is made up for them. They set one through the reset flow, which proves the
address again. Whether the address is already proven is read from the evidence, not guessed: a
sign-in link of theirs that was redeemed (``login_tokens.used_at``, set only when a link sent to
the address was opened and exchanged for a session) — verified from the first such time. An
address that only ever asked for a link starts unverified. Readers, sessions and watchlists are
left exactly as they are, so nobody is signed out by this migration.

``login_tokens`` stay — with their rows — and get a ``purpose``: the old links are ``login``;
new tokens check an address (``email_verify``) or set a password (``password_reset``).
``oauth_states`` holds a Google sign-in in flight; ``auth_rate_limits`` counts tries per window.

Revision ID: 0066
Revises: 0065
Create Date: 2026-10-06 14:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0066"
down_revision: str | None = "0065"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reader_identities",
        sa.Column("reader_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
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
        sa.CheckConstraint(
            "provider <> 'email' OR subject = email",
            name=op.f("ck_reader_identities_email_subject_is_email"),
        ),
        sa.CheckConstraint(
            "provider = 'email' OR password_hash IS NULL",
            name=op.f("ck_reader_identities_only_email_has_a_password"),
        ),
        sa.CheckConstraint(
            "provider IN ('email', 'google')", name=op.f("ck_reader_identities_provider_valid")
        ),
        sa.CheckConstraint(
            "email = lower(email)", name=op.f("ck_reader_identities_email_is_lowercase")
        ),
        sa.ForeignKeyConstraint(
            ["reader_id"], ["readers.id"], name=op.f("fk_reader_identities_reader_id_readers")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reader_identities")),
        sa.UniqueConstraint(
            "provider", "subject", name=op.f("uq_reader_identities_provider_subject")
        ),
        sa.UniqueConstraint(
            "reader_id", "provider", name=op.f("uq_reader_identities_reader_id_provider")
        ),
    )
    op.create_index(
        op.f("ix_reader_identities_reader_id"), "reader_identities", ["reader_id"], unique=False
    )
    # every reader keeps signing in as the same row: an address identity, no password, verified
    # from the first sign-in link of theirs that was redeemed — a link sent to the address and
    # opened — and unverified when none was
    op.execute(
        """
        INSERT INTO reader_identities
            (id, reader_id, provider, subject, email, password_hash, verified_at)
        SELECT gen_random_uuid(), r.id, 'email', r.email, r.email, NULL,
               (SELECT min(t.used_at) FROM login_tokens t
                 WHERE t.reader_id = r.id AND t.used_at IS NOT NULL)
        FROM readers r
        """
    )

    op.add_column(
        "login_tokens",
        sa.Column("purpose", sa.Text(), server_default="login", nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_login_tokens_purpose_valid"),
        "login_tokens",
        "purpose IN ('login', 'password_reset', 'email_verify')",
    )

    op.create_table(
        "oauth_states",
        sa.Column("state_hash", sa.Text(), nullable=False),
        sa.Column("browser_hash", sa.Text(), nullable=False),
        sa.Column("code_verifier", sa.Text(), nullable=False),
        sa.Column("nonce", sa.Text(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("lang", sa.Text(), nullable=False),
        sa.Column("next_path", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "purpose IN ('reader', 'admin')", name=op.f("ck_oauth_states_purpose_valid")
        ),
        sa.CheckConstraint(
            "expires_at > created_at", name=op.f("ck_oauth_states_expires_after_created")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_oauth_states")),
        sa.UniqueConstraint("state_hash", name=op.f("uq_oauth_states_state_hash")),
    )
    op.create_table(
        "auth_rate_limits",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_auth_rate_limits")),
    )


def downgrade() -> None:
    # only what this migration added: readers, sessions and the old tokens' rows stay
    op.drop_table("auth_rate_limits")
    op.drop_table("oauth_states")
    op.drop_constraint(op.f("ck_login_tokens_purpose_valid"), "login_tokens", type_="check")
    op.drop_column("login_tokens", "purpose")
    op.drop_index(op.f("ix_reader_identities_reader_id"), table_name="reader_identities")
    op.drop_table("reader_identities")
