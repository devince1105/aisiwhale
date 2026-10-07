// What a person may move on the production board (AD-08), and what each move does. One table,
// moves.json, read here and by the backend's test_board_moves.py, which checks every move is one
// the state machine allows (ARTICLE_FSM, STORY_FSM) — a card is never let go where the API would
// refuse it. Everything else on the board is the workflow's to move, not a person's.
import table from "./moves.json";

export type Entity = keyof typeof table;
export type MoveAction = "approve" | "send_back" | "reject" | "unpublish" | "republish" | "revise" | "start";

export interface Move {
  from: string;
  to: string;
  action: MoveAction;
}

export const MOVES: Record<Entity, readonly Move[]> = {
  article: table.article.map(([from, to, action]) => ({ from, to, action: action as MoveAction })),
  story: table.story.map(([from, to, action]) => ({ from, to, action: action as MoveAction })),
};

/** The move from ``from`` to ``to``, or null: not a person's to make. */
export function moveFor(entity: Entity, from: string, to: string): Move | null {
  return MOVES[entity].find((m) => m.from === from && m.to === to) ?? null;
}

export function targetsFrom(entity: Entity, from: string): string[] {
  return MOVES[entity].filter((m) => m.from === from).map((m) => m.to);
}

/** The permission each move needs (AD-09): deciding an approval, or changing the newsroom. */
export const MOVE_NEEDS: Record<MoveAction, string> = {
  approve: "approvals:decide",
  send_back: "approvals:decide",
  reject: "approvals:decide",
  unpublish: "newsroom:edit",
  republish: "newsroom:edit",
  revise: "newsroom:edit",
  start: "newsroom:edit",
};

/** How each move asks before it is made. ``reason``: required (the writer works from it, or the
 * record keeps why), or none. */
export const MOVE_INFO: Record<MoveAction, { verb: string; reason: "required" | "none"; tone: "danger" | "primary" }> = {
  approve: { verb: "核准", reason: "none", tone: "primary" },
  send_back: { verb: "退回修改", reason: "required", tone: "primary" },
  reject: { verb: "駁回", reason: "required", tone: "danger" },
  unpublish: { verb: "下架", reason: "required", tone: "danger" },
  republish: { verb: "重新上架", reason: "none", tone: "primary" },
  revise: { verb: "修改文章", reason: "required", tone: "primary" },
  start: { verb: "開始製作", reason: "none", tone: "primary" },
};
