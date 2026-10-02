# 17 雲端部署計畫（Vercel ＋ Render ＋ Neon ＋ Cloudflare）

2026-10-01 草擬（D-151）。使用者選定：後端 Render 新加坡、資料庫 Neon 新加坡、前端 Vercel、DNS／圖片 Cloudflare。
本文件只是計畫：**開帳號、付費、改 DNS、上線都由使用者確認後才做**。

## 1. 架構

| 元件 | 放在哪 | 說明 |
|---|---|---|
| 網站＋後台（Next.js 16） | **Vercel** | `aisiwhale.com`、`www.aisiwhale.com` |
| API（FastAPI，含 WebSocket） | **Render** Web Service，新加坡 | `api.aisiwhale.com`；`/health` 健康檢查 |
| Worker（代理、排程、每日週期） | **Render** Background Worker，新加坡 | 必須一直開著；排程在它裡面跑（沒有外部 cron） |
| Postgres 18＋pgvector | **Neon**，新加坡（aws-ap-southeast-1） | 用**直連端點**（不用 `-pooler`），見 §3.2；本機與 CI 也是 18（D-152） |
| DNS、首圖、品牌標誌 | **Cloudflare** | R2 已在用：`img.aisiwhale.com` |
| Email | Resend | 寄信網域需驗證 `aisiwhale.com` |
| 金流 | PayUni | 回呼網址改成正式網域 |

同一區域（新加坡）放 API、Worker、資料庫，查詢不跨海；台灣讀者到 Vercel 走最近的邊緣節點。

## 2. 估計費用（每月，以 2026 年中的價目為準，開帳號前再確認）

| 項目 | 方案 | 約 |
|---|---|---|
| Render API | Starter（512 MB） | US$7 |
| Render Worker | Starter（512 MB）；代理多時可能要 Standard（2 GB，US$25） | US$7–25 |
| Neon | Launch（依用量；小型約 US$5–20） | US$5–20 |
| Vercel | Hobby 免費（**不可商用**）；有付費會員就要 Pro US$20 | US$0–20 |
| Cloudflare | DNS 免費；R2 10 GB 內免費 | ~US$0 |
| 合計 | | **約 US$20–70** ＋模型與資料 API 用量 |

> Vercel Hobby 條款不允許商業用途；網站有付費會員（D-025），正式收費前應改 Pro。

## 3. 上線前要改的程式（2026-10-01 已完成，D-153）

1. **共用的 Blob 存放改到 R2**（必要）。現在代理的對話紀錄、證據快照存在本機磁碟（`LocalFSBlobStore`）：
   Render 的 API 與 Worker 是兩台機器、磁碟不共享，每次部署也會清空 → 後台看不到執行紀錄、代理中斷後無法續跑。
   做法：新增 `R2BlobStore`（沿用已寫好的 Signature V4），存在 R2 的私有路徑（例如另一個私有 bucket `aisiwhale-private`），**不能**放在公開的圖片 bucket。
2. **資料庫連線**：Neon 給的網址是 `postgres://…?sslmode=require`，要改成 `postgresql+asyncpg://…?ssl=require`。
   用**直連端點**：即時推播用 `LISTEN`，且 asyncpg 預設會用 prepared statement，兩者都不能經過 Neon 的連線池（PgBouncer transaction mode）。
   每個程序最多 10 條連線（pool 5＋overflow 5），API＋Worker 約 20 條，在 Neon 限額內。
3. **讀者登入 cookie 跨子網域**：cookie 由 API（`api.aisiwhale.com`）設定，目前沒有 `domain`，只屬於 API 網域；
   網站伺服器端渲染文章時讀不到 → 會員文章永遠顯示成未登入。新增設定 `COOKIE_DOMAIN=.aisiwhale.com`，讀者與管理員 cookie 都帶上。
4. **部署設定檔**：`render.yaml`（API、Worker、部署前執行 `alembic upgrade head`）；Vercel 專案設 Root Directory `frontend/web`。
5. **自動化**：CI 通過後才部署（Render、Vercel 都可設「只部署 main 且 CI 綠燈」）。

完成情形（D-153）：
- §3.1：`infra/s3.py`（簽章與 R2 存取）、`R2BlobStore`、`build_blob_store`（設 `BLOB_R2_BUCKET` 就用私有 bucket）；所有讀寫 blob 的地方都改走它；上線當天用 `backend/scripts/blobs_to_r2.py --bucket aisiwhale-private` 搬本機 `data/blobs`（181 MB，可重跑）。
- §3.2：`DATABASE_URL` 可直接貼 Neon 給的 `postgresql://…?sslmode=require&channel_binding=require`；程式自動改成 asyncpg 格式，`sslmode` 變成**驗證憑證**的 TLS（certifi），丟掉 asyncpg 不認得的 `channel_binding`；遷移也用同一套。
- §3.3：`COOKIE_DOMAIN`（讀者與管理員的 cookie，登入與登出都帶）。
- §3.4：根目錄 `render.yaml`（API Web Service＋Worker、新加坡、Starter、CI 綠燈才部署、部署前 `alembic upgrade head`、`/health`；43 個環境變數，機密標 `sync: false` 在建立時填）。
- 以 render.yaml 的值加上假機密，模擬正式環境載入設定：通過。

## 4. 使用者要做的帳號設定（照順序）

1. **Neon**：建立專案（Region：AWS Singapore），資料庫名 `autora`；記下**直連**連線字串（不是 pooled）。
2. **Cloudflare R2**：另建一個**私有** bucket（例：`aisiwhale-private`，不開公開存取）給 §3.1；沿用現有 API 金鑰或另發一把只能讀寫這兩個 bucket 的。
3. **Render**：New → Blueprint → 連結 GitHub `devince1105/aisiwhale`（讀根目錄的 `render.yaml`，自動建立 `aisiwhale-api` 與 `aisiwhale-worker`，新加坡）；畫面會列出所有 `sync: false` 的變數讓你填（§5），`API_BEARER_TOKEN` 自動產生。
4. **Vercel**：匯入同一個 repo，Framework「Next.js」，Root Directory `frontend/web`（保留「Include files outside the root directory」，因為它用到 `frontend/event-schema`），Install Command 用預設（偵測到 pnpm workspace）；填 §5 的環境變數；Production 分支 `main`。
5. **Cloudflare DNS**：
   - `aisiwhale.com`、`www` → Vercel（Vercel 會給 A／CNAME 記錄；Cloudflare 代理設「DNS only」灰雲，讓 Vercel 簽憑證）
   - `api` → Render 給的 `*.onrender.com`（CNAME，DNS only）
   - `img` → R2（已完成）
6. **Resend**：驗證寄信網域 `aisiwhale.com`（加 SPF／DKIM 記錄），`EMAIL_FROM` 改成 `艾矽鯨 <news@aisiwhale.com>` 之類。
7. **PayUni**：後台的回呼網址改成 §5 的正式網址（先用 sandbox 測一筆）。

## 5. 環境變數

### Render：API 與 Worker 共用（建議用 Render 的 Environment Group）

| 變數 | 值 |
|---|---|
| `AUTORA_ENV` | `prod` |
| `DATABASE_URL` | `postgresql+asyncpg://…@…neon.tech/autora?ssl=require`（直連） |
| `API_BEARER_TOKEN` | 新的長亂數（不可沿用開發用的） |
| `ADMIN_EMAILS` | 管理員信箱（JSON 陣列） |
| `SITE_BASE_URL` | `https://aisiwhale.com` |
| `CORS_ORIGINS` | `["https://aisiwhale.com","https://www.aisiwhale.com"]` |
| `COOKIE_DOMAIN` | `.aisiwhale.com`（§3.3 新增） |
| 模型 | `MODEL_PROVIDER`、`OPENAI_API_KEY`、`FRONTIER_MODEL_ID`、`FAST_MODEL_ID`、`MODEL_PRICES`、`MODEL_DAILY_CAP_USD` |
| 嵌入 | `EMBED_PROVIDER`、`EMBED_MODEL_ID`（＋其金鑰） |
| 工具 | `TOOLS_PROFILE=live`、`TAVILY_API_KEY`、`FETCH_CONTACT_EMAIL` |
| 行情 | `FRED_API_KEY`、`FINNHUB_API_KEY`、`TIINGO_API_KEY`、`FUGLE_API_KEY` |
| 首圖 | `PIXABAY_API_KEY`、`GEMINI_API_KEY`、`COVER_IMAGE_MODEL`、`R2_ACCOUNT_ID`、`R2_ACCESS_KEY_ID`、`R2_SECRET_ACCESS_KEY`、`R2_BUCKET`、`R2_KEY_PREFIX`、`R2_PUBLIC_BASE_URL` |
| 私有 Blob | `BLOB_R2_BUCKET`（§3.1 新增） |
| Email | `EMAIL_PROVIDER=resend`、`RESEND_API_KEY`、`EMAIL_FROM` |
| 金流 | `PAYUNI_ENV`、`PAYUNI_MER_ID`、`PAYUNI_HASH_KEY`、`PAYUNI_HASH_IV`、`PAYUNI_RETURN_URL=https://aisiwhale.com/news/zh-TW/membership/return`、`PAYUNI_NOTIFY_URL=https://api.aisiwhale.com/api/payments/payuni/notify` |
| 其他 | `OFFICIAL_TRADES_ENABLED`、`WORKER_CONCURRENCY` |

### Vercel

| 變數 | 值 | 備註 |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `https://api.aisiwhale.com` | **建置時**寫入；改了要重新部署 |
| `API_INTERNAL_URL` | `https://api.aisiwhale.com` | 伺服器端用 |
| `NEXT_PUBLIC_SITE_COMPANY`、`SITE_COMPANY` | `aisiwhale` | 公司代號（原 `autora-finance`，D-154） |
| `SITE_OPERATOR`、`SITE_OPERATOR_OWNER`、`SITE_CONTACT_EMAIL`、`SITE_CONTACT_PHONE` | 經營者資訊 | 個人資料只放 Vercel，不進 repo |
| `SITE_MEMBERSHIP_OPEN` | | |

## 6. 資料搬家

選一種（建議 A）：
- **A. 搬現有資料**：`pg_dump`（本機 docker）→ `pg_restore` 到 Neon；文章、題材、首圖紀錄、會員都保留。本機 `data/blobs` 依 §3.1 上傳到私有 bucket。
- **B. 全新開始**：Neon 上跑 migration、建立公司；舊文章不帶過去。

## 7. 上線順序

1. 程式修改（§3）合併、CI 綠燈。
2. Neon 建好 → 本機對 Neon 跑 `alembic upgrade head` → 搬資料（§6）。
3. Render 建 API（先用 `*.onrender.com` 網址）→ `/health` 正常、WebSocket 連得上。
4. Render 建 Worker → 看 log 有 scheduler tick、沒有錯誤。**本機的 worker 要停掉**，避免兩邊同時跑同一家公司。
5. Vercel 部署（先用 `*.vercel.app` 預覽網址，`CORS_ORIGINS` 暫時加上它）。
6. 全部驗收：首頁、文章、首圖、登入信、後台審批、辦公室即時畫面、PayUni sandbox 一筆。
7. 切 DNS（§4.5）→ 改 `SITE_BASE_URL`、`CORS_ORIGINS` 成正式網域 → 重驗一次。
8. 觀察一個完整的每日週期（14:00）。

**回退**：DNS 指回原處；Render／Vercel 都可一鍵回到上一版；資料庫有 Neon 的時間點還原。

## 7.1 已完成（2026-10-01）

- Neon 專案 `aisiwhale`、分支 `production`、資料庫 `aisiwhale`（PostgreSQL 18.6、pgvector 0.8.6），直連字串在 `.env` 的 `NEON_DATABASE_URL`（尚未取代 `DATABASE_URL`）。
- 家用網路擋 5432；手機熱點可連（從本機 174 ms／查詢；從 Render 新加坡會是個位數毫秒）。資料搬家要在熱點下做。
- 本機 Python（python.org 版）沒有系統憑證：本機連 Neon 要用 `certifi` 的憑證（或執行 Applications/Python 3.12/Install Certificates.command）；雲端不受影響。
- 本機與 CI 已升級到 Postgres 18（D-152）。
- Render Blueprint 建立 `aisiwhale-api` 與 `aisiwhale-worker`（新加坡、Starter），先只填啟動必要的 5 個機密（`DATABASE_URL`、`TAVILY_API_KEY`、三個 R2）。API 在 `https://aisiwhale-api.onrender.com`：`/health` 200、公開 API 連到 Neon（部署前遷移已建表，回空清單）、管理 API 無權杖 401、CORS 允許 `https://aisiwhale.com` 含 cookie、WebSocket 連得上（錯誤權杖回 unauthorized）。上線前要補第 ② ③ 類變數（模型、嵌入、管理員、首圖、行情、金流、Email）。
- R2 私有 bucket `aisiwhale-private`（APAC，未開公開網址）已建立；API 金鑰（`a73d48…`）的權限涵蓋 `aisiwhale` 與 `aisiwhale-private`。實測：寫入、讀回相同、沒有金鑰的請求被拒（400）、刪除後讀不到；首圖 bucket 照常可讀寫。

## 7.2 上線（2026-10-01 晚）

- **網域**：`aisiwhale.com`、`www` → Vercel（CNAME `adc91c2b90e38b1a.vercel-dns-017.com`），`api` → Render（CNAME `aisiwhale-api.onrender.com`），全部橘雲、SSL/TLS Full (strict)。先灰雲等 Vercel／Render 自行簽 Let's Encrypt／Google 憑證，再改橘雲。Cloudflare 原產地證書用不到（Vercel、Render 都不能上傳），已撤銷。`news.aisiwhale.com` 不做；要做也只用 Cloudflare 301 轉到 `www…/news`。Bot Fight Mode 不可開（會擋 PayUni 通知）。
- **Render ②③ 類變數**：Blueprint 的 `sync: false` 會先建好空欄位，「Add from .env」遇到同名會報 Duplicate key；做法是先刪掉空的那幾列、同一次編輯裡再貼上。
- **資料搬家（§6 選 A）**：暫停 Render worker → 停本機 worker → 容器內 `pg_dump -Fc --no-owner --no-acl` → 手機熱點下 `pg_restore --clean --if-exists --no-owner --no-acl --single-transaction`，用 `-L` 清單略過 `vector` 擴充與其註解（Neon 已有，重建需擁有者權限，一個錯就整筆回滾）→ 65 張表逐表筆數與本機相同。私有 blob 4443 個（197 MB）走 443 埠，家用網路即可上傳。
- **Vercel**：`NEXT_PUBLIC_API_URL` 若建成 Secret 類型，改值會被擋（公開前綴不得為 Secret），要刪掉重建為 Config；改完 Redeploy 且不用建置快取。驗證：瀏覽器端 JS 內嵌 `api.aisiwhale.com`、從 `www` 跨網域帶 cookie 讀 API 200、文章頁首圖從 `img.aisiwhale.com` 載入。
- 本機 worker 自此停用；本機資料庫不再是正式資料。

## 7.3 正式資料庫刪除三家測試公司（2026-10-02）

`echo-demo`、`newsroom-demo`、`smoke-*` 隨資料搬家帶到 Neon，後台在新瀏覽器會開到它們。手機熱點下一筆交易刪除：先檢查剛好 3 家且不含 aisiwhale，交易內暫停 7 個 append-only 觸發器、依外鍵由子表往上逐輪刪除（4 輪）、刪公司、恢復觸發器、提交。刪除前後艾矽鯨的事件 21,580、任務 568、文章 37、成員 8、核准 48 完全相同；全部事件由 22,416 減為 21,580；觸發器 7 個仍啟用。事前在本機副本演練過。**同時發現** Neon 的遷移版本仍是 0058：當天 D-156／D-157／D-159 的後端尚未部署到 Render（待查 Render Events）。

## 8. 待決定

- §6 選 A 或 B。
- Vercel Hobby 或 Pro（有收費就要 Pro）。
- Worker 先用 Starter（512 MB）觀察記憶體，不夠再升級。
- 正式上線前：Tiingo、Finnhub、富果的商用方案（D-059、D-061、D-074 已註記）。
