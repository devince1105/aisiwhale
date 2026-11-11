# 2026-11-11 Vercel Function 用量：公開網站改為 ISR（D-265）

aisiwhale 是團隊 Function 用量的主要來源。這次只改 `frontend/web`，目的是讓公開網站（`/news/*`）的頁面不再「每個請求跑一次 Function」。Vercel 目前停用，**沒有部署、也沒有正式環境的量測**；下面的「改善後」是本機 `next build` + `next start` 對著一個會記錄請求的假 API 量到的行為，Function 呼叫次數是由快取行為推算的估計值，不是 Vercel 的帳單數字。CPU 用量沒有量，不宣稱有降低。

## 1. 確認的前提

- Next.js **16.3.5**，App Router，**沒有**開 `cacheComponents`，所以用的是「舊模型」：route segment config（`revalidate`、`dynamicParams`、`generateStaticParams`）＋ `fetch` 的 Data Cache（`cache: "force-cache"`、`next.revalidate`、`next.tags`）。依據：`node_modules/next/dist/docs/01-app/02-guides/caching-without-cache-components.md`。
- 資料存取：伺服器端用 `openapi-fetch` 打 FastAPI（`SERVER_API_URL`）；沒有 ORM、沒有直接連資料庫。會員狀態是 API 設的 httpOnly cookie `autora_reader`（網域 `.aisiwhale.com`），API 的 CORS 已允許 `https://aisiwhale.com` 帶 credentials。
- `openapi-fetch` 以 `fetch(Request, init)` 呼叫；為了確定 Next 讀得到快取選項，改成在 `client()` 傳入自訂的 `fetch`，把選項明確放在第二個參數。

## 2. 改善前（`next build`，HEAD = a2d9f0e）

**`/news/[lang]` 底下 22 條公開路由全部是 `ƒ`（每個請求都在伺服器渲染）**，連隱私權、服務條款、聯絡我們都是。原因有三：

| 原因 | 影響的頁 |
|---|---|
| `[lang]` 沒有 `generateStaticParams`：動態路段沒有它就一律動態，`export const revalidate = 30/60/300` **從來沒有生效** | 全部 |
| 讀 `searchParams`（`?page=`、`?section=`、`?sort=`…） | 首頁、股票頁、機構排行、三大法人、機構頁、登入／註冊／重設密碼／驗證信 |
| `force-dynamic` ＋ `cookies()`（為了會員看全文） | 文章頁、人物持股頁、機構頁、方案價格頁 |

另外 `api.ts` 的每個 `fetch` 都沒有快取選項：每次渲染文章頁都向 API 重新要文章＋側欄五支（月曆、行情、熱門、行事曆、新聞情緒），首頁同樣再加文章列表。

## 3. 改善後

### 路由（`next build`）

| 路由 | 前 | 後 | 頁面快取時間（s-maxage） |
|---|---|---|---|
| `/news/[lang]`（首頁）＋ `?section/date/page/view` | ƒ | ● ISR | 120 秒 |
| `/news/[lang]/articles/[slug]` | ƒ（cookie） | ● ISR | 300 秒 |
| `/news/[lang]/stocks/[symbol]` ＋ `?page` | ƒ | ● ISR | 300 秒（原本寫 60） |
| `/news/[lang]/holdings/institutions` ＋ `?period/sort/order/page` | ƒ | ● ISR | 300 秒 |
| `…/institutions?q=`（搜尋） | ƒ | ƒ（刻意，`force-dynamic`；API 回應仍走 Data Cache） | — |
| `…/institutions/tw` ＋ `?day/group/side` | ƒ | ● ISR | 300 秒 |
| `…/institutions/[cik]` ＋ `?period` | ƒ（cookie） | ● ISR | 300 秒 |
| `…/holdings/people/[slug]` | ƒ（cookie） | ● ISR | 300 秒 |
| `/news/[lang]/pricing` | ƒ（force-dynamic） | ● ISR | 60 秒 |
| 登入、註冊、忘記／重設密碼、驗證信 | ƒ（searchParams） | ● ISR（查詢參數改在瀏覽器讀） | 300 秒 |
| 隱私權、條款、退款、聯絡、AI 編輯部、金幣、追蹤清單、付款完成 | ƒ | ● ISR | 300 秒 |
| `/news/[lang]/membership/return`（PAYUNi 回傳 POST） | ƒ | ƒ（必須） | — |
| `/robots.txt`、`/sitemap.xml` | 無 | ○ ／ ISR | sitemap 120 秒 |
| 不存在的語言（`/news/xx`） | ƒ 404 | ISR 404（快取） | 120 秒 |

`next build` 不預先產生任何頁（`generateStaticParams` 回傳 `[]`）：部署不依賴 API 是否在線，也不會把 API 掛掉時的空列表快取起來；每個網址第一次被要求時產生，之後在快取時間內不再跑 Function。頁面重算失敗時 Next 會繼續給舊版。所有頁的快取時間不超過版頭行情條的 300 秒（同一次渲染裡最短的 `revalidate` 決定整頁）。

### 怎麼做到

1. **查詢參數 → 路徑（`queryRoutes.ts` ＋ `next.config.ts` 的 `rewrites.beforeFiles`）**：`?section=ai&page=2` 在路由層（Function 之前）改寫到 `/news/zh-TW/browse/section/ai/page/2`，那頁是 ISR。網址列不變；每個值都要符合格式才改寫（`page` 只收 1–999、日期只收 `YYYY-MM-DD`、排序只收列舉值），其餘參數（`utm_source`、`fbclid`）不影響快取鍵。共 40 條規則，單元測試確認順序與對應。機構排行的搜尋框（`?q=`）是唯一例外：輸入不可預知，轉到每次渲染的 `…/institutions/search`，並設 `noindex`。
2. **會員資料與公開頁分離**：伺服器不再讀任何 cookie；頁面一律是「未登入讀者」看到的版本，被所有人共用。頁面有鎖（`locked`）時，瀏覽器帶自己的 cookie 直接向 API 要讀者自己的版本（`readerVersion.tsx`：`ArticleReader`、`PortfolioReader`、`InstitutionReader`）。`api.ts` 的 `keptFetch` 規定：**帶 cookie 的請求一律 `no-store`、不進 Data Cache**；有單元測試鎖住。COIN 解鎖後原本 `router.refresh()` 重抓伺服器頁，改為重抓讀者版本。機構第一次被開啟時是 `queued`，瀏覽器每 15 秒再問一次、最多 12 次（原本要靠重新整理）。
3. **側欄五支 API 的資料快取**：伺服器端公開讀取走 Data Cache（tag `public-api`）：列表 120 秒；行情、熱門、月曆、新聞情緒、股票頁、機構頁 300 秒；文章、持股、排行、三大法人 600 秒；行事曆、日 K、分析師評等、AI 編輯部樣式 3600 秒；分時線與股票搜尋不快取。同一個月、同一語言的所有文章頁共用同一份側欄資料，而不是每頁各要一次。瀏覽器端的呼叫（行情條、K 線、月曆換月）不受影響。
4. **revalidate 檢查**：首頁 30→120 秒、股票頁 60→300 秒、排行與三大法人 300（原本寫了但沒生效）、價格頁每次→60 秒。

### 本機實測（`next start` ＋ 會記錄請求的假 API）

| 網址 | 第 1 次 | 第 2 次 | 第 3 次（帶會員 cookie） | 第 1 次打 API 次數 → 第 2、3 次 |
|---|---|---|---|---|
| `/news/zh-TW` | MISS | HIT | HIT | 6 → 0、0 |
| `/news/zh-TW?section=ai&page=2` | MISS | HIT | HIT | 3 → 0、0（行情、熱門等已在 Data Cache） |
| 同上 `&utm_source=x` | HIT | HIT | HIT | 0 |
| `/news/zh-TW/holdings/institutions?sort=change&page=2` | MISS | HIT | HIT | 1 → 0、0 |
| `/news/zh-TW/articles/locked-story` | MISS | HIT | HIT | 3 → 0、0 |
| `/news/zh-TW/privacy` | MISS | HIT | HIT | 0 |
| `…/institutions?q=black` | 每次渲染（`private, no-store`） | 每次渲染 | — | 1 → 0（API 回應走 Data Cache） |

- 整輪測試**伺服器送到 API 的請求中帶 cookie 的：0 次**；帶會員 cookie 去要文章頁，回來的 HTML 不含會員全文，只有付費牆。
- 在瀏覽器裡：未登入看到付費牆；設了會員 cookie 重新整理後，全文由瀏覽器對 API 的請求（帶 cookie）取得並顯示。
- canonical：`https://aisiwhale.com/news/zh-TW?section=ai&page=2`（去掉 `utm_source`）、排行 `?sort=change&page=2`、文章用自己的 `path`；搜尋頁 canonical 指回不帶 `q` 的排行並 `noindex, follow`；`/admin/*` 回 `X-Robots-Tag: noindex, nofollow`。

## 4. Function 呼叫估計（沒有正式環境數據，為推算）

- **改善前**：`/news/*` 的每一個 HTML 請求、每一次站內換頁的 RSC 請求，都是一次 Function 呼叫；每次文章頁渲染再對 API 發 6 個以上請求。
- **改善後**：同一網址在快取時間內只有第一個請求（或背景重算）跑 Function。一個網址在 T 秒內被看 N 次，Function 呼叫從 N 次變成最多 ⌈期間 ÷ revalidate⌉ 次，與 N 無關。例：首頁一小時 3,000 次瀏覽 → 前 3,000 次，後最多 30 次（120 秒一次）；一篇文章一小時 200 次 → 前 200 次，後最多 12 次。
- **仍會呼叫 Function 的**：每個新網址的第一次、每個網址每個 revalidate 週期最多一次的背景重算、機構搜尋（`?q=`）、PAYUNi 回傳、admin 帶參數的頁（`/admin/cycles/[id]` 等，本次沒動，流量低）。
- **新增的成本**：ISR 寫入（每次重算寫一次快取）、Data Cache 讀寫。量級遠小於原本每次瀏覽一次 Function，但不是零。
- **改善幅度取決於流量分布**：流量集中在少數熱門網址（首頁、新文章）時降幅最大；爬蟲大量掃描從未被看過的舊網址（各種分頁、各檔股票）時，每個網址的第一次仍會跑 Function。這部分靠下一節。

## 5. 爬蟲

- `robots.txt`：允許 `/news/`；不讓爬登入、註冊、密碼、驗證信、追蹤清單、金幣、會員流程、排行搜尋（`?q=`）與 `/admin/`；`AhrefsBot`、`SemrushBot`、`MJ12bot`、`DotBot`、`PetalBot`、`BLEXBot`、`DataForSeoBot`、`Bytespider` 全站不讓爬（SEO 工具與已知爬很兇的爬蟲，不是讀者的搜尋引擎；`Bytespider` 是否要擋可再決定）。Google、Bing 與 AI 搜尋的爬蟲不擋。
- `sitemap.xml`：兩種語言的首頁、各分頁籤、持股與政策頁、追蹤人物、每種語言最新 500 篇文章（含 `lastModified`）。
- **沒做、要在 Vercel 恢復後到後台設定的**：robots.txt 只是請求，不遵守的爬蟲擋不住。建議在 Vercel Firewall 加一條對 `/news/*` 的每 IP 速率限制（例如每分鐘 120 次，超過就 challenge 或 429），以及對 user-agent 含上述名單者直接 deny。這些設定在 Vercel 後台，不在程式碼裡。

## 6. 恢復後要看的

1. Vercel 部署後，看 Observability → Functions 的呼叫次數與 `x-vercel-cache` 的 HIT 比例，才能確認實際降幅（本文件沒有這個數字）。
2. 確認 `API_INTERNAL_URL`／`NEXT_PUBLIC_API_URL` 在 Vercel 指向 `https://api.aisiwhale.com`，瀏覽器的會員請求才會帶到 `.aisiwhale.com` 的 cookie。
3. 新文章發布後最晚約 2 分鐘出現在首頁列表（首頁 120 秒＋列表 Data Cache 120 秒，最壞約 4 分鐘）；原本是即時。若要即時，之後可讓後端發布時呼叫一支 `revalidateTag("public-api")` 的路由（本次沒做）。
