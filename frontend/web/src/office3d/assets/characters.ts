// The avatar assets (T-404, D-008): Kenney "Mini Characters" 1.0, CC0 (see LICENSES.md). Twelve
// chibi low-poly characters, each a GLB with the same skeleton and 32 animations, sharing one
// texture. Which character an agent wears, and which clip plays for each pose, is decided here.
import { avatarPhoto } from "@/people";

import { outfitFor } from "./outfits";

import type { Pose } from "../visual/mapping";

export const CHARACTER_DIR = "/models/characters";

export const CHARACTERS = [
  "character-male-a",
  "character-female-a",
  "character-male-b",
  "character-female-b",
  "character-male-c",
  "character-female-c",
  "character-male-d",
  "character-female-d",
  "character-male-e",
  "character-female-e",
  "character-male-f",
  "character-female-f",
] as const;
export type Character = (typeof CHARACTERS)[number];

export const characterUrl = (character: Character) => `${CHARACTER_DIR}/${character}.glb`;

/**
 * Members with a figure of their own (D-196), by avatar_key: made in Blender on the pack's
 * skeleton, with the pack's clips (``figures-source/blender``). She is drawn as it — not as a
 * standee, and not as a dressed pack figure.
 */
export const OWN_FIGURES = ["tifa", "ada", "rei", "sayla", "mari", "shinobu", "ami"] as const;
export type OwnFigure = (typeof OWN_FIGURES)[number];

export function ownFigure(avatarKey: string | null | undefined): OwnFigure | null {
  return avatarKey && (OWN_FIGURES as readonly string[]).includes(avatarKey) ? (avatarKey as OwnFigure) : null;
}

export const ownFigureUrl = (figure: OwnFigure) => `${CHARACTER_DIR}/${figure}.glb`;

/** How tall an own figure stands, in model units: all of them are built to Tifa's proportions
 * (D-199), smaller than the standees they replace; the office draws them at the standees' height
 * (D-201). */
export const OWN_FIGURE_HEIGHT = 0.618;

/**
 * Clips per pose (02 §7 poses). The pack has one sitting clip; thinking, typing and reading are
 * the same seat with a different upper-body accent that T-405 layers on. `once` plays one time
 * and settles back into `base`.
 */
export const POSE_CLIP: Record<Pose, { base: string; once?: string }> = {
  sit_idle: { base: "sit" },
  sit_think: { base: "sit" },
  sit_type: { base: "sit", once: "interact-right" },
  sit_read: { base: "sit" },
  stand: { base: "idle", once: "emote-yes" },
  walk: { base: "walk" },
  slump: { base: "sit", once: "emote-no" },
};

/** The courier carrying a result (T-408). */
export const CARRY_CLIP = "pick-up";

export const REQUIRED_CLIPS = [...new Set([...Object.values(POSE_CLIP).flatMap((c) => [c.base, c.once ?? c.base]), CARRY_CLIP])].sort();

/** A character per agent: `avatar_key` if it names one, else a stable pick from the agent id. */
export function characterFor(agentId: string, avatarKey?: string | null): Character {
  if (avatarKey && (CHARACTERS as readonly string[]).includes(avatarKey)) return avatarKey as Character;
  // dressed as herself (D-115): the figure her outfit is made on
  const outfit = outfitFor(avatarKey);
  if (outfit) return outfit.model;
  let hash = 0;
  for (const ch of agentId) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  // someone with a head photo (D-113) is one of the office's women: a woman's figure for her
  if (avatarPhoto(avatarKey)) {
    const women = CHARACTERS.filter((c) => c.includes("female"));
    return women[hash % women.length];
  }
  return CHARACTERS[hash % CHARACTERS.length];
}
