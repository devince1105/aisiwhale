// The floor, drawn as pixel art on a canvas (T-410; D-026, D-027).
//
// Everything here was baked from the 3D office — the room's shell as one backdrop, each piece of
// furniture as its own sprite — and is painted in whichever of the office's styles is chosen, so
// switching 日式無印 to 電光風 in the settings repaints the 2D floor with it. The canvas has its
// own resolution (a metre of floor is 32 pixels across) and the browser scales it up with
// nearest-neighbour: every pixel on screen is a whole pixel of the drawing.
//
// This component only drives the frames: it steps the walking queue and hands the frame to
// ``floorPainter``, which is shared with the bake tool's preview. What exists and where is
// ``tiles.buildScene``, which is pure and tested without a canvas.
"use client";

import { useEffect, useMemo, useRef } from "react";

import { uiStore } from "@/stores/ui";

import { useRoster } from "../agents/roster";
import { DEFAULT_THEME, type ThemeId } from "../palette";
import { CueDirector, routeFor } from "../visual/CueRunner";
import type { BoardCard, FloorPlan } from "./board";
import { BACKDROP_KEY, piece, type BakedPiece } from "./art/pieces";
import { paintFloor, Pictures } from "./floorPainter";
import { buildScene, hitTest, type Scene } from "./tiles";
import { walkersNow, type Walker } from "./walkers";

declare global {
  interface Window {
    /** Who is walking across the 2D floor right now, and in which style, for browser tests; not
     * an API. The 3D office publishes the same thing under ``__autoraOfficeCues``. */
    __autoraOfficeFloor?: { walking: string[]; walks: number; theme?: ThemeId };
  }
}

let lastWalking = "";

function probe(walking: Walker[], theme: ThemeId): void {
  if (typeof window === "undefined") return;
  const ids = walking.map((walker) => walker.agentId);
  const key = ids.join(",");
  const previous = window.__autoraOfficeFloor;
  if (key === lastWalking && previous?.theme === theme) return;
  const started = key === lastWalking ? 0 : ids.filter((id) => !lastWalking.includes(id)).length;
  window.__autoraOfficeFloor = { walking: ids, walks: (previous?.walks ?? 0) + started, theme };
  lastWalking = key;
}

/** The floor's picture as a rectangle it fills on every row, in canvas pixels (D-187): walls and
 * windows included, without the empty columns its bake and the canvas's whole tiles leave on the
 * right — nor the corners where its outline is not square (the top rows end 12 px short on the
 * right), so no background shows anywhere along the frame. */
export function floorBox(
  back: Pick<BakedPiece, "rows"> | null,
  scene: Pick<Scene, "backdrop" | "width" | "height">,
): { x: number; y: number; width: number; height: number } | null {
  if (!back) return null;
  let x0 = 0, x1 = Infinity, y0 = -1, y1 = -1; // prettier-ignore
  back.rows.forEach((row, y) => {
    let first = -1;
    let last = -1;
    for (let x = 0; x < row.length; x++) {
      if (row[x] === "." || row[x] === " ") continue;
      if (first < 0) first = x;
      last = x;
    }
    if (last < 0) return; // an empty row: above or below the floor
    if (y0 < 0) y0 = y;
    y1 = y;
    x0 = Math.max(x0, first);
    x1 = Math.min(x1, last);
  });
  if (y0 < 0 || x1 < x0) return null;
  const x = Math.max(0, scene.backdrop.x + x0);
  const y = Math.max(0, scene.backdrop.y + y0);
  return { x, y, width: Math.min(scene.width, scene.backdrop.x + x1 + 1) - x, height: Math.min(scene.height, scene.backdrop.y + y1 + 1) - y };
}

/** The whole canvas, scaled so that ``box`` fills its frame. */
function cropStyle(box: { x: number; y: number; width: number; height: number }, scene: Pick<Scene, "width" | "height">) {
  return {
    width: `${(scene.width / box.width) * 100}%`,
    height: `${(scene.height / box.height) * 100}%`,
    left: `${(-box.x / box.width) * 100}%`,
    top: `${(-box.y / box.height) * 100}%`,
  };
}

export function PixelFloor({
  plan,
  cards,
  selected,
  focused,
  theme = DEFAULT_THEME,
  fit = "box",
}: {
  /** ``box``: fill the box it is given, letterboxed; ``width``: as wide as the box and only as tall
   * as the floor is (D-181) — no empty bands above and below it on a phone. */
  fit?: "box" | "width";
  plan: FloorPlan;
  /** The people on the floor, by id. */
  cards: Map<string, BoardCard>;
  selected: string | null;
  /** The room the tabs are on, or null for the whole floor. */
  focused: string | null;
  /** The office's style (D-011): the same one the 3D view is painted in. */
  theme?: ThemeId;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const scene = useRef<Scene | null>(null);
  const roster = useRoster();
  const characters = useMemo(() => new Map(roster.members.map((m) => [m.id, m.character as string])), [roster.members]);
  scene.current = buildScene(plan, cards, characters);
  const crop = useMemo(() => (fit === "width" ? floorBox(piece(BACKDROP_KEY), scene.current!) : null), [fit]); // the picture is fixed
  const pictures = useMemo(() => new Pictures(theme), [theme]);
  const latest = useRef({ roster, selected, focused, characters, pictures });
  latest.current = { roster, selected, focused, characters, pictures };

  // The 3D office walks its couriers from a frame hook inside its canvas. This one has no such
  // hook, so it runs the same queue itself: one director per board, stepped every frame.
  const director = useMemo(() => new CueDirector(), []);
  useEffect(() => () => director.dispose(), [director]);

  useEffect(() => {
    const element = canvas.current;
    const ctx = element?.getContext?.("2d");
    if (!element || !ctx) return; // no canvas in this environment: the tests' case
    let frame = 0;
    const draw = (time: number) => {
      const current = scene.current;
      const { roster: members, selected: chosen, focused: room, characters: wearing, pictures: art } = latest.current;
      if (!current) return;
      director.queue.step(time, (cue) => routeFor(cue, members)?.durationMs ?? null);
      const walking = walkersNow(director, members, time);

      if (element.width !== current.width) element.width = current.width;
      if (element.height !== current.height) element.height = current.height;
      paintFloor(ctx, current, art, {
        selected: chosen,
        focused: room,
        walking,
        characters: wearing,
        time,
      });
      probe(walking, art.theme);
      frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, [director]);

  const room = focused ? (plan.rooms.find((r) => r.id === focused)?.label ?? focused) : null;
  const drawn = (
    <canvas
      ref={canvas}
      data-testid="room-plan"
      data-office-theme={theme}
      role="img"
      aria-label={room ? `樓層（俯視，${room}）` : "樓層（俯視）"}
      width={scene.current.width}
      height={scene.current.height}
      className={
        fit === "width"
          ? "absolute"
          : "h-full w-full border-2 border-[color:var(--console-edge-dim)] object-contain"
      }
      style={{ imageRendering: "pixelated", background: "var(--console-bg)", ...(crop ? cropStyle(crop, scene.current) : null) }}
      onClick={(event) => {
        const current = scene.current;
        const element = canvas.current;
        if (!current || !element) return;
        const box = element.getBoundingClientRect();
        // the canvas is letterboxed by object-contain: undo that before hit-testing
        const scale = Math.min(box.width / current.width, box.height / current.height);
        const x = (event.clientX - box.left - (box.width - current.width * scale) / 2) / scale;
        const y = (event.clientY - box.top - (box.height - current.height * scale) / 2) / scale;
        const hit = hitTest(current, x, y);
        if (hit) uiStore.getState().selectAgent(hit);
      }}
    />
  );
  if (!crop) return drawn;
  // the floor's own outline, edge to edge: the picture's margins (D-187) are cut off by the frame
  return (
    <div
      className="relative w-full overflow-hidden border-2 border-[color:var(--console-edge-dim)]"
      style={{ aspectRatio: `${crop.width} / ${crop.height}` }}
    >
      {drawn}
    </div>
  );
}
