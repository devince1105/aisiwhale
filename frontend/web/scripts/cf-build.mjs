// Builds the site for Cloudflare Workers (D-266) with the same variables the Worker is given
// (wrangler.jsonc's "vars"), so what `next build` bakes in and what the Worker reads agree.
// Usage: pnpm cf:build
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";

const text = readFileSync(new URL("../wrangler.jsonc", import.meta.url), "utf8");
// JSONC: drop whole-line comments (no value in the file has "//" at the start of a line)
const config = JSON.parse(text.replace(/^\s*\/\/.*$/gm, ""));
execFileSync("pnpm", ["exec", "opennextjs-cloudflare", "build"], {
  stdio: "inherit",
  env: { ...process.env, ...config.vars },
});
