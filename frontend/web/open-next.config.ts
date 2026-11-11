// How the site runs on Cloudflare Workers (D-266), through OpenNext: the output of the real
// `next build`, so the ISR, rewrites and Data Cache of D-265 behave as they do on `next start`.
//
// - Kept pages and the Data Cache live in R2, with each Cloudflare location keeping its own copy
//   in the Cache API in front (regional cache): a page asked for again in the same place is not
//   read from R2 again.
// - A kept page past its time is rebuilt once, in the background, by a Durable Object queue, not
//   by every request that finds it stale.
// - Cache interception: a kept page is answered before the Next.js server is even loaded, which
//   is what keeps CPU time per request small. (No PPR here, which it does not support.)
// - No tag cache: nothing calls revalidateTag yet; pages and reads expire by time only.
import { defineCloudflareConfig } from "@opennextjs/cloudflare";
import r2IncrementalCache from "@opennextjs/cloudflare/overrides/incremental-cache/r2-incremental-cache";
import { withRegionalCache } from "@opennextjs/cloudflare/overrides/incremental-cache/regional-cache";
import doQueue from "@opennextjs/cloudflare/overrides/queue/do-queue";

export default defineCloudflareConfig({
  incrementalCache: withRegionalCache(r2IncrementalCache, { mode: "long-lived" }),
  queue: doQueue,
  enableCacheInterception: true,
});
