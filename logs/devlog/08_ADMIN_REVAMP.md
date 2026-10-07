# 後台改版（AD-01 ~ AD-14）

計畫與任務分解在 `logs/admin/01_ADMIN_REVAMP_PLAN.md`，決策是 D-234。本檔記錄實際執行。

## 開發計畫

| 順序 | 任務 | 依賴 | 狀態 |
|---|---|---|---|
| 1 | AD-01 共用元件 | — | ✅ 2026-10-07 |
| 2 | AD-02 外殼：側欄、頂欄、麵包屑、公司切換器 | AD-01 | ✅ 2026-10-07 |
| 3 | AD-03 ⌘K 指令面板與快捷鍵 | AD-02（`nav.ts`） | ✅ 2026-10-07 |
| 4 | AD-04 後端列表規格 | — | ✅ 2026-10-07 |
| 4b | AD-05 DataTable | AD-04 | ✅ 2026-10-07 |
| 5 | AD-06 管理操作稽核 | AD-04 | ✅ 2026-10-07 |
| 5b | AD-07 詳情頁與 Drawer 預覽 | AD-06 | ✅ 2026-10-07 |
| 6 | AD-09 RBAC（排在 P8 開放付款、TR-12 之前） | AD-06 | ✅ 2026-10-07 |
| 7 | AD-08 看板 | AD-05、AD-07 | ✅ 2026-10-07 |
| 8 | AD-10 通知 | AD-09 | ✅ 2026-10-07 |
| 9 | AD-11、AD-12、AD-13 | — | ⏳ |

---

## 2026-10-07：AD-01 共用元件、AD-02 外殼

### 做了什麼

新資料夾 `frontend/web/src/features/admin-ui/`：

| 檔案 | 內容 |
|---|---|
| `nav.ts` | 後台唯一的導覽設定：5 組、11 個頁面。`activeNav()` 以最長前綴找出目前所在的項目（`/admin/trace`、`/admin/tasks` 歸在「事件時間軸」底下）；`crumbsFor()` 產生麵包屑 |
| `AdminShell.tsx` | 側欄：公司切換器、分組導覽、目前頁面以 `aria-current` 標示、審批收件匣旁顯示待審件數。可收合成只剩圖示，狀態存 localStorage `autora.admin.sidebar`。手機寬度改成左側抽屜。頂欄：連線狀態、主題切換、登入者、登出 |
| `PageHeader.tsx` | `AdminPage` 有兩種寬度：列表 `max-w-7xl`、閱讀 `max-w-5xl`。`PageHeader` 包含麵包屑（保留 `?company=`）、標題、說明與右側動作區 |
| `Dialog.tsx` | `ConfirmDialog`（可要求填理由）與 `Drawer`，都用原生 `<dialog>` 的 `showModal()`。只在開啟時才渲染，所以 jsdom 沒有 `showModal` 也測得到 |
| `StatusLozenge.tsx` | 統一的狀態標籤，沿用 `events/describe.ts` 的 `Tone` |
| `Button.tsx`、`states.tsx`、`icons.tsx` | 按鈕樣式（primary／default／subtle／danger），載入中、空狀態與錯誤的顯示，以及線條圖示 |
| `ConnectionBadge.tsx` | 從 `DashboardView` 搬過來。頂欄用 `LiveStatus` 顯示，頁面沒有開即時連線時不顯示 |

現有頁面的調整：

- `TokenGate` 的 `AdminBar` 換成 `<Suspense><AdminShell/></Suspense>`。外殼讀 `?company=`，Suspense 讓不帶動態參數的頁面也能預先產生。
- `CompanyScope` 抽出 `useCompanyChoice()`，頁面和側欄用同一套規則決定顯示哪間公司。
- dashboard、approvals、agents、cycles、timeline、newsroom（題材、文章、來源與兩種詳情頁）、memberships、trace、tasks 都改用 `AdminPage`／`PageHeader`；各頁自己畫的「Dashboard／辦公室」連結、`NewsroomHeader` 分頁列和各頁的 `ConnectionBadge` 都拿掉。
- 辦公室頁的高度改成 `calc(100dvh - var(--admin-bar))`，扣掉頂欄。
- newsroom 的 `Badge` 和 `TONE_BADGE` 刪掉，改用 `StatusLozenge`；VIP 授予的狀態也改用它。
- 三個破壞性動作改成先開確認對話框：解雇代理、撤銷 VIP（要填理由）、下架文章（對話框裡會顯示下架說明）。
- 主題按鈕原本浮在 `app/admin/layout.tsx` 左下角，現在移到頂欄；登入頁沒有外殼，所以自帶一顆。

### 有意延後的部分

- 計畫列在 AD-01 的 Toast 和 Skeleton 這次沒有做。目前沒有任何地方用到，等第一個用得到的任務（AD-05、AD-08）再做，避免留下沒人用的元件。
- trace／tasks 頁還沒有帶公司範圍：側欄連結用的是上次選的公司。這要等後端的 trace 回應帶公司資訊之後再處理。

### 驗證

- `pnpm -F web typecheck`、`pnpm -F web lint`：通過。
- `pnpm -F web test`：74 個檔案、906 項全過。新增的 `admin-ui/admin-ui.test.tsx` 共 11 項，涵蓋：
  - 導覽設定裡的每個 `href` 都有對應的 `page.tsx`；
  - 最長前綴比對與麵包屑；
  - 確認對話框要填了理由才能送出，按 Esc、點背景、按取消都會關閉；
  - 側欄標示目前頁面、連結保留公司、待審件數、切換公司會回到同一區的列表、收合狀態會被記住、手機抽屜。
- 改了測試、沒改行為的地方（舊測試的斷言對象不見了）：
  - `dashboard.test.tsx`：連線狀態改成直接測 `ConnectionBadge`；
  - `newsroom-pages.test.tsx`：next/navigation 的 mock 補上 `usePathname`；原本斷言 `NewsroomHeader` 分頁列的「文章」連結，改成斷言「← 所有題材」連結有保留公司；下架改成要先在對話框按「確定下架」；
  - `admin-auth.test.tsx`：外殼本身的請求（公司列表、待審件數）回空陣列。
- `pnpm -F web build`：通過。
- Playwright e2e：第一次跑有 2 項失敗。
  - `newsroom.spec.ts` 是 Chrome 啟動逾時（`browserType.launch: Timeout 180000ms`），和程式無關；
  - `office.spec.ts` 的「2D 辦公室把整頁變成終端機」是我造成的：測試抓 `page.locator("header").first()`，現在第一個 header 是外殼的頂欄。2D 終端機配色仍然只覆寫辦公室自己的 `main`（D-007），所以外殼的側欄和頂欄維持網站主題。我把測試改成抓 `main[data-terminal]` 裡的 header。
  - 重跑 office、newsroom、realtime 三個 spec：15 項全過。
- 畫面檢查：用 e2e 的測試資料庫與測試管理員（`e2e/stack.ts`），拍了 1440 寬的 dashboard、approvals、articles、stories、agents、memberships、office、timeline，深色主題＋收合側欄＋解雇確認對話框，以及 375 寬的文章頁與選單抽屜。截圖用的暫時 spec 沒有提交。

---

## 2026-10-07：AD-03 指令面板與鍵盤快捷鍵

### 做了什麼

| 檔案 | 內容 |
|---|---|
| `admin-ui/CommandPalette.tsx` | 指令面板，建在 `Dialog.tsx` 匯出的 `Modal`（原生 `<dialog>`）上。輸入框是 combobox，結果是 listbox，`aria-activedescendant` 指向方向鍵選到的項目。可以打字篩選，↑↓ 選擇（循環），Enter 執行，Esc 關閉。注音或倉頡正在選字時按 Enter 不會執行（`isComposing`）。同一個檔案裡還有 `ShortcutHelp`（按 `?` 開啟的快捷鍵說明） |
| `admin-ui/commands.ts` | 面板裡的指令分四組：最近瀏覽、前往（`nav.ts` 每一頁，附上它的 `g` 快捷鍵）、切換公司（目前這間不列）、動作（收合側欄、快捷鍵說明、登出）。`pick()` 的規則：查詢的每個詞都要出現在名稱或提示裡，不分大小寫；名稱以查詢開頭的排在前面 |
| `admin-ui/hotkeys.ts` | `useHotkeys` 掛在 window 上，按鍵說明的資料也在這裡（`SHORTCUTS`）。⌘K／Ctrl K 切換面板，打字中也有效；`/` 開面板；`?` 開說明；`g` 加字母前往頁面（1.2 秒內要按第二個鍵）；`j`／`k` 在 `main [data-row]` 之間移動焦點；Enter 開啟選取那一列的第一個連結。打字中（input、textarea、select、可編輯區）、選字中、或有對話框開著時，這些鍵都不作用。列表那一列只要套上 `ROW` 與 `ROW_FOCUS` 就能參與 |
| `admin-ui/recent.ts` | 最近瀏覽的頁面，最多 8 筆，存 localStorage `autora.admin.recent`。只記詳情頁，由 `PageHeader` 在標題是純文字時記錄 |
| `nav.ts` | 每個項目新增 `go`：d Dashboard、o 辦公室、i 審批、c 週期、t 時間軸、s 題材、a 文章、f 來源、p 代理、v VIP |
| `AdminShell.tsx` | 頂欄加上「搜尋或跳頁… ⌘K」按鈕；掛上快捷鍵、面板與說明 |

會套上 `ROW` 的列表：文章、題材、來源、代理、VIP 授予、審批卡片。

審批卡片被選取時：
- 按 `a` 會先開確認對話框，焦點預設在「取消」，所以連按 Enter 不會誤核准；
- 按 `r` 會把游標移到意見欄，再用 Tab 走到「退回修改」或「駁回」。

剛按完 `g` 時，卡片不接 `a`（`sequencePending()`），所以按 `g a` 是去文章頁，不會開核准確認。

### 有意的取捨

- **不用 cmdk。** cmdk 依賴 Radix 的 dialog，和 D-234 ⑤「對話框用原生 `<dialog>`」衝突。這個面板需要的篩選、方向鍵和 ARIA 自己寫大約 150 行。
- **滑鼠點卡片上的「核准」維持一鍵完成，不加確認**；只有鍵盤的 `a` 會先問。原本的操作習慣不變，鍵盤則多一道保護，避免誤按。
- **計畫說面板第一版只搜「最近瀏覽」**，所以搜尋稿件、題材的實際資料要等 AD-04 的列表 API 有 `q` 參數後再接上。
- **面板裡沒有「切換深淺色」**：`ThemeToggle` 的狀態在元件內部，從外面切換的話它的圖示不會跟著變；頂欄的按鈕仍然在。

### 驗證

- `pnpm -F web typecheck`、`lint`、`build`：通過。
- `pnpm -F web test`：76 個檔案、928 項全過。新增的 `admin-ui/keyboard.test.tsx` 共 13 項，涵蓋：
  - 面板的分組與篩選；
  - 方向鍵循環與 Enter 執行；
  - 選字中按 Enter 不執行；
  - ⌘K、Ctrl K、`/`、`?`；
  - `g i` 會帶公司前往，超過時間則失效；
  - 輸入框裡打字不觸發，⌘K 例外；
  - `j`／`k` 不會超出第一列和最後一列，Enter 開啟該列；
  - 詳情頁會被記住，列表頁不會；
  - 審批卡的 `a` 要確認後才核准，在意見欄裡打 `a` 只是文字。
- 真實瀏覽器（暫時的 Playwright spec，用 e2e 的測試管理員，沒有提交）：讓一則題材跑到待審批，然後只用鍵盤完成整個流程：
  1. 在 Dashboard 按 ⌘K，輸入「文章」，Enter，到了文章頁；
  2. 按 `g i` 到審批收件匣；
  3. 按 `j`，卡片取得焦點；
  4. 按 `a`，跳出確認；
  5. 按 Tab、Enter 送出，API 的待審件數從 1 變成 0；
  6. 按 `?` 開出說明。

  這就是計畫的驗收條件，已通過。
- 完整的 Playwright e2e：17 項通過、1 項略過（`office-soak` 預設就不跑），沒有失敗。

---

## 2026-10-07：AD-04 後端列表規格

### 做了什麼

新模組 `backend/api/autora_api/pagination.py`，讓所有後台列表用同一種問法：`?cursor=&limit=&q=&sort=`，回傳 `{items, next_cursor, total}`。

- **limit**：1～100，預設 50。
- **sort**：每個端點自己的 `Literal` 值，前面加 `-` 是遞減，FastAPI 會先檢查（不認得的值回 422）。以列的 id 作為第二排序鍵、方向相同，所以順序完整而且穩定。
- **cursor**：keyset 分頁，內容是上一頁最後一列的排序值和 id，用 base64url 編碼。前面新增資料，後面的頁不會跟著位移；翻到很深的頁也一樣快。cursor 裡記著它的排序方式，換了排序再拿來用會回 400；cursor 壞掉也回 400，都是 problem+json。
- **q**：每個詞都要出現在該端點的搜尋欄位之一，`ILIKE` 不分大小寫；`%`、`_`、`\` 會先跳脫，所以照字面比對、不是萬用字元。
- **total**：套用篩選後的總筆數，和 cursor 無關，每一頁都有。
- 錯誤維持 RFC 7807。

改過的端點：

| 端點 | 排序 | `q` 搜尋 |
|---|---|---|
| `GET /api/approvals` | `created_at`（預設，最久的在上）、`-created_at` | 摘要、kind、action |
| `GET /api/companies/{id}/stories` | `-last_item_at`（預設）、`last_item_at`、`-score`、`-first_seen_at`、`title` | 標題 |
| `GET /api/companies/{id}/articles` | `-updated_at`（預設）、`updated_at`、`-created_at`、`title` | 標題、slug |
| `GET /api/companies/{id}/sources` | `created_at`（預設）、`-created_at`、`name` | 名稱、網址 |
| `GET /api/admin/memberships/comps` | `-created_at`（預設）、`created_at`、`-expires_at`、`expires_at` | 讀者 email、理由、撤銷理由 |

- `newsroom/admin.py` 的 `list_stories`、`list_articles`、`list_sources` 拆成兩部分：查詢（`stories_query`、`articles_query`、`sources_query`）和組成畫面資料（`story_summaries`、`article_summaries`），分頁交給 API 層，domain 模組不需要 import API。原本的 `MAX_LIST` 拿掉。
- VIP 授予的資料來自 `memberships.comp_grants`，那是會員與鯨幣工作階段負責的模組，我不改它，所以用 `page_list` 在記憶體裡分頁，規則和 SQL 版相同。授予只有內部測試用的幾筆，記憶體分頁足夠。

前端：

- `queries.ts` 的五個列表改成 `infiniteQueryOptions`。新增 `Page<T>`、`itemsOf`、`totalOf`，以及 `pendingCountQuery`：只要一列，回傳 `total`，給側欄、Dashboard、辦公室的待審件數用，不必再把整份收件匣抓下來數。
- `admin-ui/usePaged.tsx` 搭配 `LoadMore`（顯示「顯示 X / 共 Y 筆」和「載入更多」），用在審批、題材、文章、來源、VIP 授予五頁。
- 指令面板接上真實資料：輸入停頓 250 毫秒後，用 `q` 搜尋目前公司的文章與題材（各取 5 筆），結果列在「搜尋結果」組，選了就打開那篇。這就是 AD-03 說的「AD-04 完成後改打 API」。`no-fake-data.test.ts` 的計時器白名單加上 `AdminShell.tsx`，理由和股票搜尋的等字（D-061）相同：計時器只延後送出請求，顯示的仍然是 API 的結果。
- 團隊群組只拿第一頁（50 筆）的待審批與文章標題來對應訊息。原本待審批一次全拿；超過 50 筆待審的情況目前不會發生。
- `openapi.json`、`schema.gen.ts` 是等持股工作階段先提交 HD-11（1297574）、pull 之後才重新產生的，避免把對方未提交的部分一起提交。

### 有意延後的部分

- 計畫最後列的 `events`（事件時間軸）沒有改。即時串流會用 `limit` 補資料，改它的回傳格式會牽動 realtime，等 AD-05 處理時間軸表格時再一起做。
- 計畫說 `total` 只在資料量可接受的表上提供；這五張後台表都很小，所以都提供。

### 出過的錯

- **我在共用的 `autora_test` 上跑了好幾次 pytest。** conftest 每次都會 `DROP SCHEMA public CASCADE`，因此打斷了持股工作階段的完整測試（對方來問才發現）。之後改成設 `DATABASE_URL=…/autora_ad`，用自己的 `autora_ad_test`。
- `test_pagination.py` 的搜尋測試，原本四列的 action 都是 `publish_article`，而 action 也在搜尋範圍內，所以「PUBLISH」四列都命中。是測試資料寫錯，改成另一個 action。

### 驗證

- 新增 `backend/tests/api/test_pagination.py` 共 10 項：
  - 7 列資料用每頁 3 列翻完：順序正確、沒有缺漏、共 3 頁；剛好一頁的量不會多出一個空頁的 cursor；
  - 10 列 `created_at` 完全相同，正序和倒序翻頁都不會漏列或重複；
  - `q`：不分大小寫、多個詞、中文、`%` 和 `_` 照字面比對、action 也會被搜到；
  - 壞掉的 cursor、換了排序的 cursor 都回 400 problem+json；`limit` 0 或 101、未知的排序值回 422；
  - 三個新聞室列表接受相同的參數；
  - 1,000 筆待審時，第一頁和翻到深處的頁平均每頁不到 200 毫秒（計畫的驗收條件；量三次取最快的一次。第一版只量一次，在 32 分鐘的完整測試裡、機器同時跑其他工作階段的負載時超時一次，單獨跑三次都通過）；
  - cursor 編碼後能解回原值；`page_list` 規則與 SQL 版一致。
- 既有的 approvals、newsroom、membership_p2 API 測試改讀 `items`，24 項通過。
- 前端：typecheck、lint、build 通過；vitest 77 個檔案、932 項全過。新增 `admin-ui/paged.test.tsx`，測「載入更多」和面板的搜尋結果。
- `gen_openapi.py --check`、`gen-api:check`：產生的檔案是最新的。
- 完整後端 pytest（在自己的 `autora_ad_test` 上）：2,403 項中只有 1 項失敗，就是上面那個計時測試，已改成量三次取最快；`test_workflow.py` 有一項在先前另一次完整測試裡失敗過，單獨重跑通過，那次是機器負載高（load average 172）。
- Playwright e2e：17 項通過、1 項略過。`newsroom.spec.ts` 輪詢待審數的地方改讀 `total`。

---

## 2026-10-07：AD-05 DataTable 與網址中的列表狀態

### 做了什麼

| 檔案 | 內容 |
|---|---|
| `admin-ui/DataTable.tsx` | `DataTable`：欄位用資料定義（標題、儲存格、排序鍵、對齊）；表頭點了就請伺服器排序，可兩個方向時再點會反向，`aria-sort` 標示目前方向；每一列都能用 `j`／`k` 選取；有勾選框，勾了之後出現「已選 N 筆」的批次動作列；列高分「寬鬆／緊湊」兩種，所有表格共用，存 localStorage `autora.admin.density`。同一個檔案裡還有：`ListToolbar`（搜尋框按 Enter 才送出、篩選下拉、目前篩選的小標籤可逐一取消或全部清除、我的篩選器、列高切換）、`Pager`（「第 51–100 筆，共 N 筆」，以及第一頁、上一頁、下一頁）、`sortControl` |
| `admin-ui/useListState.ts` | 表格狀態全部放在網址：`q`、`sort`、各篩選、`cursor`、`prev`、`from`。`prev` 是之前每一頁的 cursor 用 `.` 串起來，第一頁記為 `0`，所以「上一頁」不需要瀏覽器的歷史紀錄；`from` 只用來顯示第幾筆。改搜尋、排序或篩選時用 `replace` 並回到第一頁；換頁用 `push`，所以瀏覽器的上一頁也能用。網址上的其他參數（`?company=`）一律保留 |
| 我的篩選器 | 存目前的 `q`、`sort` 和篩選（不存頁數和公司），取名後放在 localStorage `autora.admin.views.<表格>`，可套用、可刪除（D-234 ③） |

改成 DataTable 的頁面：

- **文章**：可依標題、更新時間排序；搜尋標題與網址代稱。
- **題材**：狀態篩選從原本的分頁按鈕移到工具列；可依標題、分數、首次出現排序。
- **來源**：可依名稱排序。
- **VIP 授予**：「只看有效中」改成篩選；可依期間、建立時間排序；新增批次撤銷：勾選後填一個理由，逐筆撤銷仍有效的授予，已撤銷或到期的會自動略過；失敗的會列在對話框裡。
- 文章、題材、來源三份列表的查詢改成「一頁」（`articlesPageQuery`、`storiesQuery`、`sourcesQuery`、`compsQuery`）。團隊群組仍然用無限捲動版的 `articlesQuery`。

**審批收件匣維持卡片，不改成表格**：每張卡片裡有稿件預覽、意見欄和決定按鈕，塞進表格的一列會比現在難用。改成表格要等 AD-07 的「列表＋右側預覽」再一起處理。這次只把它的分頁標籤、搜尋、排序（等最久的在上／最新的在上）放進網址，並加上我的篩選器；分頁仍然是「載入更多」。

### 和計畫不同的地方

- **沒有用 `@tanstack/react-table`。** 排序和分頁都在伺服器端，那個套件主要的用處（前端排序、篩選、分頁）用不到；而且安裝套件會改到 `pnpm-lock.yaml`，這是其他工作階段也在用的共用檔案。自己寫的表格加上狀態約 450 行。
- **題材少了「最近更新」欄**：`StorySummary` 沒有 `last_item_at`，加上它要再重新產生共用的 openapi 檔，而持股工作階段的 HD-12 正在等那兩個檔。預設排序仍然是最近活動優先，只是表頭不能點它。
- **計畫說 AD-05 要一起處理事件時間軸的分頁**，但時間軸是即時資料流，不是表格，所以留到 AD-07 的活動時間軸。

### 驗證

- 新增 `admin-ui/table.test.tsx` 共 6 項：
  - 搜尋按 Enter 才寫進網址；篩選與排序寫進網址並回到第一頁、保留公司；重新整理後畫面相同，小標籤可以逐一取消；
  - 表頭的兩個方向與 `aria-sort`；
  - 下一頁、上一頁、第一頁時網址上的 cursor 堆疊正確；
  - 我的篩選器可儲存、套用、刪除，而且不存頁數和公司；
  - 勾選與批次動作；列高切換後會記住；
  - 空的表格與錯誤狀態。
- `comps.test.tsx` 新增批次撤銷：只送出仍有效的兩筆，用同一個理由。
- vitest 79 個檔案、946 項中只有 1 項失敗，是 `timeline` 的計時測試在機器負載高時超時，單獨重跑 8 項全過（時間軸我沒有動）。lint 通過；typecheck 只有持股工作階段未提交的 `features/site/*`（HD-12）報錯，不是我的檔案。

---

## 2026-10-07：AD-06 管理操作稽核

AD-05 沒有自己推送，是由持股工作階段連同 HD-12 一起推上 main（ef2b84c，合併提交 e2aef53），內容沒有改動。推送前我在乾淨的 worktree 上，把 ef2b84c 疊在當時的 origin/main 上驗證過：typecheck、lint、vitest 941 項、build、e2e 17 項全部通過。

### 做了什麼

- **資料表 `admin_actions`（遷移 0076）**，欄位：
  - `actor`、`method`；
  - `route`：路由樣板，例如 `/api/articles/{article_id}/unpublish`；
  - `action`：endpoint 名稱；
  - `target_type`、`target_id`：路徑裡第一個 id，例如 `{article_id}` 就是 `article`；
  - `company_id`、`status`；
  - `input`：送出的 query 與 JSON body；
  - `ip`。

  只能新增：沿用 0002 的 `autora_forbid_mutation()` trigger，UPDATE 和 DELETE 都會被拒絕。
- **寫入方式（`autora_api/audit.py`）**：`require_operator` 放行一個寫入請求時，把操作者記在 `request.state` 上；`AuditMiddleware` 是純 ASGI middleware，在 app 讀取請求內容時順便留一份，等回應開始時寫入一列。
  - 被拒絕的嘗試（409、422）也會記錄；app 沒送出回應就失敗時記成 500。
  - 讀取（GET、HEAD、OPTIONS）不記錄；沒有登入的請求也不記錄。
  - 這一列在回應送出之前寫入，所以呼叫者的下一個請求就看得到。寫入失敗時只記 log，回應照常送出：那時修改已經 commit，再回錯誤只會誤導人。
  - 使用 app 自己的 `get_session`（遵守 dependency override），所以測試和請求共用同一個交易。
- **公司的判斷順序**：路徑的 `company_id` → query 或 body 的 `company_id` → `?company=` 的 slug → 用目標表查出所屬公司（文章、題材、審批、代理、專案、來源、工作流程）。
- **遮蔽與截斷**：鍵名含 pass、token、secret、authorization、cookie、api_key 的值改成 `***`；超過 2,000 字的文字截斷並註明原長度；body 超過 64 KB 不保存，只記大小；整份 input 超過 16 KB 時只保存鍵名。
- **`GET /api/admin/audit`**：沿用 AD-04 的分頁規格。篩選：`company_id`、`actor`、`target_type`、`target_id`、`action`、`failed`、`since`、`until`；`q` 搜尋路由、動作、對象 id 和操作者。管理員以 email 顯示（`actor_label`），但資料庫只存 reader id（D-024）。
- **前端 `/admin/audit`「操作紀錄」**：側欄新增「系統」群組，快捷鍵 `g l`。用 DataTable 顯示時間、誰、動作（27 個路由各有中文名稱）、對象（文章和題材可以點開）、結果（完成、被拒 4xx、錯誤 5xx）、送出的內容（摺疊）。篩選：範圍（這間公司／所有公司）、結果、對象種類；也支援我的篩選器。

### 和計畫不同的地方

- **計畫裡的 `before`、`after`（修改前後的欄位）沒有做**，改成記錄送出的內容和結果。要做前後差異，得在 27 個路由裡逐一寫「修改前讀一次」，而且每加一個路由就多一處要記得維護，和「新路由自動被記錄」的設計衝突。狀態的變化本來就記在 `state_transitions` 和事件裡，AD-07 的活動時間軸會把兩者合在一起顯示。
- **計畫說要修好 newsroom 那 5 個沒有記下操作者的動作**：middleware 會自動記錄所有寫入路由，所以它們現在都有紀錄（測試檢查了閱讀權限、分類、新增來源），不需要逐一改 handler。
- **管理員登入和登出不記錄**：它們在門外，不經過 `require_operator`。是否要另外記錄登入，留到 AD-09 RBAC 再一起決定。

### 防止漏掉的測試

`test_every_write_route_goes_through_the_door_or_is_named_here` 會列出 app 裡所有寫入路由。FastAPI 0.142 的 `include_router` 不再把路由攤平，而是包成 `_IncludedRouter`，所以要從 `original_router` 遞迴取出。每個寫入路由都必須經過 `require_operator`（也就是會被記錄），否則就要列在 `PUBLIC_WRITES` 白名單裡。白名單目前 16 個，都是讀者自己的帳號與自選股、公開網站、PAYUNi 通知，以及後台登入本身。之後新增的寫入路由如果沒有走這個門，又沒有列進白名單，測試就會失敗。

### 遷移編號

0074 已經被持股 HD-12 的 `tw_flows` 用掉。臨時上班修正（D-237）的工作階段原本也打算用 0074，我在它推送前提醒了撞號，協調後由對方用 0075，我改用 0076。

### 驗證

- `alembic upgrade head`、`alembic check`（模型與遷移沒有差異）、`downgrade -1` 後再 `upgrade` 都通過（在自己的資料庫 `autora_ad` 上）。
- `tests/api/test_admin_audit.py` 共 7 項：
  - 每個寫入路由都經過門或在白名單；
  - 審批決定的紀錄：操作者、路由樣板、對象、公司、送出內容、狀態 200，重複決定的 409 也有紀錄；
  - 讀取和未登入的請求不記錄；
  - 閱讀權限、分類、新增來源三個動作都有紀錄，對象和公司正確；
  - UPDATE 和 DELETE 會被 trigger 擋下；
  - 列表的排序、`failed`、`q`、`target_id` 篩選，以及未登入回 401；
  - 遮蔽、截斷、非 JSON 與過大 body 的處理。
- 前端 `features/audit/audit.test.tsx`：列表的顯示；`ACTION_LABEL` 的每個路由都存在於 openapi.json。
- 和 D-237（33071df，同樣改了 `deps.py` 與 `app.py`）合併：兩處衝突都是在同一個位置各自新增一行，兩邊都保留。`require_operator` 裡的順序是 `OFFICE_CALL.mark()` → `await OFFICE_CALL.keep(...)` → `audit.mark(...)`。合併後 `alembic heads` 只有 0076。
- 在乾淨的 worktree 驗證合併後的提交（共用目錄裡有會員工作階段未提交的修改）：
  - `gen_openapi --check`、`gen-api:check`、typecheck、lint 通過；
  - vitest 80 個檔案、950 項全過（用 `--maxWorkers=3`；機器負載約 47 時，預設的 worker 數會讓不同的測試輪流超時）；
  - build 通過；Playwright e2e 17 項通過、1 項略過；
  - 完整後端 pytest 2,425 項全過（在自己的 `autora_ad_test` 上）。
- 畫面：以 e2e 測試資料拍了操作紀錄頁，一筆完成、一筆被拒 422，送出的內容可以展開。看了截圖後發現「範圍」篩選沒選時顯示「全部」，實際上只有這間公司，所以 `FilterDef` 加了 `anyLabel`，這裡改成「這間公司」。

---

## 2026-10-07：AD-07 詳情頁雙欄、活動時間軸、列表旁預覽

### 做了什麼

- **`GET /api/admin/activity?target_type=article|story|approval&target_id=`**（`routers/admin_activity.py`）：一件東西的歷史，新的在上，最多 200 筆。合併的來源有：
  - 它的狀態變化（`state_transitions`）；
  - 在後台對它做的事（`admin_actions`，AD-06）；
  - 文章另外加上問到它的審批（`approvals.payload.article_id`）：何時提出，以及審批自己的狀態變化（誰決定、理由）。

  對審批的「決定」這個後台動作不另外列一次，因為審批的狀態變化已經記下誰決定、理由是什麼。每一筆都用文字標出是誰：管理員顯示 email、代理顯示名字、操作者權杖、系統元件。
- **`features/audit/ActivityTimeline.tsx`「活動」**：分「全部／狀態變化／人的操作」三個分頁。用文字描述每一筆：狀態依各自的對照表（草稿 → 待核准、待審批 → 已核准）；後台動作用 AD-06 的中文名稱，被拒絕的會標示；審批的項目前面加「審批：」。動作名稱的對照表搬到 `features/audit/labels.ts`，操作紀錄頁和活動共用。
- **`admin-ui/DetailLayout.tsx`**：`DetailLayout` 是詳情頁的兩欄（`lg` 以上右欄 22rem，窄螢幕改成上下排）；`Properties` 是屬性框。
- **文章詳情**：
  - 左欄：版本、語言、內文、引用的主張、事實查核、發布紀錄、讀者、工作流程事件；
  - 右欄：屬性（狀態、題材、閱讀權限、修訂、發布時間、公開頁）、閱讀權限、分類、網站上架、首圖、活動。
  - 狀態只出現在右欄（Jira 的做法），頁首只留標題。
- **題材詳情**：右欄是屬性（狀態、分數、來源、首次出現、文章）和活動；「開始製作」仍在頁首右側。
- **審批**：沒有獨立的詳情頁，每張卡片多了一個摺疊的「活動」，展開時才去讀資料。審批的決定也會出現在它所屬文章的活動裡。
- **列表旁預覽**（`admin-ui/usePeek.ts`）：
  - 在文章表和題材表上直接點標題，會從右側開出寬版 Drawer：開啟完整頁面、摘要、屬性、活動。
  - 網址加上 `?peek=<id>`，所以瀏覽器的上一頁可以關掉它，重新整理或分享連結也看得到。
  - 用 ⌘、Ctrl、Shift 點擊仍照常開新分頁，`href` 是完整頁面的網址。
  - 在這裡打開的預覽，關閉時是「回上一頁」；從連結帶進來的預覽，關閉時只把 `peek` 從網址拿掉，不會離開這一頁。
  - 選到一列時按 Enter 會點那一列的標題，所以 `j`／`k`＋Enter 也會開預覽。
- 文章與題材詳情裡原本的「時間軸」區塊改名「工作流程事件」，避免和「活動」混淆。

### 和計畫不同的地方

- **審批沒有做雙欄詳情頁**：卡片本身已經有預覽和決定按鈕，所以只加了摺疊的「活動」。
- **事件時間軸（`/admin/timeline`）的分頁，AD-04、AD-05 都說延到這裡，這次仍然沒做。** 它是即時資料流，「活動」是另一種東西（一件東西的歷史），兩者不能互相取代。要讓即時事件也能分頁或搜尋，需要改 `events` API 和 realtime 的補資料流程，風險不同，我把它列為之後的獨立任務，不再算在 AD-07 裡。

### 驗證

- 後端 `tests/api/test_admin_activity.py` 共 2 項：
  - 文章的活動合併了自己的狀態變化、人的修改（閱讀權限）、審批的提出（標成「系統（service:newsroom.approve）」）和決定（操作者權杖、理由），並依時間由新到舊；
  - 題材與審批也各有自己的活動；不認得的種類回 422，未登入回 401。
- 前端 `features/audit/activity.test.tsx` 共 5 項：每一種活動的文字描述、三個分頁、預覽的開啟與關閉方式。
- 改了測試、沒改行為的地方：`newsroom-pages.test.tsx` 的公開頁和題材連結搬到右欄的屬性框裡（連結文字從「公開頁（en）」變成屬性框裡的「en」、從「題材：…」變成題材名稱）。
- e2e `newsroom.spec.ts` 第一步在題材表點標題，原本會直接換頁，現在會先開預覽，所以改成「開預覽 → 點『開啟完整頁面』」，這也順便讓預覽有了 e2e 覆蓋。「製作中」現在同時出現在屬性框和活動裡，所以斷言限定在「屬性」區塊。這兩處是我改了行為造成的，不是測試本身有錯。
- 看截圖後改了兩處：
  - 首圖面板原本放在 22rem 的右欄，搜尋文字和按鈕被截斷，搬回左欄內文上方（`CoverPanel` 是另一個工作階段負責的檔案，我不動它）；
  - 活動裡的代理名稱原本顯示原始的 `Ami Mizuno｜水野亞美`，改用 `personName()`，和後台其他地方一致。

---

## 2026-10-07：AD-08 生產流程看板

這次在自己的 worktree（`.claude/worktrees/ad08`，分支 `admin/ad08`）做。原因是共用目錄裡，會員工作階段有未提交的 openapi.json、schema.gen.ts、queries.ts、app.py，正好都是我要改的檔案。

### 做了什麼

- **一張移動表 `features/board/moves.json`**：列出人可以做的移動，前端和後端都讀它。
  - 文章：待核准 → 已核准（核准）、→ 草稿（退回修改）、→ 已駁回（駁回）；已發布 → 已下架（下架）；已下架 → 已發布（重新上架）；已發布或已下架 → 草稿（修改文章）。
  - 題材：新發現或已選定 → 製作中（開始製作）。
  - 其他的移動（草稿送審、核准後發布、題材被放棄…）是工作流程的事，不讓人拖。
- **`features/board/Board.tsx`**：用已安裝的 @dnd-kit/core，每個狀態一欄。
  - 拿起一張卡時，可以放的欄位外框變成虛線並亮起；不能放的欄位變淡，而且不接受放下。
  - 每張卡也有「移動到…」選單，選項和拖曳完全相同，給鍵盤和螢幕閱讀器用（dnd-kit 本身也支援鍵盤拖曳）。
  - 卡片能用 `j`／`k` 選取；點標題會開 AD-07 的預覽。
- **`features/board/useBoardMoves.tsx`**：
  1. 每一次移動都先開確認對話框（拖錯很容易）。下架、退回修改、駁回、修改文章要填理由；核准、重新上架、開始製作不需要。
  2. 確認後，卡片立刻出現在目標欄並標示「處理中…」，同時送出請求。
  3. 成功：顯示 toast，重新讀取列表。卡片會留在目標欄，直到列表顯示它確實離開原欄為止，因為核准之後是由工作流程稍後把它推進下一步。
  4. 被拒：卡片放回原欄，用 toast 說明原因。
  - 欄位的總數也會跟著正在移動中的卡片調整。
- **`features/board/Boards.tsx`**：
  - `ArticleBoard`：六欄，每欄各自讀一頁（50 筆、最近更新的在前）。待核准的稿件透過它的審批來決定（`payload.article_id` 對應到審批）。
  - `StoryBoard`：五欄。
- **文章頁、題材頁的頁首加「表格／看板」切換**（`admin-ui/ViewSwitch.tsx`），選擇記在網址的 `?view=board`；看板模式不顯示搜尋列與分頁。
- **後端**：文章列表加上 `state` 篩選，給看板的每一欄用。
- **`admin-ui/Toast.tsx`**：AD-01 延後的 Toast 這次做了，第一個用到它的就是看板。
  - 右下角顯示、會被螢幕閱讀器讀出，6 秒後消失。
  - 計時器只負責把訊息拿掉，所以列進 `no-fake-data.test.ts` 的白名單。

### 看板找到的後端錯誤

`test_board_moves.py` 把一份從未發布的草稿送去「下架」與「重新上架」（例如舊頁面或腳本，看板本身不會讓人這樣拖），結果得到 **500**，而不是 409。原因是狀態機的 guard 拒絕時丟出 `GuardRejected`，但 `post_unpublish`、`post_republish` 只接 `IllegalTransition`。兩者共同的父類是 `FSMError`，改成接它之後就回 409。

### 驗證

- 後端 `tests/api/test_board_moves.py` 共 12 項：
  - `moves.json` 的每一個文章移動都是 `ARTICLE_FSM.can` 允許的；每一個題材移動都有 `STORY_FSM` 的路徑可以走（開始製作會先選定再開始）；表裡的狀態名稱兩邊都認得；
  - 草稿被拖去下架、重新上架、修改文章，都回 409。
- 前端 `features/board/board.test.tsx` 共 35 項：
  - 文章六個狀態兩兩組合（30 組）用表格驅動檢查：只有那 7 組可以移動；
  - 題材只能開始製作；
  - 卡片只提供自己能做的移動，不能移的卡片沒有拖曳把手和選單；
  - 移動的過程：先確認、要理由、處理中、成功的 toast、被拒時放回並說明原因、取消時什麼都不做。
- vitest 82 個檔案、988 項全過；typecheck、lint 通過。
- 真實瀏覽器（暫時的 Playwright spec，沒有提交）：
  1. 讓一則題材跑到待審批，打開文章看板；
  2. 用滑鼠把待核准的卡片拖到「已核准」。拖動時，「草稿」「已核准」兩欄的 `data-drop` 是 `open`，「已發布」是 `closed`；
  3. 放下後跳出「待核准 → 已核准」的確認，按核准，API 的待審數從 1 變成 0，並出現「已核准：…」的 toast。

  截圖時發現「待核准」欄顯示「0 / 1」（總數還算著正在移動的那張卡），已改成總數也跟著調整，重拍確認變成 0。
- 推送前合併了 origin/main（D-240 的會議室、會員工作階段 P3-C 的 d050849），沒有衝突。合併後重新產生 openapi.json、schema.gen.ts，結果完全相同。合併後的驗證：
  - ruff、lint-imports 通過；
  - vitest 85 個檔案 1,011 項中只有 1 項失敗，是 `office3d/agents/avatar.test.tsx` 在負載 20 時超時，單獨重跑 12 項全過；
  - build 通過；Playwright e2e 17 項通過；
  - 完整後端 pytest 2,498 項中只有 1 項失敗，是 `tests/e2e/test_recovery.py::test_killed_worker_is_recovered_without_duplicates`（會殺掉 worker 行程的測試），單獨重跑兩次都通過，那個檔案我也沒有動。

---

## 2026-10-07：AD-09 角色與權限

在 `.claude/worktrees/ad09`（分支 `admin/ad09`，從 AD-08 分出）做。

### 做了什麼

- **權限表 `autora_api/permissions.py`**：權限鍵的格式是 `模組:動作`，共 12 個。每一個「經過後台的寫入路由」都用「方法＋路由樣板」對應到一個鍵；讀取路由只有列出來的才需要鍵（`GET /api/admin/audit` 需要 `audit:view`、讀者鯨幣明細 `GET /api/admin/coins/wallet` 需要 `coins:view`、`/api/admin/access` 需要 `access:manage`），其餘所有角色都能讀。
- **四種角色**（D-234 ①）：
  - owner：全部權限；
  - editor：`newsroom:edit`、`approvals:decide`、`projects:manage`、`workflows:run`；
  - finance：`finance:edit`、`memberships:grant`、`coins:adjust`、`coins:view`；
  - viewer：沒有任何權限，只能讀。
  - 鯨幣調整是權限鍵，不是另一種角色（D-234 ①）。
- **在哪裡檢查**：`require_operator` 找出目前請求對應的路由（`request.scope["route"]`），查權限表；角色沒有那個鍵就回 403 problem+json，訊息裡會寫出缺的是哪個鍵。被拒的嘗試也會照 AD-06 記進操作紀錄。**不用改任何 router**：檢查集中在門口，和 AD-06 的稽核是同一種做法，所以其他工作階段負責的 router（例如鯨幣）不必動。
- **誰是什麼角色**：
  - `ADMIN_EMAILS` 上、而且 email 已驗證的人一律是 owner；
  - 操作者權杖也是 owner：只給機器（CI、腳本、worker）用，操作紀錄記為 `operator`（D-234 ②）；
  - 其他人由 owner 加進新的 `admin_roles` 資料表（遷移 0079），四種角色擇一，email 也必須已驗證。
- **`/api/admin/auth/me` 和登入的回應**多了 `role` 與 `permissions`。
- **`/api/admin/access`**（`access:manage`）：列出 owner 名單、其他管理員和各角色的權限；可以加入（對方須已在網站註冊）、改角色、移除。不能改或移除自己（避免 owner 不小心把自己鎖在外面）。ADMIN_EMAILS 上的人不能在這裡被加入或修改。
- **前端**：
  - `TokenGate` 把 `/me` 回來的權限放進 `PermissionsProvider`，元件用 `useCan()` 判斷要不要顯示。不在登入頁面裡時（例如單獨渲染元件的測試）一律顯示，所以既有測試不受影響。真正的檢查仍然在 API。
  - 側欄、⌘K 指令面板、`g` 快捷鍵都不顯示角色打不開的頁面（`nav.ts` 每個項目可設定 `need`），整組都沒有可顯示的項目時連組名一起隱藏。
  - 看板只提供角色能做的移動（`MOVE_NEEDS`）。
  - 審批卡片：沒有 `approvals:decide` 的人看得到內容，但看不到決定按鈕，改顯示「只能檢視」。
  - 其他依權限隱藏的：授予與撤銷 VIP、代理的暫停／恢復／解雇與雇用表單、文章的上下架／修改／閱讀權限／分類、題材的開始製作、新增來源。
  - 頂欄在 email 後面顯示角色。
- **新頁面「角色與權限」**（`/admin/settings/access`，系統群組，快捷鍵 `g r`，只有 owner 看得到）：
  - 擁有者名單（環境變數設定，在這裡不能修改）；
  - 其他管理員表格：可以改角色、移除（先確認）、加入；
  - 角色權限表：權限鍵從 API 讀取，並附上中文說明。

### 和計畫不同的地方

- **計畫說 ADMIN_EMAILS 降級成「第一次登入時自動給 owner」的初始名單，我改成「ADMIN_EMAILS 永遠是 owner」**，資料表只記其他人。這樣不會在登入時暗中寫入資料，owner 名單也一直由部署設定決定。代價是要移除一位環境變數裡的 owner，得改設定，不能在後台操作。
- **首圖面板（`CoverPanel`）沒有依權限隱藏**：那是另一個工作階段負責的檔案。沒有權限的人按了會收到 403 的錯誤訊息。
- **鯨幣頁**（會員工作階段負責）：查詢讀者明細需要 `coins:view`，沒有權限時頁面會顯示 API 的錯誤。對方希望顯示「沒有權限」，我已請它在自己的頁面處理。

### 驗證

- 後端 `tests/api/test_admin_permissions.py` 共 11 項：
  - 權限表雙向完整：每個後台寫入路由都有鍵，每個鍵都對應到真的路由；
  - 四種角色的權限；
  - **四種角色各自把權限表裡的每一個路由都打一次**：只有缺少權限鍵的才回 403，其餘不是 403，回應是 problem+json 並寫出缺的鍵；所有角色都能讀審批；
  - 權杖與 ADMIN_EMAILS 都是 owner，`/me` 的權限清單正確；
  - owner 加入、改角色、移除一個人的完整流程（加入前登入回 403、加入後可以登入、editor 打不開權限頁、移除後 cookie 失效）；
  - 不能改自己的角色；email 未驗證時有角色也進不來；被拒的嘗試記進操作紀錄（狀態 403、操作者是那位 viewer）。
- 既有的 `test_admin_auth.py`、`test_google_api.py` 原本整筆比對 `/me` 的回應（`{"via", "email"}`），現在回應多了角色，改成比對 via、email、role。這是我改了回應造成的，不是測試本身有錯。
- 遷移 0079（原本是 0078，持股工作階段的正式環境修正 0078_prices_paced 先推，照約定我改號）：在自己的資料庫上 upgrade、`alembic check`（沒有差異）、downgrade 後再 upgrade 都通過。
- 前端 `features/access/access.test.tsx` 共 6 項：側欄與指令面板依權限過濾；`useCan` 的預設與限制；看板移動對應的權限鍵；viewer 看到審批卡片但沒有決定按鈕；權限頁的顯示（不能改自己）、改角色、移除前確認、加入。vitest 86 個檔案、1,018 項全過；typecheck、lint 通過。
- 真實瀏覽器：用 e2e 的管理員打開權限頁並截圖，頂欄顯示「擁有者」，權限表正確。
- 推送前的完整驗證（在 0078 改號之前）：後端 pytest 2,509 項、Playwright e2e 17 項全過。之後合併了 origin/main：持股工作階段的 0078_prices_paced（D-244），以及 D-245（後台 2D 辦公室配色，同時把側欄的收合鈕移到標題列）。`AdminShell.tsx` 的衝突只在 `SidebarContent` 的開頭，保留了 D-245 的 `onToggle` 和我的 `useCan()`。合併並改號後，重建自己的資料庫跑 0001→0079、`alembic check`、typecheck、lint、vitest 1,018 項、API 與價格測試 325 項、e2e 17 項，全部通過。

---

## 2026-10-07：AD-10 通知

在 `.claude/worktrees/ad10`（分支 `admin/ad10`）做。

### 做了什麼

- **頂欄的鈴鐺**（`admin-ui/NotificationBell.tsx`）：
  - 顯示這間公司等待審批的件數。資料來源是 `pendingCountQuery`，會隨收件匣原本的 `APPROVAL_*` 即時事件一起更新，不另外輪詢。
  - 點開後列出最久的 8 件，各自顯示已等多久；2 小時內到期或已到期的標「快到期」或「已到期」。下方有「前往審批收件匣」，以及自己的「每日 email 摘要」開關（用操作者權杖時沒有這個開關）。
  - 按 Esc 或點外面就會關閉。
- **每日 email 摘要**（`autora/accounts/admin_digest.py`）：
  - 由 `admin.approvals_digest` 排程執行，台北時間 15:05，也就是 worker 平日上班的時間；週末則在上班時補跑。
  - 收件人：會決定審批的角色（owner：ADMIN_EMAILS 與被設為 owner 的人；editor），email 必須已驗證，而且沒有關掉摘要。
  - 內容：每間公司的待審件數、最久的在前（最多列 10 件，其餘只計數）、已等多久、幾小時後到期（快到期的會標註）、收件匣連結，最後一行說明怎麼關掉。
  - 沒有待審時不寄；某一封寄失敗不會擋住其他人；等待時間以實際寄出的時間計算，不用排定的時間。
  - 放在 accounts 層，因為要讀管理員的 email（D-025），import-linter 的三條規則都維持通過。
- **遷移 0080**：新增 `admin_prefs` 表（目前只有 `approvals_digest`，沒有資料列就是預設開啟），並寫入一筆 schedules。
- **`DIGEST_ROLES`**（owner、editor）放在 `db/models/access.py`，有測試確認它等於 `permissions.py` 裡擁有 `approvals:decide` 的角色，兩邊不會各改各的。
- **`GET`／`PUT /api/admin/me/prefs`**：自己的設定，新增權限鍵 `self:prefs`，四種角色都有（viewer 也能關自己的信）。用權杖呼叫回 409。
- 操作紀錄的中文名稱補上 AD-09 的三個權限頁路由，以及這次的通知設定。

### 和計畫不同的地方

- **站內通知只有審批**：計畫寫的也只有審批，其他事件（例如鯨幣對帳異常）要等有需要時再接。
- **摘要的寄送時間和收件人規則是我定的**，計畫沒有寫到這麼細。寄送時間是 15:05（worker 上班時），收件人是會決定審批的人（owner、editor），finance 和 viewer 不會收到。

### 驗證

- 後端 `tests/api/test_admin_notifications.py` 共 6 項：
  - `DIGEST_ROLES` 和權限表一致；
  - 收件人規則（未驗證的、viewer、finance、關掉的都不寄）；
  - 信件內容（主旨的件數與快到期件數、最久的在前、已等與到期時間的寫法、收件匣連結、關閉方式）；
  - 某一封寄失敗不影響其他人；
  - 自己的開關可以改，用權杖呼叫回 409；
  - worker 的排程器有註冊這個 handler。
- `test_admin_permissions.py`：viewer 現在有 `self:prefs`，相關的兩個斷言跟著改。
- 遷移 0080：upgrade、`alembic check`、downgrade 再 upgrade 都通過。
- 前端 `admin-ui/bell.test.tsx` 共 3 項：件數、列表與快到期標示、收件匣連結、Esc 與點外面關閉、自己的開關（權杖沒有開關）。vitest 87 個檔案、1,021 項全過。
- **計畫的驗收條件**（真實瀏覽器，暫時的 Playwright spec，沒有提交）：打開 Dashboard 等即時連線，用 API 開始製作一則題材，等 API 回報有 1 件待審，然後量鈴鐺：**8 毫秒後**顯示「1」（要求是 5 秒內）；打開鈴鐺並截圖。
- 推送前合併 origin/main（D-245 的紀錄）後，在 worktree 跑完整驗證：ruff、lint-imports、openapi 檢查、typecheck、lint、build 通過；Playwright e2e 17 項、後端 pytest 2,520 項全過。
