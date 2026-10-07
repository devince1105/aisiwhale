// AD-14: what a new back-office page must do, checked rather than remembered. The API says which
// key each route needs (``x-permission`` in openapi.json, from autora_api/permissions.py); from
// it and the source:
// - every write a role needs a key for has a name in the audit trail (audit/labels.ts);
// - every key the pages ask for (useCan, nav ``need``, the board's moves) is one a route has;
// - every page under /admin belongs to the navigation map, so it has breadcrumbs, a place in the
//   sidebar, the ⌘K palette and the shell's width.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";

import { describe, expect, it } from "vitest";

import openapi from "@/api/openapi.json";
import { ACTION_LABEL } from "@/features/audit/labels";

import { activeNav } from "./nav";

const SRC = join(__dirname, "..", "..");
const WRITES = new Set(["post", "put", "patch", "delete"]);

type Operation = { "x-permission"?: string };
const operations = Object.entries(openapi.paths as Record<string, Record<string, Operation>>).flatMap(([path, methods]) =>
  Object.entries(methods).map(([method, operation]) => ({ path, method, key: operation["x-permission"] })),
);
const KEYS = new Set(operations.flatMap((o) => (o.key ? [o.key] : [])));

function files(dir: string, keep: (name: string) => boolean): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) return files(full, keep);
    return keep(name) ? [full] : [];
  });
}

describe("conventions every back-office page keeps (AD-14)", () => {
  it("names every keyed write in the audit trail", () => {
    const unnamed = operations.filter((o) => o.key && WRITES.has(o.method) && !ACTION_LABEL[o.path]);
    expect(unnamed.map((o) => `${o.method.toUpperCase()} ${o.path}`)).toEqual([]);
  });

  it("asks only for keys a route has", () => {
    expect(KEYS.size).toBeGreaterThan(10);
    const source = files(SRC, (n) => /\.tsx?$/.test(n) && !/\.test\.tsx?$/.test(n) && !n.endsWith(".gen.ts"));
    const asked = new Set<string>();
    for (const file of source) {
      const text = readFileSync(file, "utf8");
      for (const m of text.matchAll(/(?:can\(|need:\s*|needs?:\s*)"([a-z]+:[a-z]+)"/g)) asked.add(m[1]);
    }
    for (const m of readFileSync(join(SRC, "features", "board", "moves.ts"), "utf8").matchAll(/"([a-z]+:[a-z]+)"/g)) asked.add(m[1]);
    expect(asked.size).toBeGreaterThan(3);
    expect([...asked].filter((key) => !KEYS.has(key))).toEqual([]);
  });

  it("puts every /admin page on the navigation map", () => {
    const admin = join(SRC, "app", "admin");
    // the sign-in page stands outside the shell; /admin/newsroom only redirects to its articles
    const outside = new Set(["/admin/login", "/admin/newsroom"]);
    const pages = files(admin, (n) => n === "page.tsx").map((file) => {
      const dir = relative(admin, join(file, "..")).split(sep).filter(Boolean);
      return ["/admin", ...dir.map((part) => part.replace(/^\[.+\]$/, "x"))].join("/");
    });
    expect(pages.length).toBeGreaterThan(15);
    expect(pages.filter((path) => !outside.has(path) && !activeNav(path))).toEqual([]);
  });
});
