"""Draw the brands' logos and keep them where the cover tool finds them (D-150).

    .venv/bin/python backend/scripts/brand_logos.py            # draw and upload what is missing
    .venv/bin/python backend/scripts/brand_logos.py --force    # draw and upload all again

For every brand in ``brands.BRANDS`` that Simple Icons carries: its SVG (a pinned release, CC0),
in the brand's colour (black when the colour is too light to see), drawn to a 1024-pixel PNG on a
transparent ground with sharp (the web app's image library), and put in the cover store as
``brand/<slug>.png``. The brands without one are listed: their official PNG is a person's to add
under the same key.
"""

import argparse
import asyncio
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx

from autora.app import build_cover_store
from autora.domains.newsroom.brands import BRANDS, logo_key
from autora.infra.blobstore import LocalFSBlobStore
from autora.infra.settings import load_settings

ROOT = Path(__file__).resolve().parents[2]
RELEASE = "16.33.0"
ICONS = f"https://cdn.jsdelivr.net/npm/simple-icons@{RELEASE}"
SIZE = 1024

RENDER = """
const fs = require('fs');
const sharp = require(process.argv[2]);
const jobs = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
(async () => {
  for (const job of jobs) {
    await sharp(Buffer.from(job.svg), { density: 2400 })
      .resize(job.size - 2 * job.pad, job.size - 2 * job.pad, {
        fit: 'contain', background: { r: 0, g: 0, b: 0, alpha: 0 } })
      .extend({ top: job.pad, bottom: job.pad, left: job.pad, right: job.pad,
        background: { r: 0, g: 0, b: 0, alpha: 0 } })
      .png().toFile(job.out);
  }
})().catch((e) => { console.error(e); process.exit(1); });
"""


def _sharp() -> str:
    found = sorted((ROOT / "node_modules" / ".pnpm").glob("sharp@*/node_modules/sharp"))
    if not found:
        sys.exit("sharp is not installed (pnpm install at the repository root)")
    return str(found[-1])


def _colour(hex_: str) -> str:
    r, g, b = (int(hex_[i : i + 2], 16) for i in (0, 2, 4))
    # too light to see on a light reference (Sony's white): draw it black
    return "#000000" if 0.2126 * r + 0.7152 * g + 0.0722 * b > 225 else f"#{hex_}"


async def run(force: bool) -> None:
    settings = load_settings()
    store = build_cover_store(settings, LocalFSBlobStore(settings.blob_store_dir))
    colours = {i["slug"]: i["hex"] for i in httpx.get(f"{ICONS}/data/simple-icons.json").json()}
    wanted = [b for b in BRANDS if b.simple_icons]
    missing = [b for b in BRANDS if not b.simple_icons]
    with tempfile.TemporaryDirectory() as tmp, httpx.Client(timeout=30) as client:
        jobs = []
        for brand in wanted:
            if not force and await store.exists(logo_key(brand.slug)):
                continue
            svg = client.get(f"{ICONS}/icons/{brand.simple_icons}.svg").text
            fill = _colour(colours[brand.simple_icons])
            svg = svg.replace("<svg ", f'<svg fill="{fill}" ', 1)
            jobs.append(
                {"svg": svg, "out": f"{tmp}/{brand.slug}.png", "size": SIZE, "pad": SIZE // 10}
            )
        if jobs:
            Path(tmp, "jobs.json").write_text(json.dumps(jobs))
            Path(tmp, "render.js").write_text(RENDER)
            subprocess.run(
                ["node", f"{tmp}/render.js", _sharp(), f"{tmp}/jobs.json"], check=True, cwd=ROOT
            )
            for job in jobs:
                slug = Path(job["out"]).stem
                url = await store.put(logo_key(slug), Path(job["out"]).read_bytes(), "image/png")
                print(f"  {slug:<16} {url}")
    print(f"{len(jobs)} drawn and kept, {len(wanted) - len(jobs)} already there")
    if missing:
        print("no Simple Icons logo — add the official PNG as brand/<slug>.png:")
        for brand in missing:
            print(f"  {brand.slug:<12} {brand.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true")
    asyncio.run(run(parser.parse_args().force))


if __name__ == "__main__":
    main()
