"""D-230: an address and a password, the tokens emailed about them, and sessions.

The reader tables are the only place a person's address exists, so much of what matters here is
what is *not* stored — no password, no token, no session in a form that could be used — and
that every emailed token works once, for its own purpose, for a while.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import inspect, select

from autora.accounts import credentials, models, passwords, service
from autora.accounts.models import Provider, TokenPurpose
from autora.accounts.passwords import PasswordError
from autora.accounts.service import AccountError

NOW = datetime(2026, 10, 6, 9, 0, tzinfo=UTC)
PASSWORD = "correct horse battery"


def _address() -> str:
    """An address of this test's own: readers are shared by every company, and tests that
    commit (the acceptance tests) leave theirs in the database for the rest of the run."""
    return f"reader-{uuid.uuid4().hex[:8]}@example.com"


async def _register(session, email=None, password=PASSWORD, *, now=NOW):
    return await credentials.register(session, email or _address(), password, now=now)


async def _email_identity(session, reader_id):
    return await credentials.identity(session, reader_id, Provider.EMAIL)


async def _session_for(session, reader, *, now=NOW):
    return await service.start_session(session, reader, now=now)


# --- what is kept ---


def test_a_reader_is_an_address_and_when_they_were_last_here():
    columns = {column.name for column in inspect(models.Reader).columns}
    # and when their watchlist began (D-062): not who they are, not how they sign in
    assert columns == {
        "id", "email", "last_seen_at", "watchlist_started_at", "created_at", "updated_at",
    }  # fmt: skip


def test_a_password_is_kept_only_as_a_hash():
    columns = {column.name for column in inspect(models.ReaderIdentity).columns}
    assert "password_hash" in columns and "password" not in columns


async def test_registering_keeps_an_argon2id_hash_never_the_password(db_session):
    outcome = await _register(db_session)
    row = await _email_identity(db_session, outcome.reader.id)

    assert row.password_hash.startswith("$argon2id$")
    assert PASSWORD not in row.password_hash
    assert passwords.verify(row.password_hash, PASSWORD)
    assert not passwords.verify(row.password_hash, PASSWORD + "!")


def test_two_hashes_of_one_password_differ():
    """Salted: the same password is not recognisable across readers."""
    assert passwords.hash_password(PASSWORD) != passwords.hash_password(PASSWORD)


@pytest.mark.parametrize("password", ["short", " " * 10, "x" * 129])
def test_what_is_not_a_password(password):
    with pytest.raises(PasswordError):
        passwords.check_new(password)


def test_a_plain_long_password_is_enough():
    """No arbitrary rules about digits and symbols: length is what counts."""
    assert passwords.check_new("eight ch") == "eight ch"


# --- registering ---


async def test_registering_makes_a_reader_with_an_unproven_address(db_session):
    outcome = await _register(db_session)
    row = await _email_identity(db_session, outcome.reader.id)

    assert outcome.verify_token is not None
    assert row.subject == row.email == outcome.reader.email
    assert row.verified_at is None
    assert not await credentials.email_verified(db_session, outcome.reader)


async def test_an_address_is_one_reader_however_it_is_typed(db_session):
    first = await _register(db_session, "Reader.Case@Example.COM ")
    again = await _register(db_session, "reader.case@example.com", "another password")

    assert first.reader.email == "reader.case@example.com"
    assert again.reader.id == first.reader.id
    assert again.verify_token is None, "the second time makes nothing"
    row = await _email_identity(db_session, first.reader.id)
    assert passwords.verify(row.password_hash, PASSWORD), "and changes nothing either"


async def test_dots_and_tags_are_not_rewritten(db_session):
    """Different addresses are different people: only case and spaces are normalised."""
    plain = await _register(db_session, "first.last@example.com")
    tagged = await _register(db_session, "first.last+news@example.com")
    dotless = await _register(db_session, "firstlast@example.com")
    assert len({plain.reader.id, tagged.reader.id, dotless.reader.id}) == 3


async def test_registering_an_address_with_no_password_does_not_set_one(db_session):
    """An existing reader (one who came by the old links) gets no password from a stranger."""
    reader = models.Reader(email=_address())
    db_session.add(reader)
    await db_session.flush()

    outcome = await _register(db_session, reader.email)

    assert outcome.verify_token is None
    assert await credentials.authenticate(db_session, reader.email, PASSWORD) is None


@pytest.mark.parametrize("address", ["", "nobody", "no body@example.com", "a@b"])
async def test_what_is_not_an_address(db_session, address):
    with pytest.raises(AccountError):
        await credentials.register(db_session, address, PASSWORD)


# --- signing in ---


async def test_the_right_password_signs_in(db_session):
    outcome = await _register(db_session)
    reader = await credentials.authenticate(db_session, outcome.reader.email.upper(), PASSWORD)
    assert reader is not None and reader.id == outcome.reader.id


async def test_a_wrong_password_an_unknown_address_and_no_password_all_fail_alike(db_session):
    outcome = await _register(db_session)
    no_password = models.Reader(email=_address())
    db_session.add(no_password)
    await db_session.flush()

    assert (
        await credentials.authenticate(db_session, outcome.reader.email, "wrong password") is None
    )
    assert await credentials.authenticate(db_session, _address(), PASSWORD) is None
    assert await credentials.authenticate(db_session, no_password.email, PASSWORD) is None
    assert await credentials.authenticate(db_session, "not an address", PASSWORD) is None


# --- proving the address ---


async def test_the_link_proves_the_address_once(db_session):
    outcome = await _register(db_session)
    later = NOW + timedelta(hours=1)

    reader = await credentials.verify_email(db_session, outcome.verify_token, now=later)

    assert reader.id == outcome.reader.id
    assert (await _email_identity(db_session, reader.id)).verified_at == later
    assert await credentials.email_verified(db_session, reader)
    with pytest.raises(AccountError, match="no longer works"):
        await credentials.verify_email(db_session, outcome.verify_token, now=later)


async def test_a_verify_link_that_waited_too_long_is_no_good(db_session):
    outcome = await _register(db_session)
    with pytest.raises(AccountError, match="no longer works"):
        await credentials.verify_email(
            db_session, outcome.verify_token, now=NOW + credentials.VERIFY_VALID_FOR
        )


async def test_a_new_verify_link_only_while_there_is_something_to_prove(db_session):
    outcome = await _register(db_session)
    assert await credentials.request_verification(db_session, outcome.reader, now=NOW)
    await credentials.verify_email(db_session, outcome.verify_token, now=NOW)
    assert await credentials.request_verification(db_session, outcome.reader, now=NOW) is None


# --- resetting ---


async def test_a_reset_sets_the_password_proves_the_address_and_signs_out_everywhere(db_session):
    outcome = await _register(db_session)
    elsewhere = await _session_for(db_session, outcome.reader)
    _, token = await credentials.request_reset(db_session, outcome.reader.email, now=NOW)

    later = NOW + timedelta(minutes=5)
    await credentials.reset_password(db_session, token, "a brand new password", now=later)

    assert await credentials.authenticate(db_session, outcome.reader.email, PASSWORD) is None
    assert await credentials.authenticate(db_session, outcome.reader.email, "a brand new password")
    assert (await _email_identity(db_session, outcome.reader.id)).verified_at == later
    assert await service.reader_for(db_session, elsewhere, now=later) is None


async def test_a_reset_link_works_once_and_retires_the_others(db_session):
    outcome = await _register(db_session)
    _, first = await credentials.request_reset(db_session, outcome.reader.email, now=NOW)
    _, second = await credentials.request_reset(db_session, outcome.reader.email, now=NOW)

    await credentials.reset_password(db_session, second, "a brand new password", now=NOW)

    for used in (first, second):
        with pytest.raises(AccountError, match="no longer works"):
            await credentials.reset_password(db_session, used, "yet another password", now=NOW)


async def test_a_reset_link_that_waited_too_long_is_no_good(db_session):
    outcome = await _register(db_session)
    _, token = await credentials.request_reset(db_session, outcome.reader.email, now=NOW)
    with pytest.raises(AccountError, match="no longer works"):
        await credentials.reset_password(
            db_session, token, "a brand new password", now=NOW + credentials.RESET_VALID_FOR
        )


async def test_a_bad_new_password_does_not_spend_the_link(db_session):
    outcome = await _register(db_session)
    _, token = await credentials.request_reset(db_session, outcome.reader.email, now=NOW)
    with pytest.raises(PasswordError):
        await credentials.reset_password(db_session, token, "short", now=NOW)
    await credentials.reset_password(db_session, token, "a brand new password", now=NOW)


async def test_a_reset_for_an_address_nobody_has_is_nothing(db_session):
    assert await credentials.request_reset(db_session, _address(), now=NOW) is None
    assert await credentials.request_reset(db_session, "not an address", now=NOW) is None


async def test_a_reader_without_a_password_sets_one_by_resetting(db_session):
    """Readers from the old sign-in links (and from Google) have none: this is how they get one."""
    reader = models.Reader(email=_address(), last_seen_at=NOW)
    db_session.add(reader)
    await db_session.flush()

    _, token = await credentials.request_reset(db_session, reader.email, now=NOW)
    await credentials.reset_password(db_session, token, "my first password", now=NOW)

    assert (await credentials.authenticate(db_session, reader.email, "my first password")).id == (
        reader.id
    )


async def test_a_token_only_does_what_it_was_made_for(db_session):
    """A link to prove an address cannot set a password, nor the other way round."""
    outcome = await _register(db_session)
    _, reset = await credentials.request_reset(db_session, outcome.reader.email, now=NOW)

    with pytest.raises(AccountError):
        await credentials.reset_password(db_session, outcome.verify_token, "new password!", now=NOW)
    with pytest.raises(AccountError):
        await credentials.verify_email(db_session, reset, now=NOW)


async def test_only_a_token_s_hash_is_stored(db_session):
    outcome = await _register(db_session)
    rows = (
        await db_session.scalars(
            select(models.LoginToken).where(models.LoginToken.reader_id == outcome.reader.id)
        )
    ).all()
    assert [row.purpose for row in rows] == [TokenPurpose.EMAIL_VERIFY]
    assert rows[0].token_hash == service.hash_token(outcome.verify_token) != outcome.verify_token


async def test_a_token_nobody_issued_is_no_good(db_session):
    with pytest.raises(AccountError, match="no longer works"):
        await credentials.verify_email(db_session, "made-up-token", now=NOW)


# --- sessions ---


async def test_only_the_session_s_hash_is_stored(db_session):
    outcome = await _register(db_session)
    token = await _session_for(db_session, outcome.reader)
    row = await db_session.scalar(
        select(models.ReaderSession).where(models.ReaderSession.reader_id == outcome.reader.id)
    )
    assert row.token_hash == service.hash_token(token) != token


async def test_a_session_ends_when_it_expires_or_when_they_sign_out(db_session):
    outcome = await _register(db_session)
    token = await _session_for(db_session, outcome.reader)

    stale = NOW + service.SESSION_VALID_FOR
    assert await service.reader_for(db_session, token, now=stale) is None

    assert await service.sign_out(db_session, token, now=NOW + timedelta(days=1))
    assert await service.reader_for(db_session, token, now=NOW + timedelta(days=2)) is None
    assert not await service.sign_out(db_session, token), "signing out twice changes nothing"


async def test_no_cookie_is_nobody(db_session):
    assert await service.reader_for(db_session, None) is None
    assert await service.reader_for(db_session, "") is None
    assert not await service.sign_out(db_session, None)


async def test_the_company_knows_a_reader_by_reference_never_by_address(db_session):
    outcome = await _register(db_session)
    ref = service.customer_ref(outcome.reader.id)
    assert ref == f"reader:{outcome.reader.id}"
    assert "@" not in ref


async def test_a_token_and_a_session_keep_one_clock(db_session):
    """Whatever time the caller says it is, the row agrees with itself.

    The tables check ``expires_at > created_at``. When ``created_at`` came from the database's
    own clock and ``expires_at`` from the caller's, every test with a fixed time broke once
    that time had passed. A time years ago must work as well as now does.
    """
    long_ago = datetime(2020, 1, 1, tzinfo=UTC)
    outcome = await _register(db_session, now=long_ago)
    token_row = await db_session.scalar(
        select(models.LoginToken).where(models.LoginToken.reader_id == outcome.reader.id)
    )
    assert token_row.created_at == long_ago
    assert token_row.expires_at == long_ago + credentials.VERIFY_VALID_FOR
    await _session_for(db_session, outcome.reader, now=long_ago)
