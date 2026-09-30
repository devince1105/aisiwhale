// The office log (D-136): what people in the office did, one line each, newest first — the work
// (a run started or finished, work carried to a colleague or to the approval desk) and the idle
// moments (a coffee, a chat). The work is the company's record told short; the idle moments are
// the page's own decoration, and the panel shows them faintly so the two are never confused.
// Kept in this browser tab only, the last few dozen lines.
import { useStore } from "zustand";
import { createStore } from "zustand/vanilla";

export interface LogLine {
  id: number;
  /** Epoch ms. */
  at: number;
  agentId: string;
  text: string;
  kind: "work" | "life";
}

export const LOG_LIMIT = 40;

let next = 1;

export const officeLog = createStore<{ lines: LogLine[]; add(line: Omit<LogLine, "id">): void; clear(): void }>()((set) => ({
  lines: [],
  add: (line) => set((s) => ({ lines: [{ ...line, id: next++ }, ...s.lines].slice(0, LOG_LIMIT) })),
  clear: () => set({ lines: [] }),
}));

export function useOfficeLog(): LogLine[] {
  return useStore(officeLog, (s) => s.lines);
}
