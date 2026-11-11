# 2026-11-11 aisiwhale 前端遷移至 Cloudflare Workers（D-266）

測試網址：**https://cf.aisiwhale.com**（Worker `aisiwhale-web`，custom domain）。`aisiwhale.com`、`www.aisiwhale.com` 的 DNS 與正式站**沒有動**；沒有任何真實金流交易、沒有扣 COIN。

## 1. 相容性檢查

| 項目 | 現況 | 在 Workers 上 |
|---|---|---|
| Next.js | 16.3.5 → **16.4.6**（`@opennextjs/cloudflare` 1.20.16 要求 ≥16.4.5） | OK |
| SSR／ISR | D-265 後公開頁全是 ISR；搜尋、PAYUNi 回傳每次渲染 | OK：ISR 存在 R2，重算經 Durable Object 佇列 |
| API Routes | 前端沒有 `app/api`；資料全來自 FastAPI（`api.aisiwhale.com`，Render） | 不需處理 |
| Middleware／proxy | 沒有 | 不需處理 |
| 會員 cookie | `autora_reader`，API 設、網域 `.aisiwhale.com`；伺服器不讀 cookie（D-265） | 不變；瀏覽器向 API 要會員版 |
| Node 套件 | 無原生模組；`nodejs_compat` | OK（bundle 9,099 KiB，gzip 1,779 KiB，低於 Paid 10 MiB 上限） |
| 環境變數 | 公開值寫在 `wrangler.jsonc` 的 `vars`，`scripts/cf-build.mjs` 在 build 時帶入；`SITE_OPERATOR_OWNER`、`SITE_CONTACT_PHONE` 只放 Worker secret | 見第 6 節 |
| CORS | Render `CORS_ORIGINS` 已加 `https://cf.aisiwhale.com` | 預檢：cf 網域 200（帶 credentials），其他來源 400 |

### vinext vs OpenNext → 選 OpenNext

- **OpenNext（`@opennextjs/cloudflare`）**：用原本的 `next build` 輸出改包成 Worker；App Router、ISR、`revalidate`、Data Cache、rewrites 都由 Next 本身處理。改動只有設定檔。
- **vinext 1.4.5**：Vite 重新實作的 Next API，等於換掉整套建置工具；字型改為執行時載入；官方說明它不是每個正式專案都能直接替換。這次的前提是「不做不必要的重構」，所以不選。

## 2. 設定與資源

- `frontend/web/open-next.config.ts`：增量快取 = R2 ＋ `withRegionalCache`（`long-lived`）；重算佇列 = Durable Object（`DOQueueHandler`）；`enableCacheInterception`（快取命中時不載入 Next 伺服器）。
- `frontend/web/wrangler.jsonc`：`nodejs_compat`、`global_fetch_strictly_public`；`workers_dev: false`；R2 `aisiwhale-web-opennext-cache`（APAC）；DO `NEXT_CACHE_DO_QUEUE`（SQLite）；observability 開啟。
- `public/_headers`：`/_next/static/*` 改為 `public, max-age=31536000, immutable`（原本 `max-age=0`，每次造訪都重驗）。
- `src/app/robots.ts`：依請求的 host 回應；非正式網域（如 cf.aisiwhale.com）一律 `Disallow: /`，避免測試站被收錄。
- `eslint.config.mjs`：忽略 `.open-next/`、`.wrangler/` 建置輸出。
- 指令：`pnpm cf:build`、`pnpm cf:preview`（本機 workerd）、`pnpm cf:deploy`。
- 部署版本：`33fcbc6f`、`69028971`（目前）。

## 3. 驗證結果（cf.aisiwhale.com）

| 項目 | 結果 |
|---|---|
| 首頁（兩種語言）、分頁籤、第 2 頁 | OK，第一次 `MISS`，之後 `x-opennext-cache: HIT` |
| 文章（免費／會員限定） | OK；未登入看到付費牆 |
| 股票頁 2330、NVDA（含手機版 K 線） | OK |
| 機構排行、三大法人、機構頁、人物持股 | OK |
| 排行搜尋 `?q=` | 每次渲染，`private, no-store`（刻意） |
| SEO | canonical 指向 `https://aisiwhale.com/…`；sitemap 206 個網址；測試站 robots `Disallow: /` |
| 手機版（375 寬） | 文章、股票頁正常 |
| 公開快取不含會員內容 | 會員限定文章：不帶 cookie 與帶 `autora_reader` cookie 取得的 HTML **位元組相同**（同一份快取，含付費牆），回應無 `Set-Cookie` |
| 會員功能 | 見 3.1 |

### 3.1 會員功能

用使用者自己已登入 cf.aisiwhale.com 的 Chrome 工作階段做**唯讀**驗證（沒有按解鎖、沒有扣 COIN、沒有付款、沒有改會員資料）。測試帳號：`tier=free`，具 `admin`、`coins`、`watchlist` 權限，不是 VIP。

| 項目 | 結果 |
|---|---|
| 登入狀態 | 瀏覽器帶 `.aisiwhale.com` cookie 向 `api.aisiwhale.com/api/auth/me` 取得帳號 → OK |
| 會員徽章／帳號 | 版頭顯示帳號按鈕（「帳號：…」與頭像），取代「登入」→ OK |
| 會員限定文章 | 瀏覽器有帶 cookie 重新要讀者版本（`/api/public/articles/…`）；API 對這個帳號回 `locked=true`、`lock=members`，頁面正確顯示「VIP 會員專屬報導」付費牆。**VIP 全文顯示沒有驗證到**：需要一個 VIP 帳號；D-265 時在本機 `next start`＋假 API 驗證過「API 回全文 → 頁面顯示全文」，Workers 上沒有重驗 |
| Watchlist | `/api/me/watchlist` 200，33 筆；頁面顯示「我的觀察清單」→ OK |
| Coins | `/api/me/coins` 回餘額與明細，頁面「我的鯨幣」顯示餘額 → OK |
| 公開快取是否洩漏 | 首頁、會員文章、股票 2330、機構排行、Watchlist、Coins 六頁，帶 cookie 與不帶 cookie 各取一次：HTML 都**不含**該帳號 email 與 reader id，都沒有 `Set-Cookie`；觀察清單項目與 COIN 餘額都不在伺服器 HTML 中（由瀏覽器另向 API 取得） |

## 4. 實測 CPU 與請求量（`wrangler tail`，183 個請求，166 個有紀錄）

| 類型 | 次數 | CPU 中位數 | p95 | 最大 |
|---|---|---|---|---|
| 快取命中 | 125 | 13 ms | 39 ms | 702 ms |
| 第一次渲染 | 38 | 24.5 ms | 425 ms | 654 ms |
| 排行搜尋 | 3 | 59 ms | — | — |

- 全部平均 40 ms；這輪命中率 75%（大多是第一次造訪，正式流量會更高）。
- 背景重算 RPC（DO 佇列）9 次，全部 `ok`。
- **Workers Free 不可行**：每次呼叫 CPU 上限 10 ms，快取命中的中位數就有 13 ms。

## 5. 費用估算（Workers Paid，價格依 Cloudflare 2026-10 文件）

- Workers Paid：每月 $5，含 1,000 萬請求、3,000 萬 CPU 毫秒；超過 $0.30／百萬請求、$0.02／百萬 CPU 毫秒。靜態檔請求免費。
- R2：$0.015/GB-月；Class A $4.50／百萬、Class B $0.36／百萬；免費額度 10 GB、100 萬 A、1,000 萬 B；無出口費。
- Durable Objects：含 100 萬請求，之後 $0.15／百萬。
- 假設：命中率約 95%、平均 CPU 約 30 ms／請求。Vercel 的實際請求數拿不到（Vercel 連線需要團隊重新授權），所以以下是情境，不是帳單：

| 每月 Worker 請求 | Workers | R2＋DO（粗估） | 合計 |
|---|---|---|---|
| 100 萬 | $5.00 | 約 $0 | 約 $5 |
| 500 萬 | $5 ＋ CPU $2.40 | 約 $1 | 約 $8 |
| 2,000 萬 | $5 ＋ 請求 $3 ＋ CPU $11.40 | 約 $3–7 | 約 $22–26 |

正式上線一週後，用 Cloudflare 後台 Workers → Metrics（Requests、CPU time）與 R2 Class A/B 用量重算。

## 6. 為什麼落在 San Jose（SJC）

- Workers 沒有「執行區域」設定：請求由**收到它的那個 Cloudflare 機房**執行。所以 SJC 是網路入口問題，不是 Worker 放置問題。
- 實測（中華電信 HiNet，AS3462，板橋）：
  - `cf.aisiwhale.com`、`aisiwhale.com`、`api.aisiwhale.com` → `colo=SJC`。這個區網解析到 `104.21.37.28`、`172.67.203.106`。
  - 同一條線路連 `www.cloudflare.com`、`1.1.1.1` → `colo=TPE`。
  - traceroute：到 `104.21.37.28` 在 HiNet 國際出口（`202.39.x`）後跳到約 127–155 ms，進的是美國機房；到 `1.1.1.1` 全程約 5 ms。
- 結論：HiNet 把 aisiwhale 這個區網所在的 Cloudflare 共用位址段送去美國；Cloudflare 自家位址段則留在台北。這是 ISP 與 Cloudflare 之間依方案／位址段的路由，**程式或 Worker 設定改不了**；Smart Placement 只會把執行移向後端，不會把入口拉回台北。
- 影響：從 HiNet 連入，每個請求多約 130 ms 往返＋TLS 交握。快取命中在 Worker 內約 150 ms。
- 可行做法（都不需動快取架構）：
  1. 先用其他台灣網路（台哥大、遠傳、中華行動網路）各測一次 `https://cf.aisiwhale.com/cdn-cgi/trace` 的 `colo`；不同 ISP 結果可能不同。
  2. 若主要讀者在 HiNet 而延遲不能接受：詢問 Cloudflare 較高方案（Pro／Business／Enterprise）在 HiNet 是否進 TPE。這裡**沒有驗證**哪個方案會改變，不要先付費再期待。
  3. 正式切換前，可在 Vercel 恢復後比較同一台電腦連 Vercel 的 TTFB，再決定。
- 已確認不會做的：為了換機房而改用其他 CDN 前置、拆掉 R2／DO 快取。

## 7. 正式網域切換方案（驗證通過後才做）

前置（不影響正式站）：
1. 在 Worker 設 secret：`wrangler secret put SITE_OPERATOR_OWNER`、`wrangler secret put SITE_CONTACT_PHONE`（由負責人自己輸入，不進版控）；若註冊頁用 Turnstile，設對應的 site key。
2. 確認 Render `CORS_ORIGINS` 保留 `https://aisiwhale.com`、`https://www.aisiwhale.com`。
3. Google OAuth：回呼網址依 `SITE_BASE_URL`（`https://aisiwhale.com`），切換後不變。
4. `wrangler.jsonc` 的 `routes` 加上：
   ```jsonc
   { "pattern": "aisiwhale.com", "custom_domain": true },
   { "pattern": "www.aisiwhale.com", "custom_domain": true }
   ```
   （先在 PR 準備好，不要部署）

切換（選低流量時段）：
5. Cloudflare DNS：記下 `aisiwhale.com`、`www` 目前指向 Vercel 的紀錄（截圖／匯出）。
6. 刪除這兩筆 Vercel 紀錄後，`pnpm cf:deploy` 讓 Worker 建立 custom domain（custom domain 需要該名稱沒有衝突的 DNS 紀錄）。
7. 立刻驗證：`curl -sI https://aisiwhale.com/news/zh-TW` 看 `x-opennext-cache`；robots.txt 回正式規則；會員登入、付費文章、PAYUNi 回傳頁（**用測試交易或不交易**）。
8. 監看 `wrangler tail` 與 Workers Metrics 1 小時。

回退：
- 從 `wrangler.jsonc` 移除兩條 route 並部署（或後台刪 custom domain），把第 5 步記下的 Vercel 紀錄加回去；Vercel 專案保留不刪，直到 Cloudflare 穩定運作至少兩週。

切換後：
- 在 Cloudflare WAF 加 `/news/*` 每 IP 速率限制（取代 D-265 原本規劃的 Vercel Firewall）。
- 一週後依實際 Metrics 更新第 5 節費用。
