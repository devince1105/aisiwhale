// How big a figure is and where it sits (T-405). Kept apart from ``AgentAvatar`` so that what
// draws a figure without React — the 2D bake (D-027) — reads the same numbers as the 3D office.

/** Kenney's characters are 0.67 units tall; 2 makes a 1.35 m chibi whose head clears the chair back. */
export const AVATAR_SCALE = 2;

/** Seated, the body is lifted so the hips rest on the chair (seat top 0.46 m). */
export const SEAT_LIFT = 0.41;

/** Standing up (done), the avatar steps behind its chair. */
export const STAND_BACK = 0.6;

/** An own figure (D-201) sits this much nearer its desk (m): her bending arms reach the keyboard from
 * there; the chair is where it was. */
export const SEAT_FORWARD = 0.22;

/** Where the pack's sit clip puts the hips, above a figure's origin (model units): a figure drawn
 * larger is lowered by its extra share of this when seated, so it still sits on the seat. */
export const SIT_HIP = 0.026;
