"""A stand-in for Google's side of OAuth, for tests only (D-230).

It signs ID tokens with an RSA key of its own and publishes that key the way Google publishes
its keys, so the real ``GoogleOAuth`` — the same code that runs in production — checks them for
real: signature, issuer, audience, expiry, nonce. Only the network is replaced (an
``httpx.MockTransport``); nothing here is reachable from the application's own code.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from autora.accounts.google import CERTS_URL, TOKEN_URL, GoogleOAuth

CLIENT_ID = "test-client.apps.googleusercontent.com"
CLIENT_SECRET = "test-client-secret"
REDIRECT_URI = "http://test/api/auth/google/callback"
KID = "test-key-1"


def _key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@dataclass
class FakeGoogle:
    """Google, as far as one test is concerned. ``accounts`` maps a code to the claims its ID
    token will carry; ``refuse_codes`` makes the token endpoint say no."""

    key: object = field(default_factory=_key)
    accounts: dict[str, dict] = field(default_factory=dict)
    refuse_codes: bool = False
    exchanged: list[dict] = field(default_factory=list)

    def jwks(self) -> dict:
        public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        return {"keys": [{**public, "kid": KID, "alg": "RS256", "use": "sig"}]}

    def id_token(self, *, key=None, kid: str = KID, alg: str = "RS256", **overrides) -> str:
        now = int(time.time())
        claims = {
            "iss": "https://accounts.google.com",
            "aud": CLIENT_ID,
            "sub": "1000",
            "email": "someone@gmail.com",
            "email_verified": True,
            "iat": now,
            "exp": now + 3600,
            "nonce": "",
        }
        claims.update(overrides)
        claims = {name: value for name, value in claims.items() if value is not None}
        signing = key or self.key
        if alg == "HS256":
            signing = "a shared secret nobody should accept"
        return jwt.encode(claims, signing, algorithm=alg, headers={"kid": kid})

    def give(self, code: str, **claims) -> None:
        """When this code comes back, answer with an ID token carrying these claims."""
        self.accounts[code] = claims

    async def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url).split("?")[0]
        if url == CERTS_URL:
            return httpx.Response(200, json=self.jwks())
        if url == TOKEN_URL:
            form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
            self.exchanged.append(form)
            if self.refuse_codes or form.get("code") not in self.accounts:
                return httpx.Response(400, json={"error": "invalid_grant"})
            claims = dict(self.accounts[form["code"]])
            token = claims.pop("raw_token", None) or self.id_token(**claims)
            return httpx.Response(200, json={"id_token": token, "access_token": "unused"})
        return httpx.Response(404)

    def client(self) -> GoogleOAuth:
        http = httpx.AsyncClient(transport=httpx.MockTransport(self.handler))
        return GoogleOAuth(CLIENT_ID, CLIENT_SECRET, REDIRECT_URI, http=http)


def query_of(location: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlparse(location).query).items()}
