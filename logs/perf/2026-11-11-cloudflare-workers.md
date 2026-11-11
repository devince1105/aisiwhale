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

## 8. 正式切換前最後檢查（2026-11-11，唯讀，未改 DNS）

### 8.1 VIP 權限與會員等級

- 等級只由 `autora/accounts/entitlement.py` 決定：`public`／`free`／`vip`；`vip` 只看「這家公司有沒有進行中的會員資格」（買的或贈送的）。`admin` 與等級無關，只多一個 `admin` 能力（可開後台）。
- 會員限定（`lock=members`）文章：`routers/public.py` 的 `get_article` 呼叫 `entitlement_for` 時**沒有傳 `admin_emails`**，要求的是 `READ_VIP_ARTICLES`（只有 `vip` 有）→ admin 不會因為是 admin 讀到 VIP 全文。實測：admin 帳號（`tier=free`）在 cf.aisiwhale.com 看到 VIP 付費牆。✅
- **例外（既有設計，未改）**：COIN 文章（`lock=coin`）admin 不付費可讀（程式註解：「an admin reads it unpaid」，`reader="staff"`）。這不是 VIP 權限；若不要，另案改。

### 8.2 PAYUNi

| 項目 | 設定 | 與前端網域的關係 |
|---|---|---|
| 結帳 | `CHECKOUT_OPEN = False`（寫死在 `entitlement.py`，P8 才開） | 目前無法建立交易 |
| NotifyURL（伺服器對伺服器，決定開通） | `https://api.aisiwhale.com/api/payments/payuni/notify`（render.yaml） | 在 API，**不受前端切換影響** |
| ReturnURL（讀者瀏覽器回來） | `https://aisiwhale.com/news/zh-TW/membership/return`（render.yaml） | 由前端處理；表單內容不讀、不授權任何東西，只 303 到 `…/membership/done` |
| 在 Workers 上 | `POST /news/zh-TW/membership/return` → 303 → `/membership/done` 200（測試資料，未呼叫 PAYUNi） | ✅ |

ReturnURL／NotifyURL 每筆交易帶給 PAYUNi，不在 PAYUNi 後台設定；切換不需改 PAYUNi。開放付款前，PAYUNi 商店審核看的網站頁面（條款、退款、聯絡）需要負責人與電話（見 8.3）。

### 8.3 Workers 環境變數與 Secrets

前端讀的變數：`NEXT_PUBLIC_API_URL`、`API_INTERNAL_URL`、`NEXT_PUBLIC_SITE_COMPANY`、`SITE_COMPANY`、`NEXT_PUBLIC_SITE_URL`、`SITE_BASE_URL`、`SITE_OPERATOR`、`SITE_CONTACT_EMAIL`（都已在 `wrangler.jsonc`），以及：

| 變數 | Vercel 正式環境 | Worker | 處理 |
|---|---|---|---|
| `NEXT_PUBLIC_TURNSTILE_SITE_KEY` | 有（Production） | ✅ 已補（第二輪，見 8.6） | 公開值，放 `wrangler.jsonc` 的 `vars` |
| `SITE_OPERATOR_OWNER` | 沒有 | 沒有 | 選用（Vercel 上也沒有，頁面原本就不顯示）；開放付款前補 |
| `SITE_CONTACT_PHONE` | 沒有 | 沒有 | 同上 |

設定 secret（互動輸入，值不進 shell 歷史與版控；OpenNext 每個請求把 secret 放進 `process.env`，ISR 頁最多 300 秒後更新）：

```bash
cd frontend/web && pnpm exec wrangler secret put SITE_OPERATOR_OWNER
```
```bash
cd frontend/web && pnpm exec wrangler secret put SITE_CONTACT_PHONE
```

Turnstile site key 取自 Cloudflare 帳號裡的 widget `aisiwhale-contact`（API 讀取，沒有解密 Vercel 的值）。

### 8.4 R2、Durable Objects、快取與 DNS 切換後的行為

- 快取鍵：`incremental-cache/<buildId>/<路徑雜湊>`，**不含 host**。cf.aisiwhale.com 暖好的快取，切換後 `aisiwhale.com` 直接共用；兩個網域看到的 HTML 相同（canonical 由 `SITE_URL` 決定，不看 host）。
- 每次 `cf:deploy` 換 buildId → 該版快取從空開始，舊版物件留在 R2（量小；之後可設 R2 lifecycle 清 30 天前的物件）。
- 重算：過期後第一個請求拿舊版、DO 佇列在背景重算（同一路徑去重）。DO、R2 綁定在 Worker 上，與網域無關。
- regional cache：每個機房自己的 Cache API，`long-lived`。
- Cloudflare CDN 快取不會快取 custom domain Worker 的 HTML；**不要**為這個網域加 "Cache Everything" 類的 Cache Rule。
- 會員 cookie 是 `.aisiwhale.com`：apex、www、cf 都送得到 API；CORS 已含三者。
- robots.txt：`aisiwhale.com`、`www.aisiwhale.com` 回正式規則；其他 host（cf）回 `Disallow: /`。
- 區網方案：**Free**。DNS 紀錄與規則在第二輪用後台確認（見 8.6）。

### 8.5 主網域（已決定）

**主網域 = `https://aisiwhale.com`；`www.aisiwhale.com` 301 永久轉到主網域（保留路徑與查詢字串）。** 程式與 Render 原本就以 apex 為準，不用改設定。Vercel 原本是 apex → www（308），搜尋引擎收錄的 www 網址會經 301＋canonical 換成 apex（短期排名可能波動）。

### 8.6 第二輪：切換前準備（2026-11-11，未切換、未改 DNS、未付款）

**Turnstile**
- Widget `aisiwhale-contact`（managed）原本允許 `aisiwhale.com`、`www.aisiwhale.com`，本次以 API 加上 `cf.aisiwhale.com`（三個都明列）。
- `wrangler.jsonc` 加 `NEXT_PUBLIC_TURNSTILE_SITE_KEY`，重新部署 cf（版本 `d5853b86`）；site key 確實在 contact 頁的瀏覽器程式裡。
- 實測（Chrome，cf.aisiwhale.com）：Turnstile 顯示「成功」、送出一則標明「測試，請忽略」的留言 → API **202**、頁面顯示「已收到你的留言」。對照：不帶 token 直接 POST → **403**（Render 有設 `TURNSTILE_SECRET_KEY`，驗證確實在作用）。Email 欄填的是 `service@aisiwhale.com`。

**VIP 與會員權限（規則未改）**
- VIP 全文不經過 Worker：Worker 只給「未登入版本」（付費牆）；全文是瀏覽器帶 `.aisiwhale.com` cookie 直接向 `api.aisiwhale.com` 要的。cf 的 CORS 已允許（預檢回 `access-control-allow-origin: https://cf.aisiwhale.com`、credentials true），Watchlist／Coins 走同一條路徑，已在 cf 驗證過。
- API 測試：`test_a_member_reads_the_whole_thing`（買的）、`test_a_comp_reads_the_whole_thing_until_it_is_ended`（後台贈送），本次新增 `test_an_admin_is_not_a_member`：已驗證信箱、在 `ADMIN_EMAILS` 的 admin，`/api/auth/me` 有 `admin` 能力、等級 `free`，會員限定文章仍是 `locked`。
- 在 cf 上以真實 VIP 帳號看全文：**尚未做**。安全做法：後台「贈送 VIP」給一個測試帳號 1 天（`admin_comp`，不產生訂單、不收款），在 cf 看一篇會員文章，再於後台結束贈送。會在正式資料庫留下一筆贈送紀錄（設計上保留），所以等你同意再做。

**Cloudflare 區網現況（後台／dashboard API 唯讀）**

| 項目 | 現況 | 切換時 |
|---|---|---|
| Worker custom domains | 只有 `cf.aisiwhale.com` → aisiwhale-web | 加 `aisiwhale.com` |
| Worker routes | 無 | — |
| Redirect Rules／Cache Rules／Custom WAF／Transform／Origin／Config Rules | 都沒有（各 phase 沒有 entrypoint） | 新增一條 www → apex |
| Page Rules | 無 | — |
| Rate limiting | `contact-form-flood`：只比對 `api.aisiwhale.com` 的 `/api/public/contact` POST | 不影響 |
| Managed rulesets | Cloudflare Free Managed、Normalization、DDoS L7 | 不影響 |
| SSL/TLS | Full；**Always Use HTTPS = off**；Automatic HTTPS Rewrites on | **要開 Always Use HTTPS**（之前是 Vercel 把 http 308 到 https；改由 Worker 回應後 http 會直接 200） |

**DNS 現況（切換前備份；只會動前兩筆）**

| 名稱 | 類型 | 內容 | Proxy |
|---|---|---|---|
| `aisiwhale.com` | CNAME | `cname.vercel-dns.com` | Proxied |
| `www.aisiwhale.com` | CNAME | `adc91c2b90e38b1a.vercel-dns-017.com` | Proxied |
| `api.aisiwhale.com` | CNAME | `aisiwhale-api.onrender.com` | Proxied |
| `img.aisiwhale.com` | R2 | `aisiwhale` | Proxied |
| `cf.aisiwhale.com` | Worker | `aisiwhale-web` | Proxied |
| `rsend`／`send.aisiwhale.com` | CNAME | `rsend-apne1.forge.rmta.net`／`send.forge.rmta.net` | DNS only |
| `aisiwhale.com` | MX ×3 | `route1/2/3.mx.cloudflare.net`（83／14／88） | — |
| `aisiwhale.com` | TXT | SPF `v=spf1 include:_spf.mx.cloudflare.net ~all` | — |
| `cf2024-1._domainkey`、`resend._domainkey`、`_dmarc` | TXT | DKIM／DMARC | — |

共 14 筆。切換前在後台 DNS → Records → **Export** 下載 BIND 檔另存（不進版控）。

**網址一致性**

| 項目 | 值 | 與主網域 |
|---|---|---|
| canonical | `https://aisiwhale.com/news/…`（cf 上實測首頁、文章） | ✅ |
| sitemap.xml | 210 個 `<loc>`，全部 `aisiwhale.com` | ✅ |
| robots.txt | apex／www：正式規則＋`Sitemap: https://aisiwhale.com/sitemap.xml`；cf：`Disallow: /` | ✅ |
| Google 登入 | `redirect_uri=https://api.aisiwhale.com/api/auth/google/callback`（實測 start 的 303）；登入後 303 回 `SITE_BASE_URL` = apex | ✅ 不用改 Google Console |
| PAYUNi | ReturnURL `https://aisiwhale.com/news/zh-TW/membership/return`；NotifyURL 在 API；結帳關閉 | ✅ |
| Email 連結（驗證信、重設密碼） | `SITE_BASE_URL` = apex | ✅ |
| CORS | 線上 API 允許 apex、www、cf；`render.yaml` 原本少了 cf，本次補上使兩者一致 | ✅ |

### 8.7 切換流程（需你批准後才做）

Vercel 目前停用（apex、www 都回 402），**12/7 前回滾到 Vercel 也是 402**；切換期間的短暫中斷不會比現況差。

1. **備份**：後台 DNS → Export 存檔；確認上表兩筆 Vercel 紀錄。
2. **apex 給 Worker**：刪除 `aisiwhale.com` CNAME（Worker custom domain 不能和既有紀錄並存）→ `frontend/web/wrangler.jsonc` 的 `routes` 改成
   `[{ "pattern": "cf.aisiwhale.com", "custom_domain": true }, { "pattern": "aisiwhale.com", "custom_domain": true }]`
   → `cd frontend/web && pnpm cf:deploy`（Cloudflare 自動建 DNS 與憑證）。
3. **www 轉址**：`www` 紀錄改成 `AAAA www 100::`（Proxied）；Rules → Redirect Rules → 新增：When `http.host eq "www.aisiwhale.com"` → Dynamic，`concat("https://aisiwhale.com", http.request.uri.path)`，**301**，勾選 Preserve query string。
4. **HTTPS**：SSL/TLS → Edge Certificates → Always Use HTTPS = On。
5. **驗證**：
   ```bash
   curl -sI https://aisiwhale.com/news/zh-TW | grep -iE "^HTTP|x-opennext-cache"
   ```
   ```bash
   curl -sI "https://www.aisiwhale.com/news/zh-TW?page=2" | grep -iE "^HTTP|^location"
   ```
   ```bash
   curl -sI http://aisiwhale.com/news/zh-TW | grep -iE "^HTTP|^location"
   ```
   ```bash
   curl -s https://aisiwhale.com/robots.txt | head -3
   ```
   預期：200；301 → `https://aisiwhale.com/news/zh-TW?page=2`；301 → https；正式 robots。再用瀏覽器確認登入（含 Google）、Watchlist、Coins、聯絡我們，`pnpm exec wrangler tail aisiwhale-web` 看 1 小時。
6. 一週後確認 Search Console 收錄轉到 apex；穩定後再 commit `routes` 的變更（或切換當下就 commit）。

**回滾（約 2 分鐘）**
1. Workers → aisiwhale-web → Domains 移除 `aisiwhale.com`（或還原 `routes` 後 `pnpm cf:deploy`）。
2. 刪除 www 的 Redirect Rule。
3. 依備份加回 `aisiwhale.com CNAME cname.vercel-dns.com`、`www CNAME adc91c2b90e38b1a.vercel-dns-017.com`（都 Proxied）。
4. Always Use HTTPS 可維持 On（Vercel 原本也轉 https）。

### 8.8 結論

**技術上已具備切換條件**，剩一項建議在切換前做、需要你同意：
- 以後台贈送 VIP 給測試帳號（1 天，不收款），在 cf 實看會員文章全文，看完結束贈送。

已完成：主網域決定；Turnstile（cf 實測 202、無 token 403）；區網無衝突規則；canonical／sitemap／robots／Google 登入／PAYUNi 都指向 apex；DNS 備份與切換、回滾步驟。

不阻擋：COIN 文章 admin 可讀（既有設計）；負責人與電話（Vercel 上也沒有，開放付款前補）；PAYUNi 結帳仍關閉，未啟用真實付款。
