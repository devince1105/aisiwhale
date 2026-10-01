"""S3's API as Cloudflare R2 speaks it (D-142, D-153): Signature V4 and the four calls the
company needs — put, get, head, delete one object. No SDK: four signed requests do not need one.

Used by the articles' covers (a public bucket, read through its public address) and by the blob
store in production (a private bucket: agent traces and evidence snapshots, which only the API
and the worker read, signed).
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime
from urllib.parse import quote

import httpx

EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


class S3Error(Exception):
    """The bucket answered with an error, or could not be reached. The message never carries a
    signature or a key."""

    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


def sigv4_headers(
    *,
    method: str,
    host: str,
    path: str,
    headers: dict[str, str],
    payload_hash: str,
    access_key: str,
    secret_key: str,
    region: str,
    service: str = "s3",
    now: datetime | None = None,
) -> dict[str, str]:
    """AWS Signature Version 4 for a request without a query string: the headers to send."""
    now = now or datetime.now(UTC)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    day = amz_date[:8]
    signed = {k.lower(): " ".join(v.split()) for k, v in headers.items()}
    signed |= {"host": host, "x-amz-date": amz_date, "x-amz-content-sha256": payload_hash}
    names = sorted(signed)
    canonical = "\n".join(
        [
            method,
            quote(path, safe="/-_.~"),
            "",
            "".join(f"{n}:{signed[n]}\n" for n in names),
            ";".join(names),
            payload_hash,
        ]
    )
    scope = f"{day}/{region}/{service}/aws4_request"
    to_sign = "\n".join(
        ["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()]
    )
    key = f"AWS4{secret_key}".encode()
    for part in (day, region, service, "aws4_request"):
        key = hmac.new(key, part.encode(), hashlib.sha256).digest()
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    return {k: v for k, v in signed.items() if k != "host"} | {
        "authorization": (
            f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
            f"SignedHeaders={';'.join(names)}, Signature={signature}"
        )
    }


class R2Bucket:
    """One bucket of an R2 account, under an optional prefix (a folder)."""

    def __init__(
        self,
        *,
        account_id: str,
        access_key_id: str,
        secret_access_key: str,
        bucket: str,
        prefix: str = "",
        client: httpx.AsyncClient | None = None,
    ):
        self.host = f"{account_id}.r2.cloudflarestorage.com"
        self._access = access_key_id
        self._secret = secret_access_key
        self.bucket = bucket
        self.prefix = f"{prefix.strip('/')}/" if prefix.strip("/") else ""
        self._client = client

    def path(self, key: str) -> str:
        return f"/{self.bucket}/{self.prefix}{key}"

    async def request(
        self, method: str, key: str, data: bytes = b"", headers: dict[str, str] | None = None
    ) -> httpx.Response:
        path = self.path(key)
        signed = sigv4_headers(
            method=method,
            host=self.host,
            path=path,
            headers=headers or {},
            payload_hash=hashlib.sha256(data).hexdigest() if data else EMPTY_SHA256,
            access_key=self._access,
            secret_key=self._secret,
            region="auto",
        )
        url = f"https://{self.host}{quote(path, safe='/-_.~')}"
        try:
            if self._client is not None:
                return await self._client.request(method, url, content=data, headers=signed)
            async with httpx.AsyncClient() as client:
                return await client.request(method, url, content=data, headers=signed, timeout=60.0)
        except httpx.HTTPError as exc:
            raise S3Error(f"r2: {type(exc).__name__}", retryable=True) from None

    async def put(self, key: str, data: bytes, headers: dict[str, str] | None = None) -> None:
        response = await self.request("PUT", key, data, headers)
        if response.status_code not in (200, 201, 204):
            raise S3Error(f"r2 answered {response.status_code} to PUT")

    async def get(self, key: str) -> bytes | None:
        """The object, or None when there is none."""
        response = await self.request("GET", key)
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise S3Error(f"r2 answered {response.status_code} to GET", retryable=True)
        return response.content

    async def exists(self, key: str) -> bool:
        response = await self.request("HEAD", key)
        if response.status_code in (200, 404):
            return response.status_code == 200
        raise S3Error(f"r2 answered {response.status_code} to HEAD", retryable=True)

    async def delete(self, key: str) -> None:
        response = await self.request("DELETE", key)
        if response.status_code not in (200, 204, 404):
            raise S3Error(f"r2 answered {response.status_code} to DELETE")
