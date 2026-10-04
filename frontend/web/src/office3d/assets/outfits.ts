// Each photographed member of the office dressed as herself (D-115): the chibi figure closest to
// her look, and the colours of her hair, clothes and skin.
//
// The figures (Kenney "Mini Characters", CC0) take every colour from one palette texture: a
// surface's UVs point into a 32 × 128 px cell of it, a vertical gradient. Dressing a figure never
// edits a shared cell (the same cell is the hair on one part and the shoes on another): the
// vertices a rule picks are pointed at a spare, unused cell of the figure's own copy of the
// palette, painted the rule's colour with the original cell's shading (``dress.ts``).
import type { Character } from "./characters";

export type Part = "head" | "body";

export interface Paint {
  /** Palette cells as "row:col" (4 rows of 16 columns, row 0 at the top). */
  cells: string[];
  color: string;
  /** Only these meshes (the figure's head-mesh or body-mesh); both when omitted. */
  parts?: Part[];
  /** Only vertices these bones move most (torso, arm-left, arm-right, leg-left, leg-right). */
  bones?: string[];
  /** Leave the face's features (eyes, mouth) as they are: on some figures they share the hair's
   * cell. They are the flat plane at the front of the head, below the fringe. */
  notFace?: boolean;
}

export interface Outfit {
  model: Character;
  paints: Paint[];
}

const SKIN = "#f2c9a8";
const BLACK = "#1b1b20";

/** By avatar_key (the same key as the head photo, ``people.avatarPhoto``). */
export const OUTFITS: Record<string, Outfit> = {
  // Tifa: long dark hair, black top, brown suspenders, black skirt
  tifa: {
    model: "character-female-f",
    paints: [
      { cells: ["3:13", "3:11"], parts: ["head"], color: BLACK },
      { cells: ["2:5"], color: "#6a4527" },
      { cells: ["2:11"], parts: ["body"], color: "#222228" },
      { cells: ["2:15"], parts: ["body"], color: "#4a3222" },
    ],
  },
  // Chun-Li: dark brown hair in two buns, white ribbons, a blue qipao and blue trousers
  chunli: {
    model: "character-female-b",
    paints: [
      { cells: ["3:11"], parts: ["head"], color: "#3b2519" },
      { cells: ["2:5"], parts: ["head"], color: "#f4f1ea" },
      { cells: ["2:5"], parts: ["body"], color: "#1f4fb8" },
      { cells: ["2:15"], parts: ["body"], color: "#16377f" },
    ],
  },
  // Ada: short black hair, a red top, dark trousers
  ada: {
    model: "character-female-d",
    paints: [
      { cells: ["3:11"], parts: ["head"], color: "#141418" },
      { cells: ["3:3"], parts: ["body"], color: "#b1202b" },
      { cells: ["3:1"], parts: ["body"], color: "#15151a" },
    ],
  },
  // Sayla: long blonde hair, a pink jacket, light trousers
  sayla: {
    model: "character-female-d",
    paints: [
      { cells: ["3:11"], parts: ["head"], color: "#e9c66d" },
      { cells: ["3:3"], parts: ["body"], color: "#e48aa2" },
      { cells: ["3:1"], parts: ["body"], color: "#e9e6ee" },
    ],
  },
  // Rei: light blue hair, a white plugsuit with dark blue, red eyes aside
  rei: {
    model: "character-female-e",
    paints: [
      { cells: ["3:1"], parts: ["head"], notFace: true, color: "#a9cdee" },
      { cells: ["3:7"], parts: ["body"], color: "#1d2c52" },
      { cells: ["3:1"], parts: ["body"], color: "#f0f0f4" },
    ],
  },
  // Mari: reddish-brown twin tails, a red plugsuit
  mari: {
    model: "character-female-f",
    paints: [
      { cells: ["3:13", "3:11"], parts: ["head"], color: "#8a3d22" },
      { cells: ["3:3", "3:1"], parts: ["body"], color: "#b3182c" },
      { cells: ["2:5"], color: "#1e1e24" },
      { cells: ["2:11"], parts: ["body"], color: "#b3182c" },
      { cells: ["2:15"], parts: ["body"], color: "#26262c" },
    ],
  },
  // Ami: short blue hair, a white sailor top with a blue collar and a blue skirt
  ami: {
    model: "character-female-c",
    paints: [
      { cells: ["3:3"], parts: ["head"], color: "#2446b0" },
      { cells: ["3:11"], color: SKIN },
      { cells: ["2:11"], parts: ["body"], color: "#f4f4f7" },
      { cells: ["3:9"], parts: ["body"], color: "#2a4fc4" },
      { cells: ["2:9"], parts: ["body"], color: "#2a4fc4" },
      { cells: ["3:3"], parts: ["body"], color: "#f4f4f7" },
      { cells: ["3:15"], parts: ["body"], color: "#2a4fc4" },
    ],
  },
  // Shinobu: black hair, a black uniform, lavender for the butterfly, fair skin
  shinobu: {
    model: "character-female-a",
    paints: [
      { cells: ["3:13"], color: SKIN },
      { cells: ["2:15"], parts: ["body"], color: "#1c1c26" },
      { cells: ["3:11"], parts: ["body"], color: "#1c1c26" },
      { cells: ["2:11"], parts: ["body"], bones: ["arm-left", "arm-right"], color: "#cbb6ee" },
      { cells: ["2:11"], parts: ["body"], color: "#2a2a34" },
    ],
  },

  // The public site's demo office (D-155): made-up people, each on the cell layout of a figure
  // above, in colours of her own.
  // Rinka: silver hair, a charcoal suit, gold
  demo_rinka: {
    model: "character-female-f",
    paints: [
      { cells: ["3:13", "3:11"], parts: ["head"], color: "#c9ccd6" },
      { cells: ["2:5"], color: "#b8913a" },
      { cells: ["2:11"], parts: ["body"], color: "#2b2f3a" },
      { cells: ["2:15"], parts: ["body"], color: "#2b2f3a" },
    ],
  },
  // Kaede: auburn hair, a green jacket, cream trousers
  demo_kaede: {
    model: "character-female-d",
    paints: [
      { cells: ["3:11"], parts: ["head"], color: "#7a3a1e" },
      { cells: ["3:3"], parts: ["body"], color: "#2f5d46" },
      { cells: ["3:1"], parts: ["body"], color: "#e8e1cf" },
    ],
  },
  // Nanami: teal hair, navy and white
  demo_nanami: {
    model: "character-female-e",
    paints: [
      { cells: ["3:1"], parts: ["head"], notFace: true, color: "#3fa7a0" },
      { cells: ["3:7"], parts: ["body"], color: "#22304f" },
      { cells: ["3:1"], parts: ["body"], color: "#f2f2f5" },
    ],
  },
  // Shiori: chestnut hair, a beige cardigan, a brown skirt
  demo_shiori: {
    model: "character-female-c",
    paints: [
      { cells: ["3:3"], parts: ["head"], color: "#5a3a28" },
      { cells: ["3:11"], color: SKIN },
      { cells: ["2:11"], parts: ["body"], color: "#d9c7a3" },
      { cells: ["3:9"], parts: ["body"], color: "#6b4a33" },
      { cells: ["2:9"], parts: ["body"], color: "#6b4a33" },
      { cells: ["3:3"], parts: ["body"], color: "#d9c7a3" },
      { cells: ["3:15"], parts: ["body"], color: "#6b4a33" },
    ],
  },
  // Yuzuha: mint hair, a grey jacket, charcoal trousers — on Kaede's figure (D-182): Shinobu's
  // (female-a) has wide sleeves that, coloured, read as blades in her hands, and an analyst
  // carries nothing of the kind into the office
  demo_yuzuha: {
    model: "character-female-d",
    paints: [
      { cells: ["3:11"], parts: ["head"], color: "#9fd8c4" },
      { cells: ["3:3"], parts: ["body"], color: "#4a4f58" },
      { cells: ["3:1"], parts: ["body"], color: "#2a2d33" },
    ],
  },
  // Kotone: plum hair, a lilac top, dark trousers
  demo_kotone: {
    model: "character-female-b",
    paints: [
      { cells: ["3:11"], parts: ["head"], color: "#5b2a4a" },
      { cells: ["2:5"], parts: ["head"], color: "#b9a3d9" },
      { cells: ["2:5"], parts: ["body"], color: "#b9a3d9" },
      { cells: ["2:15"], parts: ["body"], color: "#2b2633" },
    ],
  },
  // Mio: wine-red hair, a white shirt, grey trousers
  demo_mio: {
    model: "character-female-d",
    paints: [
      { cells: ["3:11"], parts: ["head"], color: "#6e1f2a" },
      { cells: ["3:3"], parts: ["body"], color: "#f2f2f4" },
      { cells: ["3:1"], parts: ["body"], color: "#5a5d66" },
    ],
  },
  // Ririka: coral hair, an orange top, denim
  demo_ririka: {
    model: "character-female-f",
    paints: [
      { cells: ["3:13", "3:11"], parts: ["head"], color: "#f08a7a" },
      { cells: ["2:5"], color: "#3a5a8c" },
      { cells: ["2:11"], parts: ["body"], color: "#f2a33a" },
      { cells: ["2:15"], parts: ["body"], color: "#3a5a8c" },
    ],
  },
};

export function outfitFor(avatarKey: string | null | undefined): Outfit | null {
  return (avatarKey && OUTFITS[avatarKey]) || null;
}
