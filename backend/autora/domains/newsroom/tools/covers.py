"""``search_images`` and ``set_cover`` (D-142): marketing picks an article's cover.

``search_images`` asks the photo library (read; nothing is kept). ``set_cover`` takes one of the
photos that search returned — by its id, from the same query — downloads it, cuts it to 1200x630
WebP, stores it and makes it the story's cover, keeping the rest of the results for a person to
swap to. Without a library (no ``PIXABAY_API_KEY``) both say so, and the story has no cover.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field
from sqlalchemy import select

from autora.domains.newsroom import brands, covers
from autora.domains.newsroom.models import Claim, Story
from autora.runtime.events.catalog import ProducedRef
from autora.runtime.tools import ToolContext, ToolFn, ToolRegistry, ToolResult

NO_LIBRARY = "no photo library is set up (PIXABAY_API_KEY): report that the story has no cover"


class SearchImagesArgs(BaseModel):
    query: str = Field(
        min_length=2,
        max_length=100,
        description="Two to four plain English words for what the photo should show, e.g. "
        "'processor chip' or 'stock market chart'.",
    )


class SetCoverArgs(BaseModel):
    story_id: uuid.UUID
    query: str = Field(min_length=2, max_length=100, description="The query that found it.")
    photo_id: str = Field(min_length=1, max_length=40, description="From search_images.")
    alt_zh: str = Field(
        min_length=2, max_length=120, description="What the photo shows, in Traditional Chinese."
    )
    alt_en: str = Field(min_length=2, max_length=160, description="What it shows, in English.")


LOOKED_AT = 8
"""How many of a search's results the viewer looks at (D-144): the ones marketing reads first."""


def search_images_tool(
    library: covers.ImageLibrary | None, viewer: covers.ImageViewer | covers.FixtureViewer | None
) -> ToolFn:
    async def search_images(args: SearchImagesArgs, ctx: ToolContext) -> ToolResult:
        if library is None:
            raise covers.CoverError(NO_LIBRARY)
        photos = await library.search(args.query, limit=LOOKED_AT)
        looks, cost = await viewer.look(library, photos) if viewer else ({}, None)
        taken = await covers.used_elsewhere(ctx.session, ctx.company_id, None, photos)
        listed = []
        for photo in photos:
            item = photo.for_model(looks.get(photo.id))
            if photo.id in taken:
                item["taken"] = "another article's cover already: do not choose it"
            listed.append(item)
        return ToolResult(
            cost_usd=cost,
            output={
                "query": args.query,
                "photos": listed,
                "note": "'looks' is what a viewer saw in each image (trust it over 'shows', the "
                "library's tags); 'kind' says photo or illustration. "
                "None suitable: try other words, or report no cover.",
            },
            summary=f"{len(photos)} photos for {args.query!r} ({library.name})",
        )

    return search_images


def set_cover_tool(library: covers.ImageLibrary | None, store: covers.CoverStore) -> ToolFn:
    async def set_cover(args: SetCoverArgs, ctx: ToolContext) -> ToolResult:
        if library is None:
            raise covers.CoverError(NO_LIBRARY)
        story = await ctx.session.get(Story, args.story_id)
        if story is None or story.company_id != ctx.company_id:
            raise covers.CoverError(f"no story {args.story_id} in this company")
        found = await library.search(args.query, limit=LOOKED_AT)
        photo = next((p for p in found if p.id == args.photo_id), None)
        if photo is None:
            raise covers.CoverError(
                f"photo {args.photo_id} is not among the results for {args.query!r}: "
                "use a photo_id search_images returned for that exact query"
            )
        row = await covers.set_cover(
            ctx.session,
            company_id=ctx.company_id,
            story_id=story.id,
            photo=photo,
            candidates=found,
            alt={"zh-TW": args.alt_zh.strip(), "en": args.alt_en.strip()},
            query=args.query,
            library=library,
            store=store,
            run_id=ctx.run_id,
        )
        return ToolResult(
            output={
                "cover_id": str(row.id),
                "photo_id": row.provider_id,
                "size": f"{row.width}x{row.height}",
                "kb": round(row.bytes / 1000),
                "others_kept": len(row.candidates),
            },
            summary=f"cover for story {story.id}: {row.provider} {row.provider_id} "
            f"({round(row.bytes / 1000)} KB)",
            produced=[ProducedRef(type="cover", id=row.id)],
        )

    return set_cover


class GenerateCoverArgs(BaseModel):
    story_id: uuid.UUID
    prompt: str = Field(
        min_length=20,
        max_length=600,
        description="In English: what the image shows, its composition, colour and mood. The "
        "site's rules (no text, no logos, no real people, wide) are added for you.",
    )
    alt_zh: str = Field(
        min_length=2, max_length=120, description="What it shows, in Traditional Chinese."
    )
    alt_en: str = Field(min_length=2, max_length=160, description="What it shows, in English.")
    brands: list[str] = Field(
        default=[],
        max_length=3,
        description="Logos to draw in, by slug, from those the context offers (the story's own "
        "companies and coins); say in the prompt where each goes.",
    )


async def story_brands(session, story: Story) -> list[brands.Brand]:
    """The brands the story names (D-150): its title, summary, angle and claims."""
    texts = [story.title, story.summary or "", story.angle or ""]
    texts += (await session.scalars(select(Claim.text).where(Claim.story_id == story.id))).all()
    return brands.named("\n".join(texts))


def generate_cover_tool(
    painter: covers.Painter | None,
    store: covers.CoverStore,
    viewer: covers.ImageViewer | covers.FixtureViewer | None,
    per_day: int,
) -> ToolFn:
    async def generate_cover(args: GenerateCoverArgs, ctx: ToolContext) -> ToolResult:
        if painter is None or per_day <= 0:
            raise covers.CoverError("image generation is not set up: report no cover")
        story = await ctx.session.get(Story, args.story_id)
        if story is None or story.company_id != ctx.company_id:
            raise covers.CoverError(f"no story {args.story_id} in this company")
        if await covers.generated_today(ctx.session, ctx.company_id) >= per_day:
            raise covers.CoverError(
                f"today's {per_day} generated covers are used: take a library photo or none"
            )
        allowed = {b.slug: b for b in await story_brands(ctx.session, story)}
        references = []
        for slug in dict.fromkeys(args.brands):
            if slug not in allowed:
                raise covers.CoverError(
                    f"{slug!r} is not a brand this story is about: use only the ones offered"
                )
            logo = await store.fetch(brands.logo_key(slug))
            if logo is None:
                raise covers.CoverError(f"no logo is kept for {slug!r}: leave it out")
            references.append((allowed[slug].name, logo))
        data, cost = await painter.paint(args.prompt, references)
        photo = covers.generated_photo(args.prompt)
        previous = await covers.cover_of(ctx.session, story.id)
        # the library photos found before stay, for a person to swap back to
        kept = [covers.Photo.from_json(c) for c in (previous.candidates if previous else [])]
        if previous is not None and previous.photo and previous.provider != covers.GENERATED:
            kept.insert(0, covers.Photo.from_json(previous.photo))
        row = await covers.set_cover(
            ctx.session,
            company_id=ctx.company_id,
            story_id=story.id,
            photo=photo,
            candidates=kept,
            alt={"zh-TW": args.alt_zh.strip(), "en": args.alt_en.strip()},
            query=f"generated: {args.prompt[:200]}",
            library=None,
            store=store,
            run_id=ctx.run_id,
            data=data,
        )
        looked = None
        if viewer is not None and isinstance(viewer, covers.ImageViewer):
            looked, look_cost = await viewer.look_at(photo.id, data)
            cost += look_cost
        return ToolResult(
            cost_usd=cost,
            output={
                "photo_id": row.provider_id,
                "size": f"{row.width}x{row.height}",
                "kb": round(row.bytes / 1000),
                "looks": looked,
                "note": "It is the story's cover now. If 'looks' shows text, a logo or a person, "
                "or it does not fit, generate once more with a clearer prompt.",
            },
            summary=f"generated cover for story {story.id} ({round(row.bytes / 1000)} KB)",
            produced=[ProducedRef(type="cover", id=row.id)],
        )

    return generate_cover


def register(
    registry: ToolRegistry,
    library: covers.ImageLibrary | None,
    store: covers.CoverStore,
    viewer: covers.ImageViewer | covers.FixtureViewer | None = None,
    painter: covers.Painter | None = None,
    per_day: int = 0,
) -> None:
    registry.tool(
        "search_images",
        description=(
            "Search the free photo library for an article's cover. English keywords; returns "
            "each image's id, the library's tags, and what the image looks like."
        ),
        side_effect="read",
        timeout_s=25.0,
        retryable=True,
    )(search_images_tool(library, viewer))
    registry.tool(
        "set_cover",
        description=(
            "Make one photo from search_images the story's cover: it is downloaded, cut to "
            "1200x630 and stored. Give what it shows in Chinese and English (for readers who "
            "cannot see it)."
        ),
        side_effect="write",
        timeout_s=60.0,
    )(set_cover_tool(library, store))
    registry.tool(
        "generate_cover",
        description=(
            "Have an image model draw the story's cover (costs more than a library photo; a "
            "few a day): only when no library image fits. It becomes the cover at once."
        ),
        side_effect="write",
        timeout_s=150.0,
    )(generate_cover_tool(painter, store, viewer, per_day))
