import type { NextConfig } from "next";

import { queryRewrites } from "./src/features/site/queryRoutes";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // The browser tests (e2e/) build their own copy against their own API, next to the dev build.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  // That build skips type checking: `pnpm typecheck` owns it, and the shared tsconfig also
  // includes the dev server's generated types, which the e2e build must not depend on.
  typescript: { ignoreBuildErrors: Boolean(process.env.NEXT_DIST_DIR) },
  // The back office moved under /admin (D-054); old bookmarks and the activity links already
  // stored in the database still say /dashboard, /newsroom/..., so they are sent on.
  // /admin itself has no page: it opens the dashboard, which sends a signed-out visitor to login.
  // The public lists' query strings (?page=, ?section=, ?sort=…) to cached pages, in the router,
  // before any function runs (queryRoutes.ts): the address keeps its query, the page is ISR.
  async rewrites() {
    return { beforeFiles: queryRewrites(), afterFiles: [], fallback: [] };
  },
  // The back office is nobody's to find through a search engine; robots.txt asks the same.
  async headers() {
    return [{ source: "/admin/:path*", headers: [{ key: "X-Robots-Tag", value: "noindex, nofollow" }] }];
  },
  async redirects() {
    return [
      { source: "/admin", destination: "/admin/dashboard", permanent: false },
      ...ADMIN_PAGES.map((page) => ({
        source: `/${page}/:rest*`,
        destination: `/admin/${page}/:rest*`,
        permanent: false,
      })),
    ];
  },
};

const ADMIN_PAGES = ["dashboard", "agents", "approvals", "cycles", "newsroom", "office", "timeline", "tasks", "trace"];

export default nextConfig;
