// The public site's demo office (D-155): the 3D office driven by a script instead of the stream.
//
// The script (script.json, written by backend/scripts/demo_office_script.py) is one real daily
// cycle with made-up people, fresh ids and no real content. The player feeds it to the same store
// the back office's socket feeds — a snapshot first, then the events at their times, each stamped
// as happening now — and starts over when it runs out. It is the one place in features/ where a
// timer moves the store, and it is named in no-fake-data.test.ts as that exception: everything it
// plays is labelled a demo on the page.

export interface ScriptAgent {
  id: string;
  role: string;
  display_name: string;
  avatar_key: string;
  department_id: string;
  department_key: string;
  office_zone_key: string;
  business_unit_key: string | null;
}

export interface ScriptEvent {
  /** When, in ms from the loop's start. */
  t: number;
  /** For AGENT_RUN_COMPLETED: how long the finished state shows (ms), as display_until. */
  du?: number;
  event_id: string;
  event_type: string;
  aggregate_type: string;
  aggregate_id: string | null;
  agent_id: string | null;
  task_id: string | null;
  run_id: string | null;
  workflow_run_id: string | null;
  cycle_id: string | null;
  actor: { kind: string; id: string };
  payload: Record<string, unknown>;
}

export interface Script {
  loop_ms: number;
  company_id: string;
  department_names: Record<string, Record<string, string>>;
  agents: ScriptAgent[];
  events: ScriptEvent[];
}

/** The parts of the realtime store the player uses. */
export interface PlayerStore {
  hydrate(snapshot: unknown): void;
  applyEvents(raws: readonly unknown[]): number;
  setConnection(patch: { status: "live" }): void;
  reset(): void;
}

export interface PlayerOptions {
  store: PlayerStore;
  script: Script;
  now?: () => number;
  setTimer?: (run: () => void, ms: number) => unknown;
  clearTimer?: (timer: unknown) => void;
}

export interface Player {
  start(): void;
  pause(): void;
  resume(): void;
  stop(): void;
}

/** The office before anything has happened: everybody at their desk, idle. */
export function demoSnapshot(script: Script, at: Date): unknown {
  const since = at.toISOString();
  return {
    company_id: script.company_id,
    last_seq: 0,
    server_time: since,
    agents: script.agents.map((agent) => ({
      ...agent,
      activity: { state: "IDLE", stored_state: "IDLE", detail: {}, since, run_id: null, task_id: null, last_event_seq: 0 },
    })),
    tasks: [],
    recent_events: [],
    kpis: null,
    cycle: null,
  };
}

/** A script event as the stream would deliver it, happening at `at`. */
export function stamp(event: ScriptEvent, script: Script, seq: number, at: Date): unknown {
  const { t: _t, du, ...rest } = event;
  const payload = du === undefined ? rest.payload : { ...rest.payload, display_until: new Date(at.getTime() + du).toISOString() };
  return {
    ...rest,
    seq,
    schema_version: 1,
    company_id: script.company_id,
    occurred_at: at.toISOString(),
    correlation_id: null,
    causation_id: null,
    payload,
  };
}

export function createDemoPlayer({
  store,
  script,
  now = () => Date.now(),
  setTimer = (run, ms) => setTimeout(run, ms),
  clearTimer = (timer) => clearTimeout(timer as ReturnType<typeof setTimeout>),
}: PlayerOptions): Player {
  let timer: unknown = null;
  let next = 0; // index of the next event
  let seq = 0;
  let elapsed = 0; // ms into the loop when the clock last started
  let startedAt = 0; // now() when it did
  let running = false;

  const position = () => elapsed + (now() - startedAt);

  const begin = () => {
    store.reset();
    store.hydrate(demoSnapshot(script, new Date(now())));
    store.setConnection({ status: "live" });
    next = 0;
    seq = 0;
    elapsed = 0;
    startedAt = now();
  };

  const tick = () => {
    timer = null;
    if (!running) return;
    const at = position();
    const due: unknown[] = [];
    while (next < script.events.length && script.events[next].t <= at) {
      seq += 1;
      due.push(stamp(script.events[next], script, seq, new Date(now())));
      next += 1;
    }
    if (due.length) store.applyEvents(due);
    if (next >= script.events.length && at >= script.loop_ms) begin();
    const upcoming = next < script.events.length ? script.events[next].t : script.loop_ms;
    timer = setTimer(tick, Math.max(0, upcoming - position()));
  };

  const halt = () => {
    if (timer !== null) clearTimer(timer);
    timer = null;
  };

  return {
    start() {
      halt();
      running = true;
      begin();
      tick();
    },
    pause() {
      if (!running) return;
      elapsed = position();
      running = false;
      halt();
    },
    resume() {
      if (running) return;
      running = true;
      startedAt = now();
      tick();
    },
    stop() {
      running = false;
      halt();
      store.reset();
    },
  };
}
