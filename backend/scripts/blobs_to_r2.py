"""Copy the local blob directory into the private R2 bucket (D-153), for the move to production.

    .venv/bin/python backend/scripts/blobs_to_r2.py --bucket aisiwhale-private          # copy
    .venv/bin/python backend/scripts/blobs_to_r2.py --bucket aisiwhale-private --check  # count

Every file under BLOB_STORE_DIR (agent traces, evidence snapshots; covers are already in their
own bucket) is put under the same key. One already there is skipped, so a second run picks up
where a first one stopped. Uses R2_ACCOUNT_ID and its keys from .env; the bucket must be private.
"""

import argparse
import asyncio
import sys
from pathlib import Path

from autora.infra.blobstore import R2BlobStore
from autora.infra.s3 import R2Bucket
from autora.infra.settings import load_settings

PARALLEL = 8


async def run(bucket: str, check: bool) -> None:
    settings = load_settings()
    if not (settings.r2_account_id and settings.r2_access_key_id and settings.r2_secret_access_key):
        sys.exit("R2_ACCOUNT_ID, R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY are needed")
    store = R2BlobStore(
        R2Bucket(
            account_id=settings.r2_account_id,
            access_key_id=settings.r2_access_key_id.get_secret_value(),
            secret_access_key=settings.r2_secret_access_key.get_secret_value(),
            bucket=bucket,
        )
    )
    root = Path(settings.blob_store_dir).resolve()
    files = [p for p in root.rglob("*") if p.is_file() and not p.name.startswith(".")]
    # covers have their own (public) bucket; only a dev fallback kept them here
    files = [p for p in files if not p.relative_to(root).as_posix().startswith("covers/")]
    counts = {"copied": 0, "there": 0, "failed": 0}
    gate = asyncio.Semaphore(PARALLEL)

    async def one(path: Path) -> None:
        key = path.relative_to(root).as_posix()
        async with gate:
            try:
                if await store.exists(key):
                    counts["there"] += 1
                elif check:
                    counts["failed"] += 1  # missing
                else:
                    await store.put(key, path.read_bytes())
                    counts["copied"] += 1
            except Exception as exc:  # noqa: BLE001 - count it, carry on; a rerun retries it
                counts["failed"] += 1
                print(f"  {key}: {exc}")

    await asyncio.gather(*(one(p) for p in files))
    label = "missing" if check else "failed"
    print(
        f"{len(files)} files: {counts['copied']} copied, {counts['there']} already there, "
        f"{counts['failed']} {label}"
    )
    if counts["failed"]:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bucket", required=True, help="the PRIVATE bucket (BLOB_R2_BUCKET)")
    parser.add_argument("--check", action="store_true", help="only count what is not there yet")
    args = parser.parse_args()
    asyncio.run(run(args.bucket, args.check))


if __name__ == "__main__":
    main()
