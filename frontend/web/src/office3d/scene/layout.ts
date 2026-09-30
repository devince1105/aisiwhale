// The office floor plan (T-402, 3d-office/04 §2, D-010): the only source of coordinates. Desks,
// avatars, decoration, courier walks (T-408) and camera focus (T-409) all read it. The desks are
// a visual setting; who sits at one is company data.
//
// **A department decides the room, not a role** (T-600 batch 3, ARCHITECTURE_V2 §14.7). An agent
// is seated in the zone its department names (`departments.office_zone_key`, carried on the
// stream as `office_zone_key`); within that zone it prefers the desk built for its role, so a
// newsroom looks exactly as it was drawn while the rule underneath is organisational. A company
// with no org chart yet falls back to the role's own zone, which is where v1 put it.
//
// Units are metres; x runs left to right, z from the back wall (-z) to the front (+z). The camera
// looks from the front right, so the back and left walls are full height and the front and right
// edges are a low rim (a cut-away diorama).
//
//   z=-8 ┌── CEO office ──┬──── meeting room ────┬──── pantry ─────┐
//        │ (glass front)  │ (glass front)        │ (open)          │
//   z=-3.2├──door─────────┴──────door────────────┘                 │
//        │ ═══════════════ back corridor (lane z=-2.25) ══════════ │
//   z=0  │ [ni][res][ana][ana]  spine x=0  [flex][flex][flex]  [reception]│  bench desks
//        │ ═══════════════ front corridor (lane z=2.4) ═══════════ │
//        │                                                 entrance ◁ (T-413)
//   z=4.6│▓ [r&d][mkt][mkt] ▒ [wri][edi][eic] ✿        lounge  │  single desks; lobby
//        │▓ (▓ the server room along the left wall; ✿ low planters)│
//
// Where things stand follows the usual feng-shui rules of an office (D-120): the CEO in the
// corner furthest from the entrance, a solid wall behind her and her door in view; the reception
// by the entrance, where it sees who comes in without standing in the door's straight line, with
// its chair behind the counter and open floor around it; the flex desks, whose sitters come and
// go, nearest the door; the editorial desk, the newsroom's own, in the front row with the wall at
// its back; and nothing in the entrance's line or doorway. R&D is the innermost desk of the front
// row, next to the server room (D-121, D-122).
//   z=8  └──────────────────────────────────────────────────────────┘
//      x=-12                                                     x=12

export type Vec2 = readonly [x: number, z: number];
export type Vec3 = readonly [x: number, y: number, z: number];
export type ZoneId = "ceo" | "research" | "editorial" | "growth" | "spare";
export type Lane = "front" | "back";

export const ROOM = { minX: -12, maxX: 12, minZ: -8, maxZ: 8, wallHeight: 3 } as const;

export const DESK = { width: 1.5, depth: 0.8, height: 0.75 } as const;
export const CHAIR = { size: 0.6 } as const;
/** How far behind the desk the chair stands; the seated agent faces -z (its monitors). */
const CHAIR_OFFSET = 0.95;
/** Where a visitor stands: beside the seated agent, to its right (left against the right wall). */
const APPROACH_OFFSET: Vec2 = [1.1, 0];

export const LANES: Record<Lane, number> = { back: -2.25, front: 2.4 };
/** The aisle between the two benches that joins the lanes. */
export const SPINE_X = -3.4;

/** Rooms along the back wall; their fronts are at z = BACK_ROOMS_Z. */
export const BACK_ROOMS_Z = -3.2;
export const CEO_OFFICE = { minX: -12, maxX: -5, minZ: -8, maxZ: BACK_ROOMS_Z, doorX: -7.4, doorWidth: 1.2 } as const;
export const MEETING_ROOM = { minX: -5, maxX: 4, minZ: -8, maxZ: BACK_ROOMS_Z, doorX: 2.6, doorWidth: 1.2 } as const;
/** Glassed in like the others (D-132), its door toward the work row's right half. */
export const PANTRY = { minX: 4, maxX: 12, minZ: -8, maxZ: BACK_ROOMS_Z, doorX: 6.4, doorWidth: 1.2 } as const;
/** The walkways between the zones. */
export const CORRIDORS = {
  back: { minZ: BACK_ROOMS_Z, maxZ: -1.3 },
  front: { minZ: 1.6, maxZ: 3.2 },
} as const;

/** The way in (T-413): an opening in the right edge where the front corridor meets it. */
export const ENTRANCE = { x: ROOM.maxX, minZ: CORRIDORS.front.minZ, maxZ: CORRIDORS.front.maxZ } as const;

export interface Area {
  minX: number;
  maxX: number;
  minZ: number;
  maxZ: number;
}

/**
 * The open-plan zones, each with its own floor (T-413): a carpet per department, and the lobby —
 * reception (the approval desk) and the waiting lounge — by the entrance.
 */
export const ZONES: Record<"research" | "editorial" | "growth" | "spare" | "lobby", Area> = {
  research: { minX: -10.6, maxX: -3.8, minZ: CORRIDORS.back.maxZ, maxZ: CORRIDORS.front.minZ },
  // the flex desks and the editorial desk changed places (D-120): flex in the work row,
  // editorial in the front row, the wall behind it; the flex desks a bench in line with
  // research's across the aisle, behind the glass (D-132)
  spare: { minX: -2.95, maxX: 4.0, minZ: CORRIDORS.back.maxZ, maxZ: CORRIDORS.front.minZ },
  growth: { minX: -10.4, maxX: -3.8, minZ: CORRIDORS.front.maxZ, maxZ: 6.6 },
  editorial: { minX: -2.6, maxX: 3.9, minZ: CORRIDORS.front.maxZ, maxZ: 6.6 },
  lobby: { minX: 4.2, maxX: ROOM.maxX, minZ: CORRIDORS.front.maxZ, maxZ: ROOM.maxZ },
};

/** The approval desk doubles as the reception counter. It stands in the waiting area, just past
 * the glass (D-132): the counter runs front to back and faces the lounge and the entrance, its
 * chair on the inside, by the glass. ``turn`` is its rotation about y: its visitor side faces +x. */
export const APPROVAL_DESK = { center: [5.7, 5.3] as Vec2, width: 2.2, depth: 0.9, turn: -Math.PI / 2, approach: [6.65, 5.3] as Vec2 } as const;
/** The counter's footprint on the floor, x by z (it runs along z). */
export const APPROVAL_FOOTPRINT: Vec2 = [APPROVAL_DESK.depth, APPROVAL_DESK.width];

interface RoleSlots {
  zone: ZoneId;
  lane: Lane;
  /** Desks joined into one bench table (drawn and walked around as one). */
  bench: boolean;
  /** Desk centres; the first is the seat a single agent of this role gets. */
  desks: Vec2[];
  /** The desk turned round (D-119): its sitter faces the room's front (+z) — the CEO facing her
   * office's door — instead of the back wall. One flag for every desk, or one per desk (a pair
   * of desks facing each other, D-132). */
  turned?: boolean | readonly boolean[];
}

function isTurned(slots: RoleSlots, index: number): boolean {
  return Array.isArray(slots.turned) ? Boolean(slots.turned[index]) : Boolean(slots.turned);
}

const WORK_Z = 0;
const FRONT_Z = 4.6;

/** Desks per role, in the order they are filled. Capacity = number of desks. */
export const SLOTS: Record<string, RoleSlots> = {
  // every member of the newsroom has a desk of her own (D-120), so no one takes another's
  news_intelligence: { zone: "research", lane: "front", bench: true, desks: [[-9.0, WORK_Z]] },
  researcher: { zone: "research", lane: "front", bench: true, desks: [[-6.8, WORK_Z]] },
  analyst: { zone: "research", lane: "front", bench: true, desks: [[-4.6, WORK_Z]] },
  // the editorial desk in the front row, in the order a story passes along it
  writer: { zone: "editorial", lane: "front", bench: false, desks: [[-1.8, FRONT_Z]] },
  editor: { zone: "editorial", lane: "front", bench: false, desks: [[0.4, FRONT_Z]] },
  editor_in_chief: { zone: "editorial", lane: "front", bench: false, desks: [[2.6, FRONT_Z]] },
  marketing: { zone: "growth", lane: "front", bench: false, desks: [[-6.8, FRONT_Z], [-4.6, FRONT_Z]] },
  // a desk kept for R&D beside marketing (D-120), the innermost of the row with the server room
  // behind it (D-121): empty until the company has an engineer
  engineer: { zone: "growth", lane: "front", bench: false, desks: [[-9.0, FRONT_Z]] },
  // by the CEO office's window on the left wall, turned to face her door (D-119): seen from the
  // camera she is framed by the glass front, not hidden behind the door's frame
  ceo: { zone: "ceo", lane: "back", bench: false, desks: [[-10.4, -6.0]], turned: true },
};

/**
 * The office divided on the line of the pantry's wall (x ≈ 4) by a glass wall the whole depth
 * of the room, open where the two walkways cross it (D-132): the desks on one side; on the
 * other, the waiting area with the reception in the front row, and in the work row three glass
 * rooms — two small meeting rooms of one size, and the server room by the entrance, its
 * racks the system itself (D-121). Their doors open onto the back walkway, inside the company,
 * not onto the waiting area: what is discussed and kept there is not a visitor's to walk into.
 */
export const DIVIDER_X = 4.15;
/** Their fronts stand just back from the walkway, so the entrance's doorway stays clear. */
const ROOMS_FRONT_Z = CORRIDORS.front.minZ - 0.15;
const ROOMS_BACK_Z = CORRIDORS.back.maxZ;
/** Two small meeting rooms of one size, for two (a table on the diagonal, a chair at each end);
 * what is left of the row goes to the server room. */
const SMALL_ROOM_WIDTH = 2.3;
export const SMALL_MEETING = { minX: DIVIDER_X, maxX: DIVIDER_X + SMALL_ROOM_WIDTH, minZ: ROOMS_BACK_Z, maxZ: ROOMS_FRONT_Z, doorX: DIVIDER_X + SMALL_ROOM_WIDTH / 2, doorWidth: 0.9 } as const;
export const TALK_ROOM = { minX: SMALL_MEETING.maxX, maxX: SMALL_MEETING.maxX + SMALL_ROOM_WIDTH, minZ: ROOMS_BACK_Z, maxZ: ROOMS_FRONT_Z, doorX: SMALL_MEETING.maxX + SMALL_ROOM_WIDTH / 2, doorWidth: 0.9 } as const;
export const SERVER_ROOM = { minX: TALK_ROOM.maxX, maxX: ROOM.maxX, minZ: ROOMS_BACK_Z, maxZ: ROOMS_FRONT_Z, doorX: 10.9, doorWidth: 0.7 } as const;
/** Two rows of three, fronts facing each other across the aisle the door opens onto. */
export const SERVER_RACKS = {
  rows: [
    { x: 11.55, facing: -1 },
    { x: 10.25, facing: 1 },
  ],
  zs: [-0.6, 0.05, 0.7],
  width: 0.6,
  depth: 0.6,
  height: 1.6,
} as const;

/** A glass wall (D-132): along x (``z`` fixed) or along z (``x`` fixed), with an optional door. */
export interface GlassWall {
  name: string;
  axis: "x" | "z";
  /** The fixed coordinate: z for a wall along x, x for a wall along z. */
  at: number;
  from: number;
  to: number;
  door?: { at: number; width: number };
}

export const GLASS_HEIGHT = 2.4;

const back = (room: { doorX: number; doorWidth: number }) => ({ at: room.doorX, width: room.doorWidth });

export const GLASS_WALLS: GlassWall[] = [
  // the divider: the work row, and the front row where the planters were
  { name: "divider glass", axis: "z", at: DIVIDER_X, from: CORRIDORS.back.maxZ, to: CORRIDORS.front.minZ },
  { name: "divider glass (front row)", axis: "z", at: DIVIDER_X, from: CORRIDORS.front.maxZ, to: ROOM.maxZ },
  // the three rooms: fronts closed, doors at the back
  { name: "small meeting front", axis: "x", at: SMALL_MEETING.maxZ, from: SMALL_MEETING.minX, to: SMALL_MEETING.maxX },
  { name: "small meeting back", axis: "x", at: SMALL_MEETING.minZ, from: SMALL_MEETING.minX, to: SMALL_MEETING.maxX, door: back(SMALL_MEETING) },
  { name: "small meeting | talk", axis: "z", at: TALK_ROOM.minX, from: TALK_ROOM.minZ, to: TALK_ROOM.maxZ },
  { name: "talk front", axis: "x", at: TALK_ROOM.maxZ, from: TALK_ROOM.minX, to: TALK_ROOM.maxX },
  { name: "talk back", axis: "x", at: TALK_ROOM.minZ, from: TALK_ROOM.minX, to: TALK_ROOM.maxX, door: back(TALK_ROOM) },
  { name: "talk | server", axis: "z", at: SERVER_ROOM.minX, from: SERVER_ROOM.minZ, to: SERVER_ROOM.maxZ },
  { name: "server front", axis: "x", at: SERVER_ROOM.maxZ, from: SERVER_ROOM.minX, to: SERVER_ROOM.maxX },
  { name: "server back", axis: "x", at: SERVER_ROOM.minZ, from: SERVER_ROOM.minX, to: SERVER_ROOM.maxX, door: back(SERVER_ROOM) },
];

/** Desks for roles the floor plan does not know (a new domain's roles), first come first served:
 * a bench in line with research's, across the aisle that joins the walkways (D-132). */
export const SPARE: RoleSlots = { zone: "spare", lane: "front", bench: true, desks: [[-2.2, WORK_Z], [0.0, WORK_Z], [2.2, WORK_Z]] };

export const ROLES = Object.keys(SLOTS);

/** The two bench tables of the work row, research's and the flex desks', in one line with the
 * aisle between them (D-132). */
export const BENCHES = [
  { name: "research bench", minX: -9.75, maxX: -3.85, z: WORK_Z },
  { name: "flex bench", minX: -2.95, maxX: 2.95, z: WORK_Z },
] as const;

/** The aisle from the back wall's walkway to the front of the room, through both rows, between
 * research and the flex desks and between marketing and editorial (D-132): where people cross. */
export const SPINE = { minX: -3.8, maxX: -2.95 } as const;

export interface Seat {
  key: string;
  role: string;
  zone: ZoneId;
  lane: Lane;
  bench: boolean;
  desk: Vec2;
  chair: Vec2;
  /** Rotation about y for the seated avatar: it faces its monitors (-z; +z at a turned desk). */
  facing: number;
  /** The desk's own turn about y: 0, or π at a turned desk (D-119). Everything placed around a
   * desk — chair, screens, lamp, where one stands up — turns with it. */
  turn: number;
  /** Centre between the seat's two monitors. */
  screen: Vec3;
  /** Where a visitor stops next to this seat. */
  approach: Vec2;
}

function seatAt(role: string, slots: RoleSlots, index: number): Seat {
  const [x, z] = slots.desks[index];
  const turned = isTurned(slots, index);
  const turn = turned ? Math.PI : 0;
  const back = turned ? -1 : 1; // which way the chair is from the desk
  const chair: Vec2 = [x, z + back * CHAIR_OFFSET];
  const side = x + APPROACH_OFFSET[0] > ROOM.maxX - 1 ? -1 : 1;
  return {
    key: `${slots.zone}:${role}:${index}`,
    role,
    zone: slots.zone,
    lane: slots.lane,
    bench: slots.bench,
    desk: [x, z],
    chair,
    facing: turned ? 0 : Math.PI,
    turn,
    screen: [x, DESK.height + 0.3, z - back * 0.18],
    approach: [chair[0] + side * APPROACH_OFFSET[0], chair[1] + APPROACH_OFFSET[1]],
  };
}

/** Every seat of a zone, in the order they are filled: the desks built for its roles first. */
export function seatsInZone(zone: ZoneId): Seat[] {
  const own = Object.entries(SLOTS)
    .filter(([, slots]) => slots.zone === zone)
    .sort(([a], [b]) => a.localeCompare(b))
    .flatMap(([role, slots]) => slots.desks.map((_, i) => seatAt(role, slots, i)));
  return zone === SPARE.zone ? [...own, ...SPARE.desks.map((_, i) => seatAt("spare", SPARE, i))] : own;
}

export const ZONE_OF_ROLE: Record<string, ZoneId> = Object.fromEntries(
  Object.entries(SLOTS).map(([role, slots]) => [role, slots.zone]),
);

/** Up to `n` seats for a role (fewer when its area is full). */
export function seatsForRole(role: string, n: number): Seat[] {
  const slots = SLOTS[role];
  if (!slots) return [];
  return Array.from({ length: Math.min(n, slots.desks.length) }, (_, i) => seatAt(role, slots, i));
}

export interface Assignment {
  seats: Map<string, Seat>;
  /** Agents with no desk left (shown on the 2D board and in lists, not in the room). */
  unseated: string[];
}

/** Anyone the office can seat: the runtime's role, and the department's place on the floor. */
export interface Seatable {
  id: string;
  role: string;
  office_zone_key?: string | null;
}

const ZONE_IDS = new Set<string>(Object.values(SLOTS).map((s) => s.zone).concat(SPARE.zone));

/** Which part of the floor an agent belongs in: its department's, or its role's, or spare. */
export function zoneOf(agent: Seatable): ZoneId {
  const named = agent.office_zone_key;
  if (named && ZONE_IDS.has(named)) return named as ZoneId;
  return ZONE_OF_ROLE[agent.role] ?? SPARE.zone;
}

/**
 * Seat every agent in its department's zone. Stable: the same roster gives the same desks.
 *
 * Within a zone the desk built for the agent's role is taken first, so a company whose
 * departments match the drawn floor looks exactly as it was designed. Anyone left over takes
 * another free desk in the same zone, then a flex desk, and only then goes unseated — which is
 * a real state, not a bug: it is shown in the lists and on the 2D board.
 */
export function assignSeats(agents: readonly Seatable[]): Assignment {
  const seats = new Map<string, Seat>();
  const unseated: string[] = [];
  const taken = new Set<string>();
  const free = new Map<ZoneId, Seat[]>();
  const zoneSeats = (zone: ZoneId): Seat[] => {
    if (!free.has(zone)) free.set(zone, seatsInZone(zone));
    return free.get(zone)!;
  };
  const claim = (zone: ZoneId, role: string): Seat | undefined => {
    const available = zoneSeats(zone).filter((seat) => !taken.has(seat.key));
    const seat = available.find((s) => s.role === role) ?? available[0];
    if (seat) taken.add(seat.key);
    return seat;
  };

  const ordered = [...agents].sort(
    (a, b) => a.role.localeCompare(b.role) || a.id.localeCompare(b.id),
  );
  for (const agent of ordered) {
    const seat = claim(zoneOf(agent), agent.role) ?? claim(SPARE.zone, agent.role);
    if (seat) seats.set(agent.id, { ...seat, role: agent.role });
    else unseated.push(agent.id);
  }
  return { seats, unseated };
}

/** Every desk the room has, for drawing furniture (occupied or not). */
export function allSeats(): Seat[] {
  return [
    ...Object.entries(SLOTS).flatMap(([role, slots]) => slots.desks.map((_, i) => seatAt(role, slots, i))),
    ...SPARE.desks.map((_, i) => seatAt("spare", SPARE, i)),
  ];
}

// --- decoration -------------------------------------------------------------------------------

export type DecorKind =
  | "low_shelf"
  | "palm"
  | "plant"
  | "lounge"
  | "meeting_set"
  | "whiteboard"
  | "pantry_counter"
  | "fridge"
  | "vending"
  | "water_cooler"
  | "cafe_table"
  | "ceo_shelf"
  | "ceo_sofa"
  | "planter"
  | "server_racks"
  | "small_meeting";

export interface Decor {
  kind: DecorKind;
  at: Vec2;
  /** Rotation about y (radians). */
  rotY: number;
  /** Footprint on the floor (x/z after rotation), for walking around it. */
  size: Vec2;
}

const d = (kind: DecorKind, at: Vec2, size: Vec2, rotY = 0): Decor => ({ kind, at, size, rotY });
const QUARTER = Math.PI / 2;

/** Fixed pieces that carry no state. Anything a walker could bump into is listed here. */
export const DECOR: Decor[] = [
  // work area: low shelves with plants along the left wall, palms and plants at the ends
  d("low_shelf", [-11.6, -0.2], [0.45, 2.2], QUARTER),
  d("palm", [-11.2, 2.4], [0.8, 0.8]),
  // front area: a planter between marketing and the flex desks; the lobby by the entrance
  // the left wall's front row is open again (the server room moved, D-132): a shelf, a plant
  d("low_shelf", [-11.6, 6.9], [0.45, 1.8], QUARTER),
  d("plant", [-11.4, 3.7], [0.6, 0.6]),
  // (the planters between marketing and editorial, and along the waiting area, gave way to the
  // aisle and the glass, D-132)
  // the server room's racks (D-121), two rows facing each other by the entrance (D-132)
  ...SERVER_RACKS.rows.map((row) =>
    d(
      "server_racks",
      [row.x, (SERVER_RACKS.zs[0] + SERVER_RACKS.zs[SERVER_RACKS.zs.length - 1]) / 2],
      [SERVER_RACKS.depth, SERVER_RACKS.zs[SERVER_RACKS.zs.length - 1] - SERVER_RACKS.zs[0] + SERVER_RACKS.width],
      row.facing < 0 ? QUARTER : -QUARTER,
    ),
  ),
  // the two small meeting rooms' tables, each with two chairs on the room's diagonal
  d("small_meeting", [(SMALL_MEETING.minX + SMALL_MEETING.maxX) / 2, 0.1], [1.9, 1.9]),
  d("small_meeting", [(TALK_ROOM.minX + TALK_ROOM.maxX) / 2, 0.1], [1.9, 1.9]),
  d("lounge", [10.3, 5.8], [3.2, 3.6]),
  d("plant", [11.5, 3.6], [0.6, 0.6]),
  // CEO office
  d("ceo_shelf", [-8.0, -7.6], [2.2, 0.5]),
  d("ceo_sofa", [-5.7, -5.8], [0.9, 2.0], -QUARTER),
  d("plant", [-11.4, -3.8], [0.6, 0.6]),
  // meeting room
  // the table points at the projection screen on the back wall (D-120)
  d("meeting_set", [-0.8, -5.4], [2.5, 3.7], QUARTER),
  d("whiteboard", [-4.3, -4.4], [0.6, 1.6], QUARTER),
  d("plant", [3.5, -7.5], [0.6, 0.6]),
  // pantry
  d("pantry_counter", [6.4, -7.65], [4.2, 0.7]),
  d("fridge", [9.0, -7.55], [0.9, 0.8]),
  d("vending", [4.55, -4.4], [0.9, 1.0], QUARTER),
  d("water_cooler", [4.45, -5.6], [0.45, 0.45], QUARTER),
  d("cafe_table", [8.6, -5.4], [2.4, 2.4]),
  d("plant", [11.5, -3.7], [0.6, 0.6]),
];

/** Words on the floor and signs on the glass fronts that name the zones and rooms (T-413). */
export interface Label {
  text: string;
  /** A second, smaller line (English). */
  sub: string;
  /** Centre; y is the height of a sign (0: painted on the floor). */
  at: Vec3;
  /** Width in metres (height is a quarter of it). */
  width: number;
  /** Painted on the floor, or a sign facing +z (the glass fronts) or +x (the entrance). */
  kind: "floor" | "sign";
  facing?: "z" | "x";
}

export const LABELS: Label[] = [
  { text: "研究部", sub: "RESEARCH", at: [-6.0, 0, 2.0], width: 3.0, kind: "floor" },
  { text: "彈性座位", sub: "FLEX DESKS", at: [0.0, 0, 2.0], width: 2.2, kind: "floor" },
  { text: "接待", sub: "RECEPTION", at: [7.4, 0, 3.8], width: 1.6, kind: "floor" },
  // behind the front desks' chairs: in front of the desks the desks would hide them
  { text: "研發部", sub: "R&D", at: [-9.0, 0, 6.3], width: 2.0, kind: "floor" },
  { text: "行銷部", sub: "MARKETING", at: [-5.7, 0, 6.3], width: 2.4, kind: "floor" },
  { text: "編輯部", sub: "EDITORIAL", at: [0.4, 0, 6.3], width: 2.4, kind: "floor" },
  // the rooms of the work row's nameplates, on their fronts (their doors are at the back, D-132)
  { text: "小會議室 1", sub: "HUDDLE ROOM 1", at: [(SMALL_MEETING.minX + SMALL_MEETING.maxX) / 2, 2.36, SMALL_MEETING.maxZ + 0.08], width: 1.0, kind: "sign" },
  { text: "小會議室 2", sub: "HUDDLE ROOM 2", at: [(TALK_ROOM.minX + TALK_ROOM.maxX) / 2, 2.36, TALK_ROOM.maxZ + 0.08], width: 1.0, kind: "sign" },
  { text: "機房", sub: "SERVER ROOM", at: [(SERVER_ROOM.minX + SERVER_ROOM.maxX) / 2, 2.36, SERVER_ROOM.maxZ + 0.08], width: 1.0, kind: "sign" },
  { text: "等候區", sub: "LOUNGE", at: [6.4, 0, 7.05], width: 2.6, kind: "floor" },
  { text: "茶水間", sub: "PANTRY", at: [9.6, 2.5, BACK_ROOMS_Z + 0.08], width: 1.6, kind: "sign" },
  { text: "總經理室", sub: "CEO OFFICE", at: [-5.95, 2.5, BACK_ROOMS_Z + 0.08], width: 1.6, kind: "sign" },
  { text: "會議室", sub: "MEETING ROOM", at: [0.6, 2.5, BACK_ROOMS_Z + 0.08], width: 1.6, kind: "sign" },
  { text: "AUTORA", sub: "入口 ENTRANCE", at: [ROOM.maxX + 0.21, 2.6, (CORRIDORS.front.minZ + CORRIDORS.front.maxZ) / 2], width: 1.4, kind: "sign", facing: "x" },
];

/** The doors in the glass fronts (open, the leaf swung into the room on the hinge side). */
export const DOORS = [
  { name: "ceo door", x: CEO_OFFICE.doorX, width: CEO_OFFICE.doorWidth },
  { name: "meeting door", x: MEETING_ROOM.doorX, width: MEETING_ROOM.doorWidth },
  { name: "pantry door", x: PANTRY.doorX, width: PANTRY.doorWidth },
] as const;

// --- walking ----------------------------------------------------------------------------------

export type WalkTarget = Seat | "approval" | { door: string };

/**
 * Where a department is entered from the corridor: the middle of its edge, on the lane that
 * runs past it (T-600 batch 4).
 *
 * The key comes from the server (a department's ``office_zone_key``), so it may name a room
 * this floor does not draw; that falls back to the middle of the walkway, which is where
 * somebody with nowhere to go would in fact stand.
 *
 * A courier carrying work to another department stops here rather than at somebody's desk.
 * That is not only an animation choice: the work goes to whichever colleague claims it next,
 * so walking to one particular desk would draw a hand-over that is not what happened.
 */
export function doorOf(zone: string): { point: Vec2; lane: Lane } {
  if (zone === "ceo") {
    // the one room with an actual door: the opening in its glass front
    return { point: [CEO_OFFICE.doorX, BACK_ROOMS_Z + 0.5], lane: "back" };
  }
  const area = ZONES[zone as keyof typeof ZONES];
  if (!area) return { point: [SPINE_X, LANES.front], lane: "front" };
  const middle = (area.minX + area.maxX) / 2;
  // every open-plan zone opens onto the front corridor: the work row from its front edge, the
  // rest from their back edge, both stopping just inside the walkway
  const inCorridor = area.maxZ <= CORRIDORS.front.minZ ? area.maxZ + 0.6 : area.minZ - 0.6;
  return { point: [middle, inCorridor], lane: "front" };
}

function approachOf(target: WalkTarget): { point: Vec2; lane: Lane } {
  if (target === "approval") return { point: APPROVAL_DESK.approach, lane: "front" };
  if ("door" in target) return doorOf(target.door);
  return { point: target.approach, lane: target.lane };
}

/**
 * The courier's route (T-408): up from the chair, out to the lane, along the lanes (changing
 * lanes on the spine), and in to the target's approach point. Walk it backwards to return.
 */
export function walkPath(from: Seat, to: WalkTarget): Vec2[] {
  const start = approachOf(from);
  const end = approachOf(to);
  // a seat in the room with a door is left and reached through it (D-119: the CEO's desk is by
  // her window, not in line with her door)
  const outOf = doorway(from, start.point);
  const into = typeof to === "object" && "key" in to ? doorway(to, end.point) : null;
  const points: Vec2[] = [from.chair, start.point, ...outOf, [(outOf.at(-1) ?? start.point)[0], LANES[start.lane]]];
  if (start.lane !== end.lane) points.push([SPINE_X, LANES[start.lane]], [SPINE_X, LANES[end.lane]]);
  const entry = into ? [...into].reverse() : [];
  points.push([(entry[0] ?? end.point)[0], LANES[end.lane]], ...entry, end.point);
  return points.filter((p, i) => i === 0 || p[0] !== points[i - 1][0] || p[1] !== points[i - 1][1]);
}

/** From a seat in the CEO office out through its door, at right angles: from beside the seat
 * (``approach``) toward the front of the room, across to the door, and out. */
function doorway(seat: Seat, approach: Vec2): Vec2[] {
  if (seat.zone !== "ceo") return [];
  // across the room beyond the open door leaf, which swings in along the hinge side
  const inside = BACK_ROOMS_Z - WALL_HALF - CEO_OFFICE.doorWidth - 0.4;
  return [
    [approach[0], inside],
    [CEO_OFFICE.doorX, inside],
    [CEO_OFFICE.doorX, BACK_ROOMS_Z + 0.5],
  ];
}

/** Axis-aligned footprints of everything a walker must go around (x/z rectangles). */
export interface Rect {
  name: string;
  minX: number;
  maxX: number;
  minZ: number;
  maxZ: number;
}

export function rectAround([x, z]: Vec2, width: number, depth: number, name: string): Rect {
  return { name, minX: x - width / 2, maxX: x + width / 2, minZ: z - depth / 2, maxZ: z + depth / 2 };
}

/** Half the thickness of interior walls and glass fronts. */
export const WALL_HALF = 0.1;

/** Interior walls and glass fronts, with their door openings left out. */
export function partitions(): Rect[] {
  const z = BACK_ROOMS_Z;
  const t = WALL_HALF;
  const glass = (from: number, to: number, name: string): Rect => ({ name, minX: from, maxX: to, minZ: z - t, maxZ: z + t });
  const opening = (door: { doorX: number; doorWidth: number }) => [door.doorX - door.doorWidth / 2, door.doorX + door.doorWidth / 2];
  const [ceoL, ceoR] = opening(CEO_OFFICE);
  const [meetL, meetR] = opening(MEETING_ROOM);
  const [pantryL, pantryR] = opening(PANTRY);
  const wall = (x: number, name: string): Rect => ({ name, minX: x - t, maxX: x + t, minZ: ROOM.minZ, maxZ: z - t });
  return [
    glass(CEO_OFFICE.minX, ceoL, "ceo glass (left of door)"),
    glass(ceoR, CEO_OFFICE.maxX - t, "ceo glass (right of door)"),
    glass(CEO_OFFICE.maxX + t, meetL, "meeting glass (left of door)"),
    glass(meetR, MEETING_ROOM.maxX - t, "meeting glass (right of door)"),
    glass(MEETING_ROOM.maxX + t, pantryL, "pantry glass (left of door)"),
    glass(pantryR, PANTRY.maxX, "pantry glass (right of door)"),
    wall(CEO_OFFICE.maxX, "wall ceo | meeting"),
    wall(MEETING_ROOM.maxX, "wall meeting | pantry"),
  ];
}

/** A glass wall's stretches either side of its door (the whole wall when it has none). */
export function glassSpans(wall: GlassWall): [number, number][] {
  if (!wall.door) return [[wall.from, wall.to]];
  return [
    [wall.from, wall.door.at - wall.door.width / 2],
    [wall.door.at + wall.door.width / 2, wall.to],
  ];
}

/** The glass walls of the work row as footprints (D-132), doors left open. */
export function glassWallRects(): Rect[] {
  const t = WALL_HALF;
  return GLASS_WALLS.flatMap((wall) =>
    glassSpans(wall).map(([from, to], i): Rect => {
      const name = `${wall.name}${wall.door ? (i ? " (after door)" : " (before door)") : ""}`;
      // the ends stop short of a crossing wall's footprint, so two walls meet without overlapping
      const [a, b] = [from + t + 0.001, to - t - 0.001];
      return wall.axis === "x"
        ? { name, minX: a, maxX: b, minZ: wall.at - t, maxZ: wall.at + t }
        : { name, minX: wall.at - t, maxX: wall.at + t, minZ: a, maxZ: b };
    }),
  );
}

/** Open door leaves: inside the room, along the hinge side of the opening. */
export function doorLeaves(): Rect[] {
  return DOORS.map((door) => {
    const hinge = door.x - door.width / 2 - 0.05;
    return {
      name: `${door.name} leaf`,
      minX: hinge - 0.03,
      maxX: hinge + 0.03,
      minZ: BACK_ROOMS_Z - WALL_HALF - door.width,
      maxZ: BACK_ROOMS_Z - WALL_HALF - 0.01,
    };
  });
}

export function obstacles(): Rect[] {
  const furniture = allSeats().flatMap((seat) => [
    ...(seat.bench ? [] : [rectAround(seat.desk, DESK.width, DESK.depth, `desk ${seat.key}`)]),
    rectAround(seat.chair, CHAIR.size, CHAIR.size, `chair ${seat.key}`),
  ]);
  const benches = BENCHES.map((b) => ({ name: b.name, minX: b.minX, maxX: b.maxX, minZ: b.z - DESK.depth / 2, maxZ: b.z + DESK.depth / 2 }));
  const decor = DECOR.map((item, i) => rectAround(item.at, item.size[0], item.size[1], `${item.kind} #${i}`));
  return [
    ...furniture,
    ...benches,
    ...decor,
    rectAround(APPROVAL_DESK.center, APPROVAL_FOOTPRINT[0], APPROVAL_FOOTPRINT[1], "approval desk"),
    ...partitions(),
    ...glassWallRects(),
    ...doorLeaves(),
  ];
}
