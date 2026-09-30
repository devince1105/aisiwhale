// The office's furniture and architecture as primitive parts (T-402, D-010). Every piece is built
// around its own origin, facing +z (a chair's sitter faces -z: its back is on the +z side), and
// placed from layout.ts. Nothing here knows about agents or state.
import { Matrix4 } from "three";

import { DEFAULT_THEME, ROLE_COLOR, THEMES, type FloorKind, type Palette } from "../palette";
import { block, box, cyl, place, sphere, type Part } from "./kit";
import {
  allSeats,
  APPROVAL_DESK,
  APPROVAL_FOOTPRINT,
  BACK_ROOMS_Z,
  BENCHES,
  CEO_OFFICE,
  DECOR,
  DESK,
  doorLeaves,
  DOORS,
  ENTRANCE,
  MEETING_ROOM,
  PANTRY,
  ROOM,
  GLASS_HEIGHT,
  GLASS_WALLS,
  glassSpans,
  SERVER_RACKS,
  SERVER_ROOM,
  SPINE,
  type GlassWall,
  WALL_HALF,
  ZONES,
  type Decor,
  type Seat,
} from "./layout";

/**
 * The palette the builders below paint with. Set by the exported entry points (officeParts and
 * the glass) for the duration of one build, so the builders need not pass it along.
 */
let P: Palette = THEMES[DEFAULT_THEME].palette;

function paintedWith<T>(palette: Palette, build: () => T): T {
  const previous = P;
  P = palette;
  try {
    return build();
  } finally {
    P = previous;
  }
}
const TOP = DESK.height; // desk top surface

/** A deterministic pseudo-random sequence, so the books look the same on every load. */
function seeded(seed: number): () => number {
  let s = seed;
  return () => {
    s = (s * 16807) % 2147483647;
    return s / 2147483647;
  };
}

/** A leaf: a flat blade from the origin along +z, tilted by `pitch` (negative = up). */
function leaf(length: number, width: number, pitch: number, color: string): Part {
  const m = new Matrix4().makeRotationX(pitch).multiply(new Matrix4().makeTranslation(0, 0, length / 2));
  return { shape: { kind: "box", w: width, h: 0.012, d: length }, matrix: m, color };
}

function rosette(count: number, length: number, width: number, pitch: (i: number) => number, y: number, color: (i: number) => string, twist = 0): Part[] {
  return Array.from({ length: count }, (_, i) => place([leaf(length, width, pitch(i), color(i))], 0, 0, twist + (i * Math.PI * 2) / count, y)).flat();
}

// --- seating & desks ---------------------------------------------------------------------------

/** An office chair: five-star base, gas lift, seat, back with two accent stripes, arms. */
export function officeChair(accent: string, tall = false): Part[] {
  const parts: Part[] = [];
  for (let i = 0; i < 5; i++) {
    const a = (i * Math.PI * 2) / 5;
    parts.push(box(0.05, 0.035, 0.3, [Math.sin(a) * 0.15, 0.06, Math.cos(a) * 0.15], P.metal, [0, a, 0]));
    parts.push(sphere(0.03, [Math.sin(a) * 0.29, 0.03, Math.cos(a) * 0.29], P.metal, undefined, 6));
  }
  const backH = tall ? 0.78 : 0.6;
  parts.push(
    cyl(0.025, 0.025, 0.32, [0, 0.07, 0], P.metal, 6),
    block(0.52, 0.08, 0.5, [0, 0.38, 0], P.chair),
    box(0.48, backH, 0.07, [0, 0.47 + backH / 2, 0.26], P.chair, [-0.1, 0, 0]),
    box(0.07, backH - 0.08, 0.075, [-0.14, 0.47 + backH / 2, 0.265], accent, [-0.1, 0, 0]),
    box(0.07, backH - 0.08, 0.075, [0.14, 0.47 + backH / 2, 0.265], accent, [-0.1, 0, 0]),
  );
  for (const side of [-1, 1]) {
    parts.push(block(0.04, 0.2, 0.04, [side * 0.28, 0.44, 0.02], P.metal), block(0.07, 0.03, 0.28, [side * 0.28, 0.63, 0.02], P.chair));
  }
  return parts;
}

/** A black metal leg frame under a table, across its depth. */
function legFrame(x: number, depth: number, height = TOP - 0.03): Part[] {
  const z = depth / 2 - 0.06;
  return [
    block(0.05, height, 0.05, [x, 0, -z], P.metal),
    block(0.05, height, 0.05, [x, 0, z], P.metal),
    box(0.05, 0.05, depth - 0.1, [x, 0.04, 0], P.metal),
    box(0.05, 0.05, depth - 0.1, [x, height - 0.03, 0], P.metal),
  ];
}

/** A lit strip along a desk top's front edge (the sitter's side, +z), in a theme that has one. */
function deskEdge(length: number, depth: number, top = TOP): Part[] {
  return P.deskEdge ? [box(length, 0.015, 0.015, [0, top - 0.02, depth / 2 + 0.006], P.deskEdge)] : [];
}

function benchTable(minX: number, maxX: number, z: number): Part[] {
  const length = maxX - minX;
  const parts: Part[] = [block(length, 0.05, DESK.depth, [0, TOP - 0.05, 0], P.deskTop), ...deskEdge(length, DESK.depth)];
  const frames = Math.max(2, Math.round(length / 2.2) + 1);
  for (let i = 0; i < frames; i++) parts.push(...legFrame(-length / 2 + 0.1 + (i * (length - 0.2)) / (frames - 1), DESK.depth));
  return place(parts, (minX + maxX) / 2, z);
}

function singleDesk(): Part[] {
  return [
    block(DESK.width, 0.05, DESK.depth, [0, TOP - 0.05, 0], P.deskTop),
    ...deskEdge(DESK.width, DESK.depth),
    ...legFrame(-DESK.width / 2 + 0.08, DESK.depth),
    ...legFrame(DESK.width / 2 - 0.08, DESK.depth),
    block(0.4, 0.55, 0.5, [0.42, 0.02, -0.05], P.pedestal),
  ];
}

function execDesk(): Part[] {
  return [
    block(DESK.width + 0.2, 0.06, DESK.depth + 0.1, [0, TOP - 0.06, 0], P.execWood),
    ...deskEdge(DESK.width + 0.2, DESK.depth + 0.1),
    block(0.06, TOP - 0.06, DESK.depth, [-DESK.width / 2, 0, 0], P.execWood),
    block(0.06, TOP - 0.06, DESK.depth, [DESK.width / 2, 0, 0], P.execWood),
    block(DESK.width, 0.5, 0.04, [0, 0.15, -DESK.depth / 2 + 0.05], P.execWood),
  ];
}

export const MONITOR = { width: 0.62, height: 0.38, y: TOP + 0.32, spread: 0.33, z: -0.18, turn: 0.2 } as const;

/** Where each of a seat's two screens is, for the screen meshes (T-406 lights them). */
export function screenSpots(seat: Seat): { pos: [number, number, number]; rotY: number }[] {
  const flip = seat.turn ? -1 : 1; // a turned desk (D-119): the same spots, mirrored through its centre
  return [-1, 1].map((side) => {
    const rotY = -side * MONITOR.turn;
    const x = seat.desk[0] + flip * (side * MONITOR.spread + Math.sin(rotY) * 0.02);
    const z = seat.desk[1] + flip * (MONITOR.z + Math.cos(rotY) * 0.02);
    return { pos: [x, MONITOR.y, z], rotY: rotY + seat.turn };
  });
}

/** Two monitors on stands, a keyboard and a mouse, around a desk centre. */
function workstation(): Part[] {
  const parts: Part[] = [];
  for (const side of [-1, 1]) {
    const monitor = [
      box(MONITOR.width, MONITOR.height, 0.035, [0, MONITOR.y, 0], P.monitor),
      cyl(0.025, 0.025, MONITOR.y - TOP - 0.12, [0, TOP, -0.03], P.metal, 6),
      block(0.22, 0.015, 0.16, [0, TOP, -0.03], P.metal),
    ];
    parts.push(...place(monitor, side * MONITOR.spread, MONITOR.z, -side * MONITOR.turn));
  }
  parts.push(block(0.44, 0.02, 0.14, [0, TOP, 0.16], P.keyboard), block(0.06, 0.02, 0.1, [0.33, TOP, 0.18], P.keyboard));
  return parts;
}

/** The desk lamp at the back right of each desk: its shade and glow are live (T-406). */
export const LAMP = { x: 0.7, z: -0.3, height: 0.42, reach: 0.16 } as const;

export function lampSpot(seat: Seat): { shade: [number, number, number]; glow: [number, number, number] } {
  const flip = seat.turn ? -1 : 1;
  const x = seat.desk[0] + flip * (LAMP.x - LAMP.reach);
  const z = seat.desk[1] + flip * LAMP.z;
  return { shade: [x, TOP + LAMP.height - 0.05, z], glow: [x, TOP + 0.004, z + flip * 0.08] };
}

/** The approval desk's lamp, on its raised counter (the visitor side, 1.1 m up): blinks while
 * someone waits for a decision (T-407). At dz 0.2 it was over the low desk behind the counter,
 * at the counter's height — standing on nothing. */
const APPROVAL_LAMP = { dx: 1.0, dz: -0.33, lift: 1.1 - TOP } as const;

export function approvalLampSpot(): { shade: [number, number, number]; glow: [number, number, number] } {
  // the desk is turned (D-120, D-132): its own x and z, turned with it
  const [cos, sin] = [Math.cos(APPROVAL_DESK.turn), Math.sin(APPROVAL_DESK.turn)];
  const at = (lx: number, lz: number): [number, number] => [
    APPROVAL_DESK.center[0] + lx * cos + lz * sin,
    APPROVAL_DESK.center[1] - lx * sin + lz * cos,
  ];
  const [x, z] = at(APPROVAL_LAMP.dx - LAMP.reach, APPROVAL_LAMP.dz);
  const [gx, gz] = at(APPROVAL_LAMP.dx - LAMP.reach, APPROVAL_LAMP.dz - 0.05);
  return { shade: [x, 1.1 + LAMP.height - 0.05, z], glow: [gx, 1.1 + 0.004, gz] };
}

/** The lamp's fixed parts: base, pole and arm (the shade is drawn live). */
function lampBody(): Part[] {
  return [
    cyl(0.08, 0.08, 0.02, [LAMP.x, TOP, LAMP.z], P.metal, 10),
    cyl(0.012, 0.012, LAMP.height, [LAMP.x, TOP, LAMP.z], P.metal, 6),
    box(LAMP.reach + 0.02, 0.02, 0.02, [LAMP.x - LAMP.reach / 2, TOP + LAMP.height, LAMP.z], P.metal),
  ];
}

function seatParts(seat: Seat): Part[] {
  const accent = ROLE_COLOR[seat.role] ?? ROLE_COLOR.spare;
  const [x, z] = seat.desk;
  const desk = seat.bench ? [] : seat.role === "ceo" ? execDesk() : singleDesk();
  return [
    ...place([...desk, ...workstation(), ...lampBody()], x, z, seat.turn),
    ...place(officeChair(accent, seat.role === "ceo"), seat.chair[0], seat.chair[1], seat.turn),
  ];
}

// --- decoration --------------------------------------------------------------------------------

function books(width: number, y: number, depth: number, rand: () => number): Part[] {
  const parts: Part[] = [];
  let x = -width / 2 + 0.03;
  while (x < width / 2 - 0.08) {
    const w = 0.03 + rand() * 0.04;
    const h = 0.18 + rand() * 0.1;
    const color = P.books[Math.floor(rand() * P.books.length)];
    parts.push(block(w, h, depth * 0.75, [x + w / 2, y, 0], color, [0, 0, rand() < 0.1 ? 0.25 : 0]));
    x += w + 0.005;
  }
  return parts;
}

function smallPlant(pot: string = P.pot, scale = 1): Part[] {
  const parts: Part[] = [cyl(0.17, 0.13, 0.28, [0, 0, 0], pot, 10), cyl(0.16, 0.16, 0.02, [0, 0.26, 0], P.soil, 10)];
  parts.push(...rosette(8, 0.36, 0.16, (i) => -0.8 + (i % 3) * 0.3, 0.3, (i) => (i % 2 ? P.leafLight : P.leaf)));
  return place(parts.map((p) => ({ ...p, matrix: new Matrix4().makeScale(scale, scale, scale).multiply(p.matrix) })), 0, 0);
}

function palm(): Part[] {
  const parts: Part[] = [cyl(0.3, 0.24, 0.6, [0, 0, 0], P.pot, 12), cyl(0.28, 0.28, 0.02, [0, 0.58, 0], P.soil, 12)];
  const stems: [number, number, number][] = [
    [0.05, 2.1, 0.05],
    [-0.08, 1.7, 0.02],
    [0.06, 1.4, -0.07],
  ];
  for (const [dx, h, dz] of stems) {
    parts.push(cyl(0.035, 0.05, h - 0.6, [dx, 0.6, dz], P.trunk, 6));
    parts.push(...place(rosette(11, 0.95, 0.17, (i) => -0.35 + (i % 3) * 0.3, 0, (i) => (i % 3 ? P.leaf : P.leafLight), h), dx, dz, 0, h));
  }
  return parts;
}

function lowShelf(length: number, seed: number): Part[] {
  const h = 0.9;
  const dpt = 0.4;
  const rand = seeded(seed);
  const parts: Part[] = [
    block(length, 0.04, dpt, [0, 0, 0], P.shelfWood),
    block(length, 0.04, dpt, [0, h - 0.04, 0], P.shelfWood),
    block(length, 0.03, dpt, [0, h / 2 - 0.015, 0], P.shelfWood),
    block(length, h, 0.02, [0, 0, -dpt / 2 + 0.01], P.shelfWood),
  ];
  const cells = Math.round(length / 0.45);
  for (let i = 0; i <= cells; i++) parts.push(block(0.03, h, dpt, [-length / 2 + (i * length) / cells, 0, 0], P.shelfWood));
  for (let i = 0; i < cells; i++) {
    const cx = -length / 2 + ((i + 0.5) * length) / cells;
    if (rand() < 0.55) parts.push(...place(books(length / cells - 0.05, 0.04, dpt, rand), cx, 0));
    if (rand() < 0.35) parts.push(...place(books(length / cells - 0.05, h / 2 + 0.015, dpt, rand), cx, 0));
  }
  parts.push(...place(smallPlant(rand() < 0.5 ? P.pot : P.potTerracotta, 0.8), -length / 3, 0, 0, h));
  parts.push(...place(smallPlant(P.pot, 0.7), length / 3, 0, 0, h));
  return parts;
}

function tallShelf(width: number, seed: number, color: string = P.shelfDark): Part[] {
  const h = 2.0;
  const dpt = 0.45;
  const rand = seeded(seed);
  const parts: Part[] = [
    block(0.04, h, dpt, [-width / 2, 0, 0], color),
    block(0.04, h, dpt, [width / 2, 0, 0], color),
    block(width, h, 0.02, [0, 0, -dpt / 2 + 0.01], color),
  ];
  for (let i = 0; i <= 5; i++) {
    const y = i * (h / 5) - (i === 5 ? 0.04 : 0);
    parts.push(block(width, 0.04, dpt, [0, y, 0], color));
    if (i < 5 && rand() < 0.6) parts.push(...books(width * (0.4 + rand() * 0.5), y + 0.04, dpt, rand).map((p) => ({ ...p })));
  }
  return parts;
}

function sofa(length: number, color: string, cushion: string): Part[] {
  const parts: Part[] = [
    block(length, 0.28, 0.85, [0, 0.08, 0], color),
    block(length, 0.5, 0.2, [0, 0.3, -0.33], color),
    block(0.18, 0.5, 0.85, [-length / 2 + 0.09, 0.08, 0], color),
    block(0.18, 0.5, 0.85, [length / 2 - 0.09, 0.08, 0], color),
  ];
  const seats = Math.max(1, Math.round(length / 0.8));
  const inner = length - 0.36;
  for (let i = 0; i < seats; i++) {
    const x = -inner / 2 + ((i + 0.5) * inner) / seats;
    parts.push(block(inner / seats - 0.04, 0.12, 0.62, [x, 0.36, 0.06], cushion));
    parts.push(box(inner / seats - 0.1, 0.38, 0.12, [x, 0.66, -0.2], cushion, [-0.2, 0, 0]));
  }
  for (const sx of [-1, 1]) for (const sz of [-1, 1]) parts.push(block(0.05, 0.08, 0.05, [sx * (length / 2 - 0.1), 0, sz * 0.35], P.metal));
  return parts;
}

function lounge(): Part[] {
  return [
    ...place(sofa(2.2, P.sofa, P.cushion), 1.15, 0, -Math.PI / 2),
    ...place(sofa(0.95, P.armchair, P.cushion), -1.0, -1.1, Math.PI / 2),
    ...place(sofa(0.95, P.armchair, P.cushion), -1.0, 1.1, Math.PI / 2),
    block(1.0, 0.04, 0.7, [0.05, 0.38, 0], P.glassTable),
    ...[-1, 1].flatMap((sx) => [-1, 1].map((sz) => block(0.04, 0.38, 0.04, [0.05 + sx * 0.45, 0, sz * 0.3], P.metal))),
    ...place(smallPlant(P.potTerracotta, 1.1), 1.3, 1.55),
  ];
}

/** The meeting table (D-120), built along its own x with its open end at +x: turned a quarter in
 * the room, that end faces the projection screen on the back wall. Three chairs a side facing
 * each other, one at the far end facing the screen, none in front of it. */
export const MEETING_TABLE = { length: 2.8, width: 1.2 } as const;

function meetingSet(): Part[] {
  const { length, width } = MEETING_TABLE;
  const parts: Part[] = [
    block(length, 0.06, width, [0, TOP - 0.06, 0], P.tableWood),
    block(0.12, TOP - 0.06, width - 0.4, [-length / 2 + 0.4, 0, 0], P.metal),
    block(0.12, TOP - 0.06, width - 0.4, [length / 2 - 0.4, 0, 0], P.metal),
    block(0.5, 0.02, 0.35, [-0.6, TOP, 0.15], P.keyboard),
    block(0.5, 0.02, 0.35, [0.7, TOP, -0.15], P.keyboard),
  ];
  for (const x of [-0.85, 0, 0.85]) {
    parts.push(...place(officeChair(P.cushion), x, width / 2 + 0.35));
    parts.push(...place(officeChair(P.cushion), x, -width / 2 - 0.35, Math.PI));
  }
  const end = -length / 2 - 0.55;
  parts.push(...place(officeChair(P.cushion), end, 0, -Math.PI / 2));
  // centred on what it covers (from the end chair to the table's open end), as its footprint is
  return place(parts, -(end - 0.3 + length / 2) / 2, 0);
}

function whiteboard(): Part[] {
  return [
    box(1.5, 0.95, 0.04, [0, 1.45, 0], P.whiteboard),
    box(1.56, 0.04, 0.06, [0, 1.95, 0], P.pedestal),
    box(1.56, 0.04, 0.08, [0, 0.95, 0.02], P.pedestal),
    ...[-0.7, 0.7].flatMap((x) => [block(0.04, 1.95, 0.04, [x, 0, 0], P.pedestal), block(0.05, 0.03, 0.6, [x, 0, 0], P.pedestal)]),
    box(0.3, 0.2, 0.01, [-0.35, 1.55, 0.025], P.picture[0]),
    box(0.4, 0.02, 0.01, [0.3, 1.6, 0.025], P.books[1]),
    box(0.3, 0.02, 0.01, [0.25, 1.45, 0.025], P.books[0]),
  ];
}

function pantryCounter(): Part[] {
  const length = 4.2;
  const parts: Part[] = [
    block(length, 0.85, 0.6, [0, 0, 0], P.counter),
    block(length + 0.05, 0.05, 0.66, [0, 0.85, 0.02], P.counterTop),
    block(0.6, 0.02, 0.4, [-0.9, 0.9, 0.02], P.fridge),
    block(length, 0.7, 0.35, [0, 1.55, -0.12], P.counter),
    block(0.55, 0.32, 0.4, [1.2, 0.9, -0.05], P.keyboard),
  ];
  const doors = 6;
  for (let i = 0; i < doors; i++) {
    const x = -length / 2 + ((i + 0.5) * length) / doors;
    parts.push(box(length / doors - 0.04, 0.7, 0.02, [x, 0.45, 0.305], P.counterFront));
    parts.push(box(length / doors - 0.04, 0.6, 0.02, [x, 1.9, 0.06], P.counterFront));
  }
  return parts;
}

function fridge(): Part[] {
  return [block(0.85, 2.0, 0.75, [0, 0, 0], P.fridge), box(0.03, 0.6, 0.04, [0.3, 1.35, 0.39], P.metal), box(0.03, 0.4, 0.04, [0.3, 0.6, 0.39], P.metal), box(0.84, 0.01, 0.01, [0, 1.0, 0.38], P.metal)];
}

function vending(): Part[] {
  return [
    block(0.9, 1.9, 0.8, [0, 0, 0], P.vending),
    box(0.55, 1.2, 0.02, [-0.1, 1.15, 0.41], P.vendingGlass),
    box(0.18, 0.5, 0.02, [0.3, 1.3, 0.41], P.metal),
    box(0.55, 0.15, 0.02, [-0.1, 0.35, 0.41], P.metal),
  ];
}

function waterCooler(): Part[] {
  return [block(0.4, 1.0, 0.4, [0, 0, 0], P.cooler), cyl(0.15, 0.15, 0.42, [0, 1.0, 0], P.coolerBottle, 10), box(0.2, 0.06, 0.03, [0, 0.8, 0.21], P.metal)];
}

function stool(): Part[] {
  return [cyl(0.2, 0.2, 0.05, [0, 0.62, 0], P.tableWood, 10), cyl(0.03, 0.03, 0.62, [0, 0, 0], P.metal, 6), cyl(0.18, 0.18, 0.02, [0, 0, 0], P.metal, 10)];
}

function cafeTable(): Part[] {
  return [
    cyl(0.55, 0.55, 0.04, [0, TOP, 0], P.deskTop, 16),
    cyl(0.05, 0.05, TOP, [0, 0, 0], P.metal, 8),
    cyl(0.3, 0.3, 0.02, [0, 0, 0], P.metal, 12),
    ...[0, 2, 4].flatMap((i) => place(stool(), Math.sin((i * Math.PI) / 3) * 0.85, Math.cos((i * Math.PI) / 3) * 0.85)),
  ];
}

/** A long low planter box of greenery: divides two zones without walling them off. */
function planter(length: number): Part[] {
  const parts: Part[] = [block(length, 0.45, 0.36, [0, 0, 0], P.shelfWood), block(length - 0.06, 0.02, 0.3, [0, 0.44, 0], P.soil)];
  const plants = Math.max(2, Math.round(length / 0.4));
  for (let i = 0; i < plants; i++) {
    const x = -length / 2 + ((i + 0.5) * length) / plants;
    parts.push(...place(rosette(7, 0.34, 0.14, (j) => -0.9 + (j % 3) * 0.3, 0, (j) => ((i + j) % 2 ? P.leafLight : P.leaf), i), x, 0, 0, 0.45));
  }
  return parts;
}

/** One row of the server room's racks round its middle, fronts toward -z; each row's decor turns
 * it along z, fronts to the aisle between the rows (D-132). Their lights are live
 * (``ServerLights``), at ``serverLightSpots``. */
function serverRacks(): Part[] {
  const { zs, width, depth, height } = SERVER_RACKS;
  const mid = (zs[0] + zs[zs.length - 1]) / 2;
  return zs.flatMap((x) => [
    block(width, height, depth, [x - mid, 0, 0], P.monitor),
    // a darker door panel on each face, and a plinth
    box(width - 0.08, height - 0.14, 0.02, [x - mid, height / 2, -depth / 2 - 0.005], P.screenOff),
    box(width - 0.08, height - 0.14, 0.02, [x - mid, height / 2, depth / 2 + 0.005], P.screenOff),
    block(width + 0.02, 0.06, depth + 0.02, [x - mid, 0, 0], P.metal),
    cyl(0.035, 0.035, 0.03, [x - mid, height, 0], P.metal, 10),
  ]);
}

/** Where the racks' lights are (D-121): two columns of status lights on each face of each rack,
 * the top one of each column the activity light, and a beacon on every rack's top. */
export const SERVER_LIGHT_ROWS = 6;
export function serverLightSpots(): { leds: [number, number, number][]; beacons: [number, number, number][] } {
  const { rows, zs, depth, height } = SERVER_RACKS;
  const leds: [number, number, number][] = [];
  const beacons: [number, number, number][] = [];
  for (const { x } of rows)
    for (const z of zs) {
      for (const face of [-1, 1])
        for (const dz of [-0.13, 0.13])
          for (let row = 0; row < SERVER_LIGHT_ROWS; row++) leds.push([x + face * (depth / 2 + 0.02), height - 0.2 - row * 0.2, z + dz]);
      beacons.push([x, height + 0.08, z]);
    }
  return { leds, beacons };
}

/** A glass wall's frame (D-132), in place: a top rail, posts at its ends and every
 * 1.8 m (sparser than the back rooms' fronts: in the neon style the frames glow, and the office
 * is meant to stay mostly lit normally), and its door's frame. The panes are in
 * ``partitionGlassParts``. */
function glassWallFrame(wall: GlassWall): Part[] {
  const h = GLASS_HEIGHT;
  const along = (a: number, y: number, len: number, height: number, thick: number, color: string, standing: boolean): Part =>
    (standing ? block : box)(
      wall.axis === "x" ? len : thick,
      height,
      wall.axis === "x" ? thick : len,
      wall.axis === "x" ? [a, y, wall.at] : [wall.at, y, a],
      color,
    );
  const length = wall.to - wall.from;
  const middle = (wall.from + wall.to) / 2;
  // a top rail only: the panes stand on the floor
  const parts: Part[] = [along(middle, h - 0.03, length, 0.06, 0.1, P.mullion, false)];
  const posts = Math.max(1, Math.ceil(length / 1.8));
  for (let i = 0; i <= posts; i++) {
    const a = wall.from + (i * length) / posts;
    if (wall.door && Math.abs(a - wall.door.at) < wall.door.width / 2 + 0.05) continue; // not in the doorway
    parts.push(along(a, 0, 0.06, h, 0.1, P.mullion, true));
  }
  if (wall.door) {
    const { at, width } = wall.door;
    // a plain metal frame, not the back rooms' doors' (which glow in the neon style)
    for (const side of [-1, 1]) parts.push(along(at + (side * width) / 2, 0, 0.08, 2.1, 0.12, P.metal, true));
    parts.push(along(at, 2.14, width + 0.16, 0.08, 0.12, P.metal, false));
  }
  return parts;
}

function wallCentre(wall: GlassWall): [number, number] {
  const middle = (wall.from + wall.to) / 2;
  return wall.axis === "x" ? [middle, wall.at] : [wall.at, middle];
}

/** The server room's raised floor (D-121). */
function serverFloor(): Part[] {
  const { minX, maxX, minZ, maxZ } = SERVER_ROOM;
  return [block(maxX - minX, 0.03, maxZ - minZ, [(minX + maxX) / 2, 0, (minZ + maxZ) / 2], P.screenOff)];
}

/** A small meeting room's table and its two chairs (D-132): the table turned to the room's
 * diagonal and a chair at each end of it, so the two sit across a corner from each other rather
 * than squarely face to face — the easier way to talk, and it leaves the room's floor open. */
const DIAGONAL = Math.PI / 4;
const CHAIR_OUT = 0.62;
function smallMeeting(): Part[] {
  const table = [
    block(1.0, 0.05, 0.7, [0, TOP - 0.05, 0], P.tableWood),
    block(0.5, TOP - 0.05, 0.1, [0, 0, 0], P.metal),
    block(0.35, 0.02, 0.25, [0.2, TOP, 0.05], P.keyboard),
  ];
  return [
    ...place(table, 0, 0, DIAGONAL),
    // each chair faces the table's middle along the diagonal
    ...place(officeChair(P.cushion), CHAIR_OUT, CHAIR_OUT, DIAGONAL),
    ...place(officeChair(P.cushion), -CHAIR_OUT, -CHAIR_OUT, DIAGONAL - Math.PI),
  ];
}

function ceoSofa(): Part[] {
  return sofa(1.8, P.armchair, P.cushion);
}

/** What a decor item is made of, built around its own origin and not yet turned or placed. */
function decorBuild(item: Decor, index: number): Part[] {
  const build: Record<Decor["kind"], () => Part[]> = {
    low_shelf: () => lowShelf(Math.max(item.size[0], item.size[1]), 11 + index),
    palm,
    plant: () => smallPlant(index % 2 ? P.potTerracotta : P.pot, 1.2),
    lounge,
    meeting_set: meetingSet,
    whiteboard,
    pantry_counter: pantryCounter,
    fridge,
    vending,
    water_cooler: waterCooler,
    cafe_table: cafeTable,
    ceo_shelf: () => tallShelf(Math.max(item.size[0], item.size[1]), 41, P.execWood),
    ceo_sofa: ceoSofa,
    planter: () => planter(Math.max(item.size[0], item.size[1])),
    server_racks: serverRacks,
    small_meeting: smallMeeting,
  };
  return build[item.kind]();
}

function decorParts(item: Decor, index: number): Part[] {
  return place(decorBuild(item, index), item.at[0], item.at[1], item.rotY);
}

function approvalDesk(): Part[] {
  const { width, depth } = APPROVAL_DESK;
  // built with the visitor side at -z and the approver behind it (+z), then turned round (D-120):
  // the counter faces the front walkway, the chair is on the inside
  const parts: Part[] = [
    block(width, 1.05, 0.12, [0, 0, -depth / 2 + 0.06], P.counter),
    block(0.12, 1.05, depth, [-width / 2 + 0.06, 0, 0], P.counter),
    block(0.12, 1.05, depth, [width / 2 - 0.06, 0, 0], P.counter),
    block(width + 0.1, 0.05, 0.35, [0, 1.05, -depth / 2 + 0.1], P.deskTop),
    block(width - 0.24, 0.04, depth - 0.12, [0, TOP - 0.04, 0.05], P.deskTop),
    box(width + 0.01, 0.22, 0.02, [0, 0.7, -depth / 2 - 0.005], P.approvalAccent),
    box(0.35, 0.35, 0.02, [0, 0.35, -depth / 2 - 0.005], P.approvalAccent),
    ...place(workstation(), 0, 0.1),
    ...place(officeChair(P.approvalAccent), 0, depth / 2 + 0.45),
    ...place(lampBody(), APPROVAL_LAMP.dx - LAMP.x, APPROVAL_LAMP.dz - LAMP.z, 0, APPROVAL_LAMP.lift),
  ];
  return place(parts, APPROVAL_DESK.center[0], APPROVAL_DESK.center[1], APPROVAL_DESK.turn);
}

// --- architecture ------------------------------------------------------------------------------

const WALL = 0.25;
const CAP = 0.05;
const INNER_WALL_H = 2.8;

/** A window on a wall plane (local +z = into the room): frame and mullions; the glass is separate. */
function windowFrame(width: number, height: number, sill: number): Part[] {
  const t = 0.07;
  const parts: Part[] = [
    box(width, t, 0.08, [0, sill, 0.04], P.frame),
    box(width, t, 0.08, [0, sill + height, 0.04], P.frame),
    box(t, height, 0.08, [-width / 2, sill + height / 2, 0.04], P.frame),
    box(t, height, 0.08, [width / 2, sill + height / 2, 0.04], P.frame),
    box(width + 0.1, 0.05, 0.16, [0, sill - 0.04, 0.08], P.frame),
  ];
  const panes = Math.max(2, Math.round(width / 0.7));
  for (let i = 1; i < panes; i++) parts.push(box(0.05, height, 0.07, [-width / 2 + (i * width) / panes, sill + height / 2, 0.04], P.frame));
  return parts;
}

function picture(width: number, height: number, color: string): Part[] {
  return [box(width, height, 0.03, [0, 0, 0.015], P.metal), box(width - 0.08, height - 0.08, 0.035, [0, 0, 0.02], color), box((width - 0.08) * 0.4, (height - 0.08) * 0.5, 0.04, [0.05, -0.02, 0.022], P.frame)];
}

/** Windows (frames here; glass in windowGlassParts) as [x or z along the wall, width]. */
const BACK_WINDOWS: [number, number][] = [
  [-3.8, 1.4],
  [2.0, 1.4],
  [10.7, 1.6],
];
const LEFT_WINDOWS: [number, number][] = [
  [-5.6, 2.4],
  // the open office's three, all the CEO office's size and evenly spaced (1.3 m apart), the
  // picture in the first gap (D-122, D-132)
  [-1.8, 2.4],
  [1.9, 2.4],
  [5.6, 2.4],
];
const WINDOW = { sill: 1.0, height: 1.5 };

/** The two full-height walls of the diorama (D-119): the 3D office hides the one the camera is
 * behind when it is turned round, so they are their own meshes there; the 2D board keeps them in
 * its baked backdrop. */
export type OuterWall = "back" | "left";
export const OUTER_WALLS: readonly OuterWall[] = ["back", "left"];

/** A wall with its cap, skirting, windows and what hangs on it. */
function outerWall(side: OuterWall): Part[] {
  const width = ROOM.maxX - ROOM.minX;
  const depth = ROOM.maxZ - ROOM.minZ;
  if (side === "back")
    return [
      block(width + WALL, ROOM.wallHeight, WALL, [-WALL / 2, 0, ROOM.minZ - WALL / 2], P.wall),
      box(width + WALL + 0.04, CAP, WALL + 0.04, [-WALL / 2, ROOM.wallHeight + CAP / 2, ROOM.minZ - WALL / 2], P.wallCap),
      block(width, 0.12, 0.02, [0, 0, ROOM.minZ + 0.01], P.frame),
      ...BACK_WINDOWS.flatMap(([x, w]) => place(windowFrame(w, WINDOW.height, WINDOW.sill), x, ROOM.minZ)),
      // the meeting room's projection screen
      box(3.2, 1.7, 0.03, [-0.8, 1.75, ROOM.minZ + 0.03], P.whiteboard),
      box(3.4, 0.12, 0.14, [-0.8, 2.65, ROOM.minZ + 0.08], P.metal),
    ];
  return [
    block(WALL, ROOM.wallHeight, depth, [ROOM.minX - WALL / 2, 0, 0], P.wall),
    box(WALL + 0.04, CAP, depth + 0.04, [ROOM.minX - WALL / 2, ROOM.wallHeight + CAP / 2, 0], P.wallCap),
    block(0.02, 0.12, depth, [ROOM.minX + 0.01, 0, 0], P.frame),
    ...LEFT_WINDOWS.flatMap(([z, w]) => place(windowFrame(w, WINDOW.height, WINDOW.sill), ROOM.minX, z, Math.PI / 2)),
    ...place(picture(0.9, 0.7, P.picture[0]), ROOM.minX + 0.01, 0.05, Math.PI / 2, 1.75),
  ];
}

/** Whether the camera, at ``position``, is on a wall's outer side: that wall would stand between
 * it and the room (D-119). */
export function wallInTheWay(side: OuterWall, position: { x: number; z: number }): boolean {
  return side === "back" ? position.z < ROOM.minZ : position.x < ROOM.minX;
}

/** A wall's parts, in a palette: its own mesh in the 3D office. */
export function outerWallParts(side: OuterWall, palette: Palette = DEFAULT_PALETTE): Part[] {
  return paintedWith(palette, () => outerWall(side));
}

/**
 * The office's shell: what never stands in front of anything — the slab, the back and left walls
 * with their windows and pictures, the low rims of the cut-away front and right, the entrance.
 * The 2D board bakes this as one backdrop and draws it first.
 */
function shell(): Part[] {
  return [...shellCore(), ...OUTER_WALLS.flatMap(outerWall)];
}

/** The shell without its two tall walls: what the 3D office merges into one mesh (D-119). */
function shellCore(): Part[] {
  const width = ROOM.maxX - ROOM.minX;
  const parts: Part[] = [
    // the slab the diorama stands on, with its white edge
    block(width + 0.8, 0.35, ROOM.maxZ - ROOM.minZ + 0.8, [0, -0.35, 0], P.slab),
    // the cut-away front and right edges: a low white rim, open at the entrance
    block(width + WALL * 2, 0.14, WALL, [0, 0, ROOM.maxZ + WALL / 2], P.wallCap),
    block(WALL, 0.14, ENTRANCE.minZ - ROOM.minZ + WALL, [ROOM.maxX + WALL / 2, 0, (ROOM.minZ - WALL + ENTRANCE.minZ) / 2], P.wallCap),
    block(WALL, 0.14, ROOM.maxZ - ENTRANCE.maxZ, [ROOM.maxX + WALL / 2, 0, (ENTRANCE.maxZ + ROOM.maxZ) / 2], P.wallCap),
  ];

  // the entrance: a slim portal frame on the right edge (its sign is a label) and a threshold
  {
    const x = ENTRANCE.x + WALL / 2;
    const span = ENTRANCE.maxZ - ENTRANCE.minZ;
    const mid = (ENTRANCE.minZ + ENTRANCE.maxZ) / 2;
    for (const z of [ENTRANCE.minZ, ENTRANCE.maxZ]) parts.push(block(0.14, 2.3, 0.14, [x, 0, z], P.door));
    parts.push(box(0.14, 0.12, span + 0.14, [x, 2.36, mid], P.door));
    parts.push(block(WALL, 0.02, span, [x, 0, mid], P.metal));
  }

  // pictures on the inner walls (the outer walls' own are with them)
  parts.push(...place(picture(0.7, 0.9, P.picture[1]), CEO_OFFICE.maxX + WALL_HALF, -6.4, Math.PI / 2, 1.6));
  parts.push(...place(picture(0.6, 0.6, P.picture[2]), MEETING_ROOM.maxX - WALL_HALF, -6.2, -Math.PI / 2, 1.7));
  parts.push(...place(picture(0.6, 0.8, P.picture[3]), PANTRY.minX + WALL_HALF, -6.9, Math.PI / 2, 1.8));
  return parts;
}

/** The walls between the back rooms, one per x: they stand between things, so the 2D sorts them. */
const INNER_WALL_XS = [CEO_OFFICE.maxX, MEETING_ROOM.maxX] as const;
const INNER_WALL_DEPTH = BACK_ROOMS_Z - WALL_HALF - ROOM.minZ;

function innerWall(x: number): Part[] {
  return [
    block(WALL_HALF * 2, INNER_WALL_H, INNER_WALL_DEPTH, [x, 0, ROOM.minZ + INNER_WALL_DEPTH / 2], P.wall),
    box(WALL_HALF * 2 + 0.04, CAP, INNER_WALL_DEPTH, [x, INNER_WALL_H + CAP / 2, ROOM.minZ + INNER_WALL_DEPTH / 2], P.wallCap),
  ];
}

/** The back rooms' glass fronts (frames only; the panes are their own mesh), with their doors. */
const GLASS_FRONTS: readonly (readonly [number, number])[] = [
  [CEO_OFFICE.minX, CEO_OFFICE.maxX],
  [MEETING_ROOM.minX, MEETING_ROOM.maxX],
  [PANTRY.minX, PANTRY.maxX], // glassed in too (D-132)
];

function glassFront([from, to]: readonly [number, number]): Part[] {
  const parts: Part[] = [];
  const len = to - from;
  parts.push(box(len, 0.08, 0.12, [(from + to) / 2, INNER_WALL_H - 0.04, BACK_ROOMS_Z], P.mullion));
  parts.push(box(len, 0.06, 0.12, [(from + to) / 2, 0.03, BACK_ROOMS_Z], P.mullion));
  const posts = Math.ceil(len / 1.4);
  for (let i = 0; i <= posts; i++) parts.push(block(0.06, INNER_WALL_H, 0.12, [from + (i * len) / posts, 0, BACK_ROOMS_Z], P.mullion));
  return parts;
}

function doorsOf([from, to]: readonly [number, number]): Part[] {
  const parts: Part[] = [];
  for (const door of DOORS.filter((d) => d.x >= from && d.x <= to)) {
    for (const side of [-1, 1]) parts.push(block(0.08, 2.2, 0.16, [door.x + (side * door.width) / 2, 0, BACK_ROOMS_Z], P.door));
    parts.push(box(door.width + 0.16, 0.08, 0.16, [door.x, 2.24, BACK_ROOMS_Z], P.door));
  }
  for (const leafRect of doorLeaves().filter((l) => (l.minX + l.maxX) / 2 >= from - 1 && (l.minX + l.maxX) / 2 <= to + 1)) {
    const cz = (leafRect.minZ + leafRect.maxZ) / 2;
    parts.push(block(0.05, 2.15, leafRect.maxZ - leafRect.minZ, [(leafRect.minX + leafRect.maxX) / 2, 0.02, cz], P.door));
    parts.push(box(0.08, 0.04, 0.14, [(leafRect.minX + leafRect.maxX) / 2, 1.05, leafRect.minZ + 0.12], P.metal));
  }
  return parts;
}

/** The 3D office's merged architecture: the shell without its two tall walls (D-119). */
function architecture(): Part[] {
  return [
    ...shellCore(),
    ...INNER_WALL_XS.flatMap(innerWall),
    ...GLASS_FRONTS.flatMap((front) => [...glassFront(front), ...doorsOf(front)]),
  ];
}

/** Neon outlines around the zones' floors, in a theme that has them. */
function zoneTrims(): Part[] {
  const parts: Part[] = [];
  const areas = { ...ZONES, pantry: PANTRY };
  const t = 0.05;
  const y = 0.02;
  for (const [zone, colour] of Object.entries(P.zoneTrim ?? {})) {
    if (!colour) continue;
    const a = areas[zone as keyof typeof areas];
    const w = a.maxX - a.minX;
    const d = a.maxZ - a.minZ;
    const cx = (a.minX + a.maxX) / 2;
    const cz = (a.minZ + a.maxZ) / 2;
    parts.push(
      box(w, 0.01, t, [cx, y, a.minZ + t / 2], colour),
      box(w, 0.01, t, [cx, y, a.maxZ - t / 2], colour),
      box(t, 0.01, d - 2 * t, [a.minX + t / 2, y, cz], colour),
      box(t, 0.01, d - 2 * t, [a.maxX - t / 2, y, cz], colour),
    );
  }
  return parts;
}

// --- the whole office --------------------------------------------------------------------------

const DEFAULT_PALETTE = THEMES[DEFAULT_THEME].palette;

/** Everything static and opaque, merged into one mesh by the scene. */
export function officeParts(palette: Palette = DEFAULT_PALETTE): Part[] {
  return paintedWith(palette, () => [
    ...architecture(),
    ...BENCHES.flatMap((b) => benchTable(b.minX, b.maxX, b.z)),
    ...allSeats().flatMap(seatParts),
    ...DECOR.flatMap(decorParts),
    ...approvalDesk(),
    ...GLASS_WALLS.flatMap(glassWallFrame),
    ...serverFloor(),
    ...zoneTrims(),
  ]);
}

/** Window panes (a separate, softly glowing mesh). */
export function windowGlassParts(palette: Palette = DEFAULT_PALETTE, side?: OuterWall): Part[] {
  const pane = (w: number) => box(w - 0.08, WINDOW.height - 0.08, 0.02, [0, WINDOW.sill + WINDOW.height / 2, 0.03], palette.windowGlass);
  return [
    ...(side === "left" ? [] : BACK_WINDOWS.flatMap(([x, w]) => place([pane(w)], x, ROOM.minZ))),
    ...(side === "back" ? [] : LEFT_WINDOWS.flatMap(([z, w]) => place([pane(w)], ROOM.minX, z, Math.PI / 2))),
  ];
}

/** The glass of the back rooms' fronts (a separate, transparent mesh), doors left open. */
export function partitionGlassParts(palette: Palette = DEFAULT_PALETTE): Part[] {
  const P = palette;
  const h = INNER_WALL_H - 0.12;
  const segments: [number, number][] = [];
  for (const [room, door] of [
    [CEO_OFFICE, DOORS[0]],
    [MEETING_ROOM, DOORS[1]],
    [PANTRY, DOORS[2]],
  ] as const) {
    segments.push([room.minX, door.x - door.width / 2], [door.x + door.width / 2, room.maxX]);
  }
  const panes = segments.map(([from, to]) => box(to - from, h, 0.02, [(from + to) / 2, 0.06 + h / 2, BACK_ROOMS_Z], P.glass));
  // the transoms above the doors
  for (const door of DOORS) panes.push(box(door.width, INNER_WALL_H - 2.36, 0.02, [door.x, 2.28 + (INNER_WALL_H - 2.36) / 2, BACK_ROOMS_Z], P.glass));
  // the work row's glass walls (D-132): either side of each door, and above it
  const g = GLASS_HEIGHT - 0.06;
  const pane = (wall: GlassWall, from: number, to: number, y0: number, y1: number) =>
    box(
      wall.axis === "x" ? to - from : 0.02,
      y1 - y0,
      wall.axis === "x" ? 0.02 : to - from,
      wall.axis === "x" ? [(from + to) / 2, (y0 + y1) / 2, wall.at] : [wall.at, (y0 + y1) / 2, (from + to) / 2],
      P.glass,
    );
  for (const wall of GLASS_WALLS) {
    for (const [from, to] of glassSpans(wall)) panes.push(pane(wall, from, to, 0.06, g));
    if (wall.door) panes.push(pane(wall, wall.door.at - wall.door.width / 2, wall.door.at + wall.door.width / 2, 2.18, g));
  }
  return panes;
}

/** Floor regions, drawn by material (the procedural textures live in scene/textures.ts). */
export type { FloorKind };

export interface FloorRegion {
  kind: FloorKind;
  minX: number;
  maxX: number;
  minZ: number;
  maxZ: number;
  /** Stacking order: higher draws over lower (a few millimetres apart). */
  layer: number;
}

export function floorRegions(): FloorRegion[] {
  const full = { minX: ROOM.minX, maxX: ROOM.maxX };
  const room = (kind: FloorKind, r: { minX: number; maxX: number; minZ: number; maxZ: number }, layer: number): FloorRegion => ({
    kind,
    minX: r.minX,
    maxX: r.maxX,
    minZ: r.minZ,
    maxZ: r.maxZ,
    layer,
  });
  return [
    { kind: "base", ...full, minZ: ROOM.minZ, maxZ: ROOM.maxZ, layer: 0 },
    room("ceo", CEO_OFFICE, 1),
    room("meeting", MEETING_ROOM, 1),
    room("pantry", PANTRY, 1),
    room("research", ZONES.research, 1),
    room("editorial", ZONES.editorial, 1),
    room("growth", ZONES.growth, 1),
    room("spare", ZONES.spare, 1),
    room("lobby", ZONES.lobby, 1),
    { kind: "corridor", ...full, minZ: -3.2, maxZ: -1.3, layer: 2 },
    { kind: "corridor", ...full, minZ: 1.6, maxZ: 3.2, layer: 2 },
    { kind: "corridor", minX: SPINE.minX, maxX: SPINE.maxX, minZ: -1.3, maxZ: 1.6, layer: 2 },
    { kind: "rugLounge", minX: 8.8, maxX: 11.8, minZ: 4.1, maxZ: 7.5, layer: 3 },
    // no rug in the CEO office (D-119): the wood floor alone, with the desk by the window
    { kind: "entranceMat", minX: ROOM.maxX - 1.0, maxX: ROOM.maxX, minZ: ENTRANCE.minZ + 0.2, maxZ: ENTRANCE.maxZ - 0.2, layer: 3 },
  ];
}

// --- the pieces the 2D board bakes (D-026, D-027) ----------------------------------------------
//
// The 2D office is not drawn by hand any more, and it is not laid out by hand either. Each piece
// below is rendered once, from a fixed orthographic angle, into a pixel sprite
// (``tools/bake-sprites``), and ``placedPieces`` says where every one of them stands — read from
// the same seats, benches and decor list the 3D office is built from. The 2D board draws the 3D
// office's furniture in the 3D office's places; move a plant in layout.ts and it moves in both.
//
// Each piece is built around its own origin, standing on y = 0, already turned the way it stands
// in the office (the bake has one camera, so a sofa turned a quarter has to be baked turned).

export interface BakeablePiece {
  /**
   * ``accent`` is the colour that belongs to whoever uses the piece — a chair's stripes are its
   * sitter's role colour. The bake passes a probe for it, so the 2D board can repaint it per seat.
   */
  parts: (palette: Palette, accent: string) => Part[];
  /** Metres of floor it stands on, after turning: x across, z deep. Its front edge sorts it. */
  footprint: readonly [number, number];
}

/** One piece of furniture where it stands in the office. */
export interface PlacedPiece {
  /** Which baked sprite it is (a key of ``BAKEABLE``); every plain desk shares one. */
  bake: string;
  /** Where its origin stands on the floor, metres. */
  at: readonly [number, number];
  /** The seat it belongs to: a chair is painted in its sitter's colour, a desk lit by them. */
  seat?: string;
}

const deskSet = (desk: () => Part[]) => (p: Palette) => paintedWith(p, () => [...desk(), ...workstation(), ...lampBody()]);

/** The suffix of a baked piece turned round (D-119). */
const TURNED = ":turned";

/** The key of the office's shell in ``BAKEABLE``: baked as one piece, drawn first, never sorted. */
export const BACKDROP = "backdrop";

/** The floor as flat slabs, one per region, each a few millimetres above the one it covers. */
function floorParts(): Part[] {
  return floorRegions().map((r) =>
    box(r.maxX - r.minX, 0.004, r.maxZ - r.minZ, [(r.minX + r.maxX) / 2, r.layer * 0.004, (r.minZ + r.maxZ) / 2], P.floors[r.kind].color),
  );
}
const benchKey = (i: number) => `bench:${i}`;
const decorKey = (i: number, item: Decor) => `decor:${i}:${item.kind}`;

export const BAKEABLE: Record<string, BakeablePiece> = {
  desk: { parts: deskSet(singleDesk), footprint: [DESK.width, DESK.depth] },
  execDesk: { parts: deskSet(execDesk), footprint: [DESK.width + 0.2, DESK.depth + 0.1] },
  // a seat at a bench has no desk of its own: the bench is the desk, baked once for the row
  benchSeat: { parts: deskSet(() => []), footprint: [DESK.width, DESK.depth] },
  chair: { parts: (p, accent) => paintedWith(p, () => officeChair(accent)), footprint: [0.6, 0.6] },
  chairTall: { parts: (p, accent) => paintedWith(p, () => officeChair(accent, true)), footprint: [0.6, 0.6] },
  // the CEO's desk and chair turned round to face her door (D-119)
  [`execDesk${TURNED}`]: {
    parts: (p) => paintedWith(p, () => place([...execDesk(), ...workstation(), ...lampBody()], 0, 0, Math.PI)),
    footprint: [DESK.width + 0.2, DESK.depth + 0.1],
  },
  [`chairTall${TURNED}`]: {
    parts: (p, accent) => paintedWith(p, () => place(officeChair(accent, true), 0, 0, Math.PI)),
    footprint: [0.6, 0.6],
  },
  [BACKDROP]: {
    // everything that never stands in front of anything, in one piece: floors, the shell, the
    // window panes, and the zone trims of the styles that have them
    parts: (p) => paintedWith(p, () => [...floorParts(), ...shell(), ...zoneTrims(), ...windowGlassParts(p)]),
    footprint: [ROOM.maxX - ROOM.minX + WALL * 2, ROOM.maxZ - ROOM.minZ + WALL * 2],
  },
  ...Object.fromEntries(
    INNER_WALL_XS.map((x, i) => [
      `wall:${i}`,
      {
        parts: (p: Palette) => paintedWith(p, () => place(innerWall(x), -x, -(ROOM.minZ + INNER_WALL_DEPTH / 2))),
        footprint: [WALL_HALF * 2, INNER_WALL_DEPTH] as const,
      },
    ]),
  ),
  ...Object.fromEntries(
    GLASS_FRONTS.map((front, i) => [
      `front:${i}`,
      {
        parts: (p: Palette) =>
          paintedWith(p, () => place([...glassFront(front), ...doorsOf(front)], -(front[0] + front[1]) / 2, -BACK_ROOMS_Z)),
        footprint: [front[1] - front[0], 0.16] as const,
      },
    ]),
  ),
  counterDesk: {
    // approvalDesk() builds itself where it stands; bring it back to the origin. Turned round
    // (D-120), its chair is behind it, so the counter's front is the footprint's front.
    parts: (p) => paintedWith(p, () => place(approvalDesk(), -APPROVAL_DESK.center[0], -APPROVAL_DESK.center[1])),
    footprint: [APPROVAL_FOOTPRINT[0] + 0.1, APPROVAL_FOOTPRINT[1]],
  },
  ...Object.fromEntries(
    BENCHES.map((b, i) => [
      benchKey(i),
      {
        parts: (p: Palette) => paintedWith(p, () => place(benchTable(b.minX, b.maxX, b.z), -(b.minX + b.maxX) / 2, -b.z)),
        footprint: [b.maxX - b.minX, DESK.depth] as const,
      },
    ]),
  ),
  // the work row's glass walls (D-132)
  ...Object.fromEntries(
    GLASS_WALLS.map((wall, i) => {
      const [cx, cz] = wallCentre(wall);
      const length = wall.to - wall.from;
      return [
        `glass:${i}`,
        {
          parts: (p: Palette) => paintedWith(p, () => place(glassWallFrame(wall), -cx, -cz)),
          footprint: (wall.axis === "x" ? [length, 0.12] : [0.12, length]) as readonly [number, number],
        },
      ];
    }),
  ),
  ...Object.fromEntries(
    DECOR.map((item, i) => [
      decorKey(i, item),
      {
        parts: (p: Palette) => paintedWith(p, () => place(decorBuild(item, i), 0, 0, item.rotY)),
        footprint: item.size,
      },
    ]),
  ),
};

/** Every piece of furniture in the office, where the 3D office puts it. */
export function placedPieces(): PlacedPiece[] {
  const pieces: PlacedPiece[] = [];
  for (const seat of allSeats()) {
    const ceo = seat.role === "ceo";
    const turned = seat.turn ? TURNED : ""; // a desk turned round has its own sprites (D-119)
    pieces.push({ bake: (seat.bench ? "benchSeat" : ceo ? "execDesk" : "desk") + turned, at: seat.desk, seat: seat.key });
    pieces.push({ bake: (ceo ? "chairTall" : "chair") + turned, at: seat.chair, seat: seat.key });
  }
  BENCHES.forEach((b, i) => pieces.push({ bake: benchKey(i), at: [(b.minX + b.maxX) / 2, b.z] }));
  DECOR.forEach((item, i) => pieces.push({ bake: decorKey(i, item), at: item.at }));
  pieces.push({ bake: "counterDesk", at: APPROVAL_DESK.center });
  INNER_WALL_XS.forEach((x, i) => pieces.push({ bake: `wall:${i}`, at: [x, ROOM.minZ + INNER_WALL_DEPTH / 2] }));
  GLASS_FRONTS.forEach((front, i) => pieces.push({ bake: `front:${i}`, at: [(front[0] + front[1]) / 2, BACK_ROOMS_Z] }));
  GLASS_WALLS.forEach((wall, i) => pieces.push({ bake: `glass:${i}`, at: wallCentre(wall) }));
  return pieces;
}
