"""``search_images`` and ``set_cover`` (D-142): marketing picks an article's cover.

``search_images`` asks the photo library (read; nothing is kept). ``set_cover`` takes one of the
photos that search returned — by its id, from the same query — downloads it, cuts it to 1200x630
WebP, stores it and makes it the story's cover, keeping the rest of the results for a person to
swap to. Without a library (no ``PIXABAY_API_KEY``) both say so, and the story has no cover.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from autora.domains.newsroom import covers
from autora.domains.newsroom.models import Story
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


def register(
    registry: ToolRegistry,
    library: covers.ImageLibrary | None,
    store: covers.CoverStore,
    viewer: covers.ImageViewer | covers.FixtureViewer | None = None,
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
