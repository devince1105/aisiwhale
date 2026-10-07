# 後台改版計畫：參考 Jira 的 UI/UX，並從 ERP 專案借用可用的部分

> 狀態：🚧 進行中。2026-10-07 定案為 D-234，第 6 節的五個問題照建議決定；AD-01～AD-13 已完成，執行紀錄見 `logs/devlog/08_ADMIN_REVAMP.md`。
> 任務編號：**AD-01 ~ AD-14**。
> 參考來源：`~/Dev/2026/erp-system-phoenix`（以下稱「ERP」），2026-10-07 實際讀過程式碼。

---

## 0. 結論先講

1. **ERP 的程式碼大多不能直接搬。** ERP 後端是 .NET 10 / C# / EF Core，我們是 FastAPI / SQLAlchemy，所以後端只能借「設計」，不能借程式。前端都是 Next.js + Tailwind v4，**殼層元件可以直接參考著改寫**。
2. **ERP 最有價值的三樣東西：**
   - 一套有側欄、頂欄、麵包屑、⌘K 指令面板的「後台外殼」；
   - 通用的審批引擎設計（`FormType + DocumentId`、多關卡、代理人、審批報表）；
   - 檔案儲存抽象（本機／R2 二選一）與 `MODULE:action` 權限鍵的命名方式。
3. **ERP 也有不少不能學的地方：**
   - RBAC 只是前端假資料：權限矩陣存在 localStorage，後端從不檢查；
   - 表格沒有共用元件，分頁在前端做；
   - 單號用「當天筆數 +1」產生，同時建立會撞號；
   - 錯誤用 `alert()` 顯示；token 放 localStorage。
   - 這幾點**我們目前反而做得比較好**（httpOnly cookie、RFC 7807 錯誤、openapi 型別）。不要倒退。
4. **我們後台真正缺的是：**
   - 外殼與導覽：現在沒有側欄，各頁自己畫頁首，Dashboard 兼當導覽頁；
   - 共用元件：表格、徽章、確認對話框、抽屜；
   - 列表規格：分頁、搜尋、排序、總數；
   - 一份管理操作稽核紀錄；
   - 角色權限：現在只有「是管理員／不是」兩種。
5. **Jira 適合我們的原因：** 我們後台的核心物件是審批、稿件、故事、交易提案，本質上都是「有狀態流、有負責人、需要留下紀錄的工作項」，和 Jira 的 issue 是同一種東西。所以借 Jira 的版面語言（列表、看板、詳情雙欄、活動紀錄），比借 ERP 的表單式版面更合適。

---

## 1. 現況盤點（aisiwhale 後台）

| 項目 | 現況 | 位置 |
|---|---|---|
| 技術 | Next.js 16 App Router、React 19、Tailwind v4（自訂 token：`bg-canvas`、`text-ink`、`border-line`…）、TanStack Query、openapi-fetch、zod、@dnd-kit、zustand | `frontend/web` |
| 外殼 | `admin/layout.tsx` 只有 `data-admin` 包裝與左下角浮動的主題切換；沒有側欄或全域導覽 | `src/app/admin/layout.tsx` |
| 頁面 | dashboard、approvals、office、agents、cycles、timeline、trace、tasks、newsroom（stories／articles／sources）、memberships | `src/app/admin/**` → `src/features/*` |
| 共用元件 | 只有 newsroom 的 `Badge`、`Section`、`Empty`；表格是各頁手寫的 `<table>`；沒有對話框 | `features/newsroom/parts.tsx` |
| 版面寬度 | `max-w-3xl`、`4xl`、`5xl`、`6xl` 各頁不同；頁首的標題列每頁複製一份 | 各 feature |
| 公司切換 | `?company=` 或 localStorage，畫面上看不到切換器 | `features/company/CompanyScope.tsx` |
| 授權 | `require_operator`：共用 bearer token，或 `ADMIN_EMAILS` 名單上的 cookie。只有一種權限，沒有角色 | `api/autora_api/deps.py` |
| 列表 API | 只有 `limit`，沒有 offset、cursor、總數、搜尋或排序；approvals 一次回傳全部 | `routers/approvals.py`、`routers/newsroom.py` |
| 稽核 | 有 `state_transitions`（狀態機稽核）、`policy_decisions`、outbox 事件。**沒有管理操作稽核**。newsroom 有 5 個寫入動作沒有記下操作者：cover swap、cover delete、access、section、POST sources | `routers/newsroom.py` 約 194、212、229、248、367 行 |
| 通知 | 待審批沒有 email，也沒有站內通知；只有 TeamChat 裡的連結 | `features/office/chatModel.ts` |
| 設定 | 沒有設定頁；可改的只有 office-theme、budgets、capital；其他都靠 env | — |

---

## 2. ERP 專案盤點：可用、可參考、不要學

### 2.1 前端：可以參考著改寫（同為 Next.js + Tailwind v4）

| ERP 元件 | 位置（`frontend/src/`） | 用法 |
|---|---|---|
| `AppLayout` | `features/core/components/AppLayout.tsx` | 頂欄＋側欄＋可捲動的主區，並有列印用 class。照這個結構改寫成我們的 `AdminShell` |
| `Sidebar`（436 行） | `features/core/components/Sidebar.tsx` | 可收合（w-64 ↔ w-16）、手風琴分組、目前路由高亮。**它的選單寫死在 JSX 裡，每組複製一次。** 我們改成以設定資料驅動 |
| `Navbar` | `features/core/components/Navbar.tsx` | 搜尋按鈕（開指令面板）、主題切換、使用者選單 |
| `Breadcrumbs` | `features/core/components/Breadcrumbs.tsx` | `{label, href?}[]` 的簡單元件；我們改成依路由設定自動產生 |
| 指令面板 | `CommandPalette.tsx`、`contexts/CommandPaletteContext.tsx` | 用 cmdk，⌘K 開啟。ERP 的面板只能跳頁，我們會再加「搜尋資料」 |
| 看板拖放 | `app/crm/page.tsx` | 先在畫面上移動（樂觀更新），API 失敗就退回；拖到特定欄位時先開對話框再存。我們用已安裝的 @dnd-kit 實作同樣的模式 |
| 審批流程圖 | `features/hr/components/ApprovalFlow.tsx` | 把審批的每一關畫成步驟條 |
| 匯出 | `utils/exportUtils.ts` | SheetJS 匯出 Excel。我們改成由後端產生 CSV，見 AD-13 |
| 圖表與統計卡 | `features/accounting/components/StatCards.tsx`、各 `*Dashboard.tsx` | 只參考版面；圖表依 `dataviz` 規範重做 |

### 2.2 後端：只參考設計（C# → Python 要重寫）

| ERP 設計 | 位置（`backend/src/`） | 對我們的意義 |
|---|---|---|
| **通用審批引擎** | `ERP.Modules.HR/Services/ApprovalService.cs`（571 行）、`Models/ApprovalInstance.cs`、`WorkflowStepDefinition.cs` | 以 `(FormType, DocumentId)` 掛到任何單據；有多關卡、以相對角色找審批人（直屬主管、財務…）、建立時就固定審批人名單、代理人、`GetPendingForUserAsync` 收件匣，以及 `GetReportAsync` 報表（通過率、平均處理時數、各關卡耗時、卡住的件）。我們的 `runtime/approvals/service.py` 已經有逾期重問與代理窗口，**不必換引擎**。要借的是：① 審批報表（AD-12）；② 交易代理 TR-12 和鯨幣人工調整需要「同一張單、多種表單」時，改用 `form_type` 欄位 |
| 檔案儲存抽象 | `ERP.Shared/Interfaces/IReceiptStorage.cs`、`ERP.Host/Storage/ReceiptStorage.cs` | 本機或 R2 二選一，另有 6MB 上限、副檔名白名單、GUID 檔名。我們封面圖已經在用 R2，可以順便檢查是否有同樣的防護 |
| `MODULE:action` 權限鍵 | `frontend/src/utils/rbac.ts` | 鍵的命名（view、create、edit、delete、approve）和「角色預設＋個人覆寫」的模型可以用。**但要放在後端資料庫並在後端檢查**（AD-09） |
| 系統設定表 | `Accounting/Models/SystemSetting.cs`、`SettingsController.cs` | key/value 表加上每個 key 一支型別化的 API。我們改成一份 pydantic schema 管全部 key（AD-11） |
| 關帳日鎖 | `VouchersController.cs`（`Accounting:ClosedUntilDate`） | 「某日之前的資料不准改」。鯨幣帳本與財務以後可能需要 |
| 模組化單體註冊 | `ERP.Host/Program.cs` 的 `Add*Module()` | 我們已經是 `domains/*` 模組化單體，不需要另外做 |

### 2.3 不要學

| ERP 的做法 | 問題 | 我們的做法 |
|---|---|---|
| RBAC 矩陣存 localStorage，後端只檢查粗略的 `[Authorize(Roles=…)]` | 權限可以在瀏覽器裡改掉，等於沒有權限 | 後端檢查，前端只用來隱藏按鈕 |
| token 存 localStorage | 被 XSS 就會外洩 | 維持 httpOnly cookie（D-230） |
| `alert()` 顯示錯誤，錯誤格式各寫各的 | — | 維持 RFC 7807，前端改成 toast 或行內錯誤 |
| 單號 `PO-{yyyyMMdd}-{count+1}` | 同時建立會撞號 | 需要可讀單號時，用 Postgres sequence 或 `UNIQUE` 加重試 |
| 分頁在前端做；大多數列表一次回傳全部 | 資料一多就慢 | 後端分頁（AD-04） |
| 沒有共用表格、只用 HTML `required` 驗證 | — | DataTable 元件＋zod |

---

## 3. 要借 Jira 的哪些 UI/UX

不是照抄 Atlassian 的外觀，是借它的**資訊架構與操作習慣**，配色仍用我們的 token（`data-admin` 淺色／深色）。

| Jira 的元素 | 在我們後台對應到 | 任務 |
|---|---|---|
| 左側欄：專案切換＋分組導覽，可收合 | 側欄最上方是**公司切換器**（取代看不見的 `?company=`），下面分組：工作（審批、任務、週期）／新聞室（故事、稿件、來源）／營運（辦公室、代理人、時間線）／會員與金流（VIP 贈送、鯨幣、訂單）／交易（TR-10）／系統（設定、稽核、權限） | AD-02 |
| 頂欄：全域搜尋＋「建立」按鈕＋通知鈴＋頭像 | 搜尋開 ⌘K 面板；「建立」選單（新故事、新來源、贈送 VIP…）；鈴鐺顯示待審批數 | AD-02、AD-03、AD-10 |
| 狀態用 lozenge 標籤（灰＝待辦、藍＝進行中、綠＝完成、紅＝失敗） | 統一一個 `<StatusLozenge>`，用一張表把各領域的狀態（approval、article、story、run、comp）對應成 4～5 種語氣，取代目前各自的 `TONE_BADGE` | AD-01 |
| issue 列表：篩選條件以小標籤（chips）呈現、可存成篩選器、欄位可排序、勾選後批次操作 | `DataTable`：篩選、排序、分頁都寫在 URL 參數裡（可分享、可回上一頁）；「我的篩選器」先存在 localStorage | AD-05 |
| 看板 | 故事和稿件的生產流程（題目 → 撰寫 → 待審 → 已發佈）；之後也用在交易提案。只允許狀態機合法的移動 | AD-08 |
| issue 詳情雙欄：左邊內容，右邊屬性面板（狀態下拉、負責人、標籤、日期） | 稿件、故事、審批詳情統一成這個版面；右欄的狀態下拉只列出現在能走的下一步 | AD-07 |
| 活動分頁：全部／留言／歷史紀錄 | 詳情頁底部的時間軸：狀態變化（`state_transitions`）＋管理操作（新的 `admin_actions`）＋審批決定 | AD-06、AD-07 |
| 在列表上點一列，右側滑出預覽 | 列表點一列時，從右側開 Drawer 預覽，不離開列表；按 Enter 才進完整頁面 | AD-07 |
| 鍵盤快捷鍵：`/` 搜尋、`g` 再按 `d` 去 dashboard、`j`/`k` 上下列、`?` 顯示說明 | 同上。審批頁另加 `a` 核准、`r` 駁回，按了先開確認對話框 | AD-03 |
| 儀表板由小卡組成 | 現在的 Dashboard 只保留 KPI 和待辦卡片，導覽功能移交給側欄 | AD-02 |

---

## 4. 任務分解（AD-01 ~ AD-14）

依賴順序：**AD-01 → AD-02 → AD-04 → AD-05** 是主線，其他可穿插。每項都附驗收條件。

### 第一階段：外殼與共用元件（只動前端，不動 API）

**AD-01 共用元件** `src/features/admin-ui/`
- `PageHeader`（麵包屑、標題、右側動作區）、`StatusLozenge`＋狀態語氣對照表、`Button`（primary／subtle／danger）、`EmptyState`、`ErrorState`、`Skeleton`、`ConfirmDialog`（破壞性動作要打字確認或二次點擊）、`Drawer`、`Toast`。
- 頁面寬度統一成兩種：清單頁 full（自適應），閱讀頁 `max-w-5xl`。
- 驗收：
  - newsroom、approvals、memberships 三個功能區改用這些元件；
  - 撤銷 VIP 贈送、下架稿件、退役代理人這三個動作都會先跳確認對話框；
  - 現有 Vitest 與 Playwright 全部通過。

**AD-02 AdminShell：側欄、頂欄、麵包屑、公司切換器**
- `src/features/admin-ui/nav.ts` 是唯一的導覽設定（分組、路徑、圖示、所需權限鍵）。側欄、麵包屑和 ⌘K 面板都讀這一份。
- 側欄可收合，收合狀態存在 localStorage；手機寬度改成抽屜式。
- 公司切換器放在側欄頂部，背後仍走 `CompanyScope`，只是讓使用者看得到、點得到。
- 移除各頁手寫的「Dashboard／辦公室」連結和 `NewsroomHeader` 的分頁列；`ConnectionBadge` 移到頂欄。
- `/admin/login` 不套外殼。trace 和 tasks 頁補上公司範圍。
- 驗收：
  - 任何後台頁都能用兩次點擊到達其他任何頁；
  - 375px 寬度下沒有橫向捲動；
  - 淺色和深色主題都檢查過。

**AD-03 ⌘K 指令面板與快捷鍵**
- 安裝 cmdk。面板分三組：跳頁（來自 `nav.ts`）、動作（新故事…）、搜尋。搜尋第一版只做前端的最近瀏覽紀錄，AD-04 完成後改打 API。
- 快捷鍵：`/`、`g` 系列、`j`/`k`、`?` 說明面板。焦點在輸入框時一律不觸發。
- 驗收：只用鍵盤就能完成「開 approvals → 選第一件 → 預覽 → 核准」，而且核准前有確認。

### 第二階段：列表規格與資料表

**AD-04 後端列表規格**（`api/autora_api/pagination.py`）
- 統一的 query 參數：`cursor`、`limit`（≤100）、`q`、`sort`（例如 `-created_at`）、各列表自己的篩選欄位。
- 回應格式：`{items, next_cursor, total?}`；`total` 用 `count(*)`，只在資料量可接受的表上提供。
- 依序套用到：approvals（目前一次回傳全部，最優先）→ articles → stories → comps → sources → events。
- 維持 RFC 7807 錯誤格式。重新產生 `openapi.json` 和 `schema.gen.ts`。
- 驗收：
  - 每個改過的 endpoint 都有 pytest，涵蓋分頁邊界、排序穩定（以 id 當第二排序鍵）、`q` 不分大小寫；
  - approvals 在 1,000 筆假資料下回應 < 200ms。

**AD-05 `DataTable`**
- 欄位設定（標題、寬度、是否可排序、格式化函式）、可勾選列、批次動作列、密度切換（一般／緊湊）。
- 篩選標籤、排序、cursor 都放在 URL 參數裡。「我的篩選器」先存 localStorage；如果要跨裝置，再另提一項把它存到後端。
- 用 `@tanstack/react-table`，不畫 UI 的 headless 版本；樣式用我們自己的 token。
- 驗收：articles、comps、approvals 三張表換成 DataTable；重新整理頁面後篩選條件還在；複製網址給別人，打開的畫面相同。

### 第三階段：追溯性（Jira 的「歷史紀錄」）

**AD-06 管理操作稽核**（migration：`admin_actions`）
- 欄位：`id`、`actor`、`action`（如 `newsroom.article.unpublish`）、`target_type`、`target_id`、`company_id`、`before`、`after`（JSONB，只存改到的欄位）、`ip`、`created_at`。只能新增，不能改或刪。
- 做成 FastAPI dependency 或裝飾器，所有 `Operator` 的非 GET 動作都寫一筆。順便修好 newsroom 那 5 個沒記下操作者的動作。
- 新增頁面 `/admin/audit`：用 DataTable 依操作者、動作、對象、日期篩選。
- 驗收：
  - 每個非 GET 的管理 endpoint 都有測試，確認會寫入 `admin_actions`；
  - 一個測試掃描所有 router，找出沒套上稽核的寫入路由，有就失敗。

**AD-07 詳情頁雙欄與 Drawer 預覽**
- 稿件、故事、審批三種詳情頁：左欄是內容，右欄是屬性面板，底部是活動時間軸。時間軸合併 `state_transitions`、`admin_actions` 和審批決定，依時間排序。
- 列表點一列時開 Drawer 預覽，內容和詳情頁共用同一個元件。
- 驗收：從列表開 Drawer 不會換網址（或只用 `?peek=` 參數）；按瀏覽器的上一頁可以關掉 Drawer。

**AD-08 看板**
- 先做故事／稿件看板，欄位是生產流程的各個狀態。只能拖到狀態機允許的下一個狀態，其餘欄位在拖動時顯示為不可放；需要說明理由的動作（駁回、要求修改）拖放後先開對話框。
- 拖放的處理照 ERP CRM 看板：先在畫面上移動，API 失敗就退回並跳出 toast。
- 驗收：用狀態機的轉移表跑表格驅動測試，確認不合法的移動在前端和後端都會被擋下。

### 第四階段：權限、通知、設定

**AD-09 RBAC（取代二分法）**
- 權限鍵沿用 ERP 的 `MODULE:action` 命名，例如 `newsroom:publish`、`approvals:decide`、`finance:edit`、`memberships:grant`、`coins:adjust`、`trading:approve`、`system:settings`、`audit:view`。
- 預設角色：`owner`（全部）、`editor`（新聞室與審批）、`finance`（財務、鯨幣、會員）、`viewer`（只讀）。
- 資料表：`admin_roles`（reader_id → role）；有需要時再加 `admin_role_overrides`。`ADMIN_EMAILS` 降級成「第一次登入時自動給 owner」的初始名單。
- 後端把 `require_operator` 擴充成 `require(perm)`。共用 bearer token 等同 owner，只給機器和緊急情況使用，並寫進稽核。
- 前端從 `/api/admin/auth/me` 取得權限清單，用來隱藏沒權限的導覽項目和按鈕；真正的檢查仍在後端。
- 新增頁面 `/admin/settings/access`：角色矩陣（參考 ERP 的 `EmployeePermissionSettings.tsx` 版面），每次修改都寫進稽核。
- 驗收：每個權限鍵都有正反兩面的測試；viewer 呼叫任何寫入 endpoint 都回 403（problem+json）。

**AD-10 通知**
- 頂欄鈴鐺：顯示待審批數，以及即將逾期的件（D-001、D-131 的逾期重問）。資料來源用現有的 WebSocket 事件。
- Email：待審批的每日摘要，由 Resend 寄出，只寄給有 `approvals:decide` 權限的人；可在個人設定關閉。
- 驗收：新審批出現後 5 秒內，鈴鐺上的數字會增加。

**AD-11 系統設定頁**（migration：`system_settings`）
- 用一份 pydantic schema 定義所有 key（型別、預設值、說明、需要的權限）。把班表、上班時段這類目前寫在 env、但其實可以在執行中改的值搬進來。秘密資訊仍留在 env。
- 每次修改都寫進稽核，並發出 `settings.changed` 事件，讓 worker 重新讀取。
- 驗收：改設定後不必重新部署就會生效，並且在稽核頁看得到修改前後的值。

### 第五階段：報表與匯出

**AD-12 審批報表**（借 ERP 的 `GetReportAsync`）
- 指標：通過率、駁回率、要求修改率、平均和 P90 處理時數、逾期重問次數、目前卡住的件（超過 N 小時）。可依領域（newsroom、trading、coins）切開來看。
- 放在 `/admin/approvals/report`，圖表依 `dataviz` 規範畫。

**AD-13 CSV 匯出**
- DataTable 的「匯出」按鈕會把目前的篩選條件帶給後端，後端用串流回傳 CSV（UTF-8 BOM，讓 Excel 正確讀中文）。匯出動作寫進稽核。

**AD-14 讓已規劃的頁面直接用新外殼**
- TR-10 交易頁、P3 鯨幣人工調整、P6a 研究工作頁，一律用 AD-01～AD-09 的元件和權限鍵開發，不再各自手寫。

---

## 5. 建議順序與工作量（粗估）

| 順序 | 任務 | 粗估 | 可見成果 |
|---|---|---|---|
| 1 | AD-01、AD-02 | 2～3 天 | 後台馬上「像一個系統」：有側欄、公司切換器、版面一致 |
| 2 | AD-03 | 1 天 | ⌘K 與快捷鍵 |
| 3 | AD-04、AD-05 | 3～4 天 | 列表能分頁、搜尋、排序，approvals 不再一次回傳全部 |
| 4 | AD-06、AD-07 | 3 天 | 誰做了什麼都查得到；詳情頁有活動時間軸 |
| 5 | AD-09 | 2～3 天 | 角色權限（建議在 P8 開放付款、TR 實盤之前完成） |
| 6 | AD-08、AD-10、AD-11 | 3～4 天 | 看板、通知、設定頁 |
| 7 | AD-12、AD-13 | 1～2 天 | 報表與匯出 |

**與其他工作的關係：**
- AD-06（稽核）和 AD-09（RBAC）建議排在 **P8 開放付款**與 **TR-12 實盤核准**之前。這兩件事都涉及錢，需要知道誰有權限、誰做了什麼。
- AD-01、AD-02 只動前端，可以和其他工作階段的後端工作（HD-11、P3）並行，衝突最少。

---

## 6. 待拍板的問題

1. **角色的切法**：owner／editor／finance／viewer 這四種夠嗎？鯨幣調整要不要獨立成一種角色？
2. **共用 bearer token 的去留**：保留作為機器和緊急入口，並寫進稽核？還是改用個人 API key？
3. **已存篩選器**：只存 localStorage 就好，還是要存後端、可以分享給其他管理員？
4. **後台語言**：維持只有繁中，還是把字串抽出來，為之後的英文做準備（ERP 也沒做 i18n）？
5. **元件庫**：繼續全部手寫，還是引入 shadcn/ui（以 Radix 為底，處理無障礙與焦點管理）？我的建議是：Dialog、Drawer、Dropdown、Combobox 這四種用 Radix primitives，其餘自己寫，以維持現有的 token 風格。
