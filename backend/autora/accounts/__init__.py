"""Readers: who signs in to read, and nothing else about them (D-024, D-025, D-230).

This package is the only holder of a person's identity in Autora. Nothing below it may import
it — ``.importlinter`` has a contract that says so — so no agent, no domain and no part of the
company layer can read an address. The company's side of a reader is a customer whose
``external_ref`` is ``reader:<id>``.

A reader signs in with an address and a password (``credentials``) or with Google
(``google``); either way they are one ``readers`` row with a session cookie (``service``).
"""

from autora.accounts.credentials import (
    Registration,
    authenticate,
    email_verified,
    register,
    request_reset,
    request_verification,
    reset_password,
    verify_email,
)
from autora.accounts.models import (
    AuthRateLimit,
    LoginToken,
    OAuthPurpose,
    OAuthState,
    Provider,
    Reader,
    ReaderIdentity,
    ReaderSession,
    TokenPurpose,
    WatchlistItem,
)
from autora.accounts.passwords import PasswordError
from autora.accounts.service import (
    SESSION_COOKIE,
    AccountError,
    by_email,
    customer_ref,
    normalise,
    reader_for,
    sign_out,
    start_session,
)

__all__ = [
    "SESSION_COOKIE",
    "AccountError",
    "AuthRateLimit",
    "LoginToken",
    "OAuthPurpose",
    "OAuthState",
    "PasswordError",
    "Provider",
    "Reader",
    "ReaderIdentity",
    "ReaderSession",
    "Registration",
    "TokenPurpose",
    "WatchlistItem",
    "authenticate",
    "by_email",
    "customer_ref",
    "email_verified",
    "normalise",
    "reader_for",
    "register",
    "request_reset",
    "request_verification",
    "reset_password",
    "sign_out",
    "start_session",
    "verify_email",
]
