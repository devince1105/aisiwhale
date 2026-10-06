"""D-230: signing in with Google — the ID token is checked for real, and who it signs in as.

The token is believed only once it is proven: Google's key, Google's issuer, this app's client
id, not expired, this attempt's nonce. Then the binding rules: a known ``sub`` is that reader;
an unverified Google address is refused; an address nobody has is a new reader; an address a
reader has is linked only when that reader's address is proven. Nothing else — no name, no
domain, no near match — ever decides who somebody is.
"""

import time
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from autora.accounts import credentials, google, models
from autora.accounts.google import GoogleAccount, GoogleError, SignInRefused
from autora.accounts.models import OAuthPurpose, Provider
from tests.accounts.google_double import CLIENT_ID, FakeGoogle, query_of

NOW = datetime(2026, 10, 6, 9, 0, tzinfo=UTC)
NONCE = "the-nonce-of-this-sign-in"


def _address() -> str:
    return f"g-{uuid.uuid4().hex[:8]}@gmail.com"


def _sub() -> str:
    return str(uuid.uuid4().int)[:21]


@pytest.fixture
def fake():
    return FakeGoogle()


# --- the ID token ---


async def test_a_good_token_says_who_it_is(fake):
    token = fake.id_token(sub="42", email="Someone@Gmail.com", nonce=NONCE)
    account = await fake.client().verify(token, nonce=NONCE)
    assert account == GoogleAccount(sub="42", email="someone@gmail.com", email_verified=True)


async def test_the_short_issuer_is_google_too(fake):
    token = fake.id_token(iss="accounts.google.com", nonce=NONCE)
    assert (await fake.client().verify(token, nonce=NONCE)).sub == "1000"


@pytest.mark.parametrize(
    ("change", "why"),
    [
        ({"iss": "https://evil.example.com"}, "another issuer"),
        ({"aud": "someone-elses-client"}, "made for another app"),
        ({"exp": int(time.time()) - 3600, "iat": int(time.time()) - 7200}, "expired"),
        ({"nonce": "another-attempt"}, "made for another sign-in"),
        ({"email": None}, "no address"),
        ({"sub": None}, "nobody"),
    ],
)
async def test_a_token_that_does_not_check_out_is_refused(fake, change, why):
    token = fake.id_token(**{"nonce": NONCE, **change})
    with pytest.raises(GoogleError):
        await fake.client().verify(token, nonce=NONCE)


async def test_a_token_signed_by_another_key_is_refused(fake):
    impostor = FakeGoogle()
    token = impostor.id_token(nonce=NONCE)  # same kid, different key
    with pytest.raises(GoogleError):
        await fake.client().verify(token, nonce=NONCE)


async def test_a_token_with_a_key_google_does_not_publish_is_refused(fake):
    token = fake.id_token(kid="unknown-key", nonce=NONCE)
    with pytest.raises(GoogleError, match="does not publish"):
        await fake.client().verify(token, nonce=NONCE)


async def test_a_token_not_signed_the_way_google_signs_is_refused(fake):
    token = fake.id_token(alg="HS256", nonce=NONCE)
    with pytest.raises(GoogleError):
        await fake.client().verify(token, nonce=NONCE)


async def test_rubbish_is_not_a_token(fake):
    with pytest.raises(GoogleError):
        await fake.client().verify("not.a.token", nonce=NONCE)


async def test_a_code_google_will_not_exchange_is_refused(fake):
    fake.refuse_codes = True
    with pytest.raises(GoogleError):
        await fake.client().exchange("a-code", "a-verifier")


async def test_the_code_is_exchanged_with_the_pkce_verifier(fake):
    fake.give("a-code", nonce=NONCE)
    await fake.client().exchange("a-code", "the-verifier")
    (form,) = fake.exchanged
    assert form["code_verifier"] == "the-verifier"
    assert form["client_id"] == CLIENT_ID and form["grant_type"] == "authorization_code"


# --- a sign-in in flight ---


async def test_leaving_for_google_carries_state_nonce_and_a_pkce_challenge(db_session, fake):
    start = await google.begin(
        db_session, fake.client(), OAuthPurpose.READER, lang="zh-TW", next_path="/x", now=NOW
    )
    query = query_of(start.url)

    assert query["client_id"] == CLIENT_ID and query["response_type"] == "code"
    assert query["code_challenge_method"] == "S256" and query["code_challenge"]
    assert query["state"] and query["nonce"]
    row = await google.claim(db_session, query["state"], start.browser, now=NOW)
    assert row.nonce == query["nonce"] and row.next_path == "/x"
    assert row.state_hash != query["state"], "only the state's hash is kept"
    assert query["code_challenge"] == google._challenge(row.code_verifier)
    assert row.code_verifier not in start.url, "the verifier never leaves the server"


async def test_a_state_is_good_once_for_ten_minutes_in_one_browser(db_session, fake):
    async def started():
        start = await google.begin(
            db_session, fake.client(), OAuthPurpose.READER, lang="zh-TW", next_path=None, now=NOW
        )
        return query_of(start.url)["state"], start.browser

    state, browser = await started()
    await google.claim(db_session, state, browser, now=NOW)
    with pytest.raises(GoogleError, match="already used"):
        await google.claim(db_session, state, browser, now=NOW)

    state, browser = await started()
    with pytest.raises(GoogleError, match="expired"):
        await google.claim(db_session, state, browser, now=NOW + google.STATE_VALID_FOR)

    state, _ = await started()
    with pytest.raises(GoogleError, match="another browser"):
        await google.claim(db_session, state, "somebody-elses-browser", now=NOW)
    with pytest.raises(GoogleError, match="already used"):
        await google.claim(db_session, state, "anyone", now=NOW)

    with pytest.raises(GoogleError, match="without a state"):
        await google.claim(db_session, None, browser, now=NOW)
    with pytest.raises(GoogleError, match="unknown"):
        await google.claim(db_session, "made-up-state", browser, now=NOW)


# --- who it signs in as ---


async def _proven_reader(session, address):
    outcome = await credentials.register(session, address, "correct horse battery", now=NOW)
    await credentials.verify_email(session, outcome.verify_token, now=NOW)
    return outcome.reader


async def _google_identities(session, reader_id):
    return (
        await session.scalars(
            select(models.ReaderIdentity).where(
                models.ReaderIdentity.reader_id == reader_id,
                models.ReaderIdentity.provider == Provider.GOOGLE,
            )
        )
    ).all()


async def test_a_new_address_is_a_new_reader(db_session):
    account = GoogleAccount(sub=_sub(), email=_address(), email_verified=True)
    reader = await google.sign_in(db_session, account, now=NOW)

    assert reader.email == account.email
    (linked,) = await _google_identities(db_session, reader.id)
    assert (linked.subject, linked.verified_at) == (account.sub, NOW)
    assert await credentials.email_verified(db_session, reader), "Google vouched for it"
    assert await credentials.identity(db_session, reader.id, Provider.EMAIL) is None, (
        "no password is made up for them"
    )


async def test_a_known_google_account_is_the_same_reader_whatever_its_address_is_now(db_session):
    sub = _sub()
    first = await google.sign_in(
        db_session, GoogleAccount(sub=sub, email=_address(), email_verified=True), now=NOW
    )
    renamed = GoogleAccount(sub=sub, email=_address(), email_verified=True)
    again = await google.sign_in(db_session, renamed, now=NOW)

    assert again.id == first.id
    count = await db_session.scalar(select(func.count()).select_from(models.Reader))
    assert await google.sign_in(db_session, renamed, now=NOW)
    assert await db_session.scalar(select(func.count()).select_from(models.Reader)) == count


async def test_a_proven_address_is_linked_to_its_reader(db_session):
    address = _address()
    reader = await _proven_reader(db_session, address)

    signed_in = await google.sign_in(
        db_session, GoogleAccount(sub=_sub(), email=address, email_verified=True), now=NOW
    )

    assert signed_in.id == reader.id
    assert len(await _google_identities(db_session, reader.id)) == 1
    assert await credentials.authenticate(db_session, address, "correct horse battery"), (
        "and the password still works"
    )


async def test_an_unproven_address_is_not_linked_by_google(db_session):
    """Pre-hijacking: somebody registers another person's address and waits for them to arrive
    by Google. That reader is not handed to the Google account, and nothing of it is removed."""
    address = _address()
    squatter = await credentials.register(db_session, address, "the squatter's password", now=NOW)

    with pytest.raises(SignInRefused) as refused:
        await google.sign_in(
            db_session, GoogleAccount(sub=_sub(), email=address, email_verified=True), now=NOW
        )

    assert refused.value.reason == google.ADDRESS_NOT_PROVEN
    assert await _google_identities(db_session, squatter.reader.id) == []
    row = await credentials.identity(db_session, squatter.reader.id, Provider.EMAIL)
    assert row.password_hash is not None, "the existing credential is left alone"


async def test_after_proving_the_address_by_a_reset_google_links(db_session):
    """The way out for the owner: a reset proves the address, then Google links."""
    address = _address()
    await credentials.register(db_session, address, "the squatter's password", now=NOW)
    _, token = await credentials.request_reset(db_session, address, now=NOW)
    reader = await credentials.reset_password(db_session, token, "the owner's password", now=NOW)

    signed_in = await google.sign_in(
        db_session, GoogleAccount(sub=_sub(), email=address, email_verified=True), now=NOW
    )
    assert signed_in.id == reader.id
    assert await credentials.authenticate(db_session, address, "the squatter's password") is None


async def test_an_address_google_has_not_verified_is_refused(db_session):
    address = _address()
    reader = await _proven_reader(db_session, address)

    with pytest.raises(SignInRefused) as refused:
        await google.sign_in(
            db_session, GoogleAccount(sub=_sub(), email=address, email_verified=False), now=NOW
        )
    assert refused.value.reason == google.EMAIL_NOT_VERIFIED
    assert await _google_identities(db_session, reader.id) == []

    with pytest.raises(SignInRefused):  # and makes no reader either
        await google.sign_in(
            db_session, GoogleAccount(sub=_sub(), email=_address(), email_verified=False), now=NOW
        )


async def test_a_different_address_is_never_merged(db_session):
    """Same person, maybe; not the same address — so a reader of its own. No near matching."""
    existing = await _proven_reader(db_session, "first.last@example.com")
    for other in ("first.last@gmail.com", "firstlast@example.com", "first.last+x@example.com"):
        reader = await google.sign_in(
            db_session, GoogleAccount(sub=_sub(), email=other, email_verified=True), now=NOW
        )
        assert reader.id != existing.id


async def test_a_reader_links_one_google_account(db_session):
    address = _address()
    await _proven_reader(db_session, address)
    await google.sign_in(
        db_session, GoogleAccount(sub=_sub(), email=address, email_verified=True), now=NOW
    )

    with pytest.raises(SignInRefused) as refused:
        await google.sign_in(
            db_session, GoogleAccount(sub=_sub(), email=address, email_verified=True), now=NOW
        )
    assert refused.value.reason == google.ANOTHER_GOOGLE_LINKED


async def test_a_google_account_belongs_to_one_reader(db_session):
    """(provider, subject) is unique in the database itself, not only in the code."""
    from sqlalchemy.exc import IntegrityError

    sub = _sub()
    first = await google.sign_in(
        db_session, GoogleAccount(sub=sub, email=_address(), email_verified=True), now=NOW
    )
    other = models.Reader(email=_address())
    db_session.add(other)
    await db_session.flush()
    db_session.add(
        models.ReaderIdentity(reader_id=other.id, provider="google", subject=sub, email=other.email)
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()
    assert first.id != other.id


def test_a_state_and_nothing_else_is_remembered():
    """What an oauth_states row holds: hashes, the verifier and the nonce — no token, no code."""
    columns = set(models.OAuthState.__table__.columns.keys())
    assert "state" not in columns and "browser" not in columns
    assert {"state_hash", "browser_hash", "code_verifier", "nonce"} <= columns


async def test_only_the_reader_s_own_proven_address_identity_vouches(db_session):
    """A reader with no address identity of its own (nothing this site ever checked) is not
    linked either: Google's word alone never vouches for a reader that already exists."""
    bare = models.Reader(email=_address())
    db_session.add(bare)
    await db_session.flush()

    with pytest.raises(SignInRefused) as refused:
        await google.sign_in(
            db_session, GoogleAccount(sub=_sub(), email=bare.email, email_verified=True), now=NOW
        )
    assert refused.value.reason == google.ADDRESS_NOT_PROVEN
    assert await _google_identities(db_session, bare.id) == []
