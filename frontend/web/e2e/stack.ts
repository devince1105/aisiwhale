// The stack the browser tests run against (T-315): its own database (<dev db>_e2e, reset and
// seeded by backend/scripts/e2e_prepare.py), its own API on :8100 and worker, simulated model.
// The developer's .env is not read (AUTORA_ENV_FILE=/dev/null), so no real key is ever used and
// the dev database is never touched. The web app (:3100) is started by playwright.config.ts.
import { execFileSync, spawn, type ChildProcess } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

export const REPO = resolve(__dirname, "../../..");
const PYTHON = join(REPO, ".venv/bin/python");
export const API_PORT = 8100;
export const WEB_PORT = 3100;
export const API_URL = `http://localhost:${API_PORT}`;
/** The e2e API's own operator token (not the dev one): for the tests' own API calls, never put in
 * a browser (D-230). */
export const TOKEN = "e2e-operator-token";
/** The e2e database's back-office admin (made by e2e_prepare.py): the browser signs in as them
 * and keeps the API's cookie, as a real admin does (D-230). Only ever in the throwaway e2e DB. */
export const ADMIN_EMAIL = "admin@e2e.test";
const ADMIN_PASSWORD = "e2e admin password";

interface Seeded {
  database_url: string;
  company_id: string;
  project_id: string;
  /** The demo newsroom (T-520): its fixture feeds read and clustered into stories. */
  newsroom_company_id: string;
  newsroom_project_id: string;
}

/** A backend process whose output is kept, so tests can wait for log lines. */
export class Proc {
  private child: ChildProcess | null = null;
  output = "";

  constructor(
    readonly name: string,
    private readonly args: string[],
    private readonly env: NodeJS.ProcessEnv,
  ) {}

  start(): void {
    const child = spawn(PYTHON, this.args, { cwd: REPO, env: this.env, stdio: ["ignore", "pipe", "pipe"] });
    const keep = (chunk: Buffer) => {
      this.output += chunk.toString();
    };
    child.stdout!.on("data", keep);
    child.stderr!.on("data", keep);
    this.child = child;
  }

  async stop(signal: NodeJS.Signals = "SIGTERM"): Promise<void> {
    const child = this.child;
    if (!child || child.exitCode !== null || child.signalCode !== null) return;
    const exited = new Promise((done) => child.once("exit", done));
    child.kill(signal);
    await exited;
  }

  count(pattern: RegExp): number {
    return this.output.match(new RegExp(pattern.source, "g"))?.length ?? 0;
  }

  async waitFor(check: () => boolean, what: string, timeoutMs: number): Promise<void> {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      if (check()) return;
      await new Promise((done) => setTimeout(done, 100));
    }
    throw new Error(`${this.name}: timed out waiting for ${what}\n${this.output.slice(-4000)}`);
  }
}

async function reachable(url: string): Promise<boolean> {
  try {
    return (await fetch(url)).ok;
  } catch {
    return false;
  }
}

/** A cookie as Playwright's `addCookies` takes it. */
interface AdminCookie {
  name: string;
  value: string;
  url: string;
  httpOnly: boolean;
  sameSite: "Lax";
}

export class Stack {
  readonly api: Proc;
  readonly worker: Proc;

  private constructor(readonly seeded: Seeded) {
    const env: NodeJS.ProcessEnv = {
      ...process.env,
      AUTORA_ENV_FILE: "/dev/null",
      DATABASE_URL: seeded.database_url,
      MODEL_PROVIDER: "fake",
      TOOLS_PROFILE: "fixture",
      EMBED_PROVIDER: "fake",
      API_BEARER_TOKEN: TOKEN,
      ADMIN_EMAILS: JSON.stringify([ADMIN_EMAIL]),
      CORS_ORIGINS: JSON.stringify([`http://localhost:${WEB_PORT}`]),
      BLOB_STORE_DIR: mkdtempSync(join(tmpdir(), "autora-e2e-blobs-")),
      WORKER_ID: "e2e-worker",
      WORKER_COMPANY_IDS: JSON.stringify([seeded.company_id, seeded.newsroom_company_id]),
      WORKER_POLL_SECONDS: "0.2",
      WORKER_IDLE_POLL_SECONDS: "0.2", // the tests wait on no idle worker (D-192)
      PYTHONUNBUFFERED: "1",
    };
    this.api = new Proc("api", ["-m", "uvicorn", "--app-dir", "backend/api", "main:app", "--port", String(API_PORT)], env);
    this.worker = new Proc("worker", ["backend/worker/main.py"], env);
  }

  get companyId(): string {
    return this.seeded.company_id;
  }

  get projectId(): string {
    return this.seeded.project_id;
  }

  get newsroomCompanyId(): string {
    return this.seeded.newsroom_company_id;
  }

  get newsroomProjectId(): string {
    return this.seeded.newsroom_project_id;
  }

  static async start(): Promise<Stack> {
    if (await reachable(`${API_URL}/health`)) throw new Error(`port ${API_PORT} is already in use`);
    const out = execFileSync(PYTHON, [join(REPO, "backend/scripts/e2e_prepare.py")], {
      encoding: "utf8",
      env: { ...process.env, E2E_ADMIN_EMAIL: ADMIN_EMAIL, E2E_ADMIN_PASSWORD: ADMIN_PASSWORD },
    });
    const stack = new Stack(JSON.parse(out.trim().split("\n").at(-1)!) as Seeded);
    await stack.startApi();
    stack.worker.start();
    await stack.worker.waitFor(() => stack.worker.output.includes("started (concurrency="), "worker start", 30_000);
    return stack;
  }

  async startApi(): Promise<void> {
    this.api.start();
    const deadline = Date.now() + 30_000;
    while (!(await reachable(`${API_URL}/health`))) {
      if (Date.now() > deadline) throw new Error(`api did not start\n${this.api.output.slice(-4000)}`);
      await new Promise((done) => setTimeout(done, 200));
    }
  }

  private adminCookie: Promise<AdminCookie[]> | null = null;

  /** The back office's cookie for the e2e admin, to add to a browser context (D-230). Signed in
   * once per stack and the cookie reused, as a real admin's browser does: signing in before every
   * test would run into the API's own limit on sign-ins per address (10 in 15 minutes). The
   * session lives in the database, so it outlasts the API restarts some tests make. */
  adminCookies(): Promise<AdminCookie[]> {
    this.adminCookie ??= this.signInAdmin().catch((error: unknown) => {
      this.adminCookie = null; // a failed sign-in is not kept: the next test asks again
      throw error;
    });
    return this.adminCookie;
  }

  private async signInAdmin(): Promise<AdminCookie[]> {
    const response = await fetch(`${API_URL}/api/admin/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: ADMIN_EMAIL, password: ADMIN_PASSWORD }),
    });
    if (!response.ok) throw new Error(`admin sign-in failed: ${response.status} ${await response.text()}`);
    const value = /autora_admin=([^;]+)/.exec(response.headers.get("set-cookie") ?? "")?.[1];
    if (!value) throw new Error("admin sign-in set no cookie");
    // localhost: the cookie counts for the web app (:3100) and the API (:8100) alike
    return [{ name: "autora_admin", value, url: API_URL, httpOnly: true, sameSite: "Lax" }];
  }

  async stop(): Promise<void> {
    await Promise.all([this.worker.stop(), this.api.stop()]);
  }
}
