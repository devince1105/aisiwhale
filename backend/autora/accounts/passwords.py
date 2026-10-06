"""Passwords: what a good enough one is, and how it is kept (D-230).

Only ever an Argon2id hash is stored — never the password, never anything it could be read back
from. Checking a password costs the same whether or not the address has one: an address that
does not exist is checked against a stand-in hash, so how long the answer takes does not say.

The rule for a new password is deliberately plain: 8 to 128 characters. Length is what makes a
password hard to guess; required digits and symbols mostly make people write them down.
"""

from __future__ import annotations

from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

MIN_LENGTH = 8
MAX_LENGTH = 128
"""Long enough for a passphrase; short enough that hashing one is not a way to tie up the API."""

_hasher = PasswordHasher()  # Argon2id, the library's current recommended cost


class PasswordError(Exception):
    pass


def check_new(password: str) -> str:
    """The password, if it may be set. Raises with what is wrong with it."""
    if len(password) < MIN_LENGTH:
        raise PasswordError(f"a password needs at least {MIN_LENGTH} characters")
    if len(password) > MAX_LENGTH:
        raise PasswordError(f"a password may have at most {MAX_LENGTH} characters")
    if not password.strip():
        raise PasswordError("a password cannot be only spaces")
    return password


def hash_password(password: str) -> str:
    return _hasher.hash(password)


@lru_cache(maxsize=1)
def _stand_in() -> str:
    """A hash nobody's password matches, checked when there is no real one to check."""
    return _hasher.hash("no account has this password")


def verify(password_hash: str | None, password: str) -> bool:
    """Whether this is the password. Takes as long with no hash as with one."""
    try:
        return _hasher.verify(password_hash or _stand_in(), password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """True when the hash was made at an older cost: rehash it while the password is at hand."""
    return _hasher.check_needs_rehash(password_hash)
