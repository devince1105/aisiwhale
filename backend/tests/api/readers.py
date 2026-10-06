"""Signing a reader in the way a browser does (D-230): register, then sign in with the password.

For the tests whose subject is something else — a paywall, a watchlist, a checkout — and only
need somebody signed in. The sign-in itself is tested in ``test_auth_api``.
"""

import re
import uuid

PASSWORD = "correct horse battery"


async def sign_in(client, address: str, password: str = PASSWORD, *, company: str | None = None):
    """Register ``address`` (new, or left as it was) and sign in. Returns the sign-in response."""
    registered = await client.post(
        "/api/auth/register", json={"email": address, "password": password}
    )
    assert registered.status_code == 202, registered.text
    params = {"company": company} if company else None
    answer = await client.post(
        "/api/auth/login", json={"email": address, "password": password}, params=params
    )
    assert answer.status_code == 200, answer.text
    return answer


async def sign_in_id(client, address: str, password: str = PASSWORD) -> uuid.UUID:
    return uuid.UUID((await sign_in(client, address, password)).json()["reader_id"])


def token_in(message) -> str:
    """The token in an emailed link."""
    match = re.search(r"token=([A-Za-z0-9_\-]+)", message.text)
    assert match, message.text
    return match.group(1)
