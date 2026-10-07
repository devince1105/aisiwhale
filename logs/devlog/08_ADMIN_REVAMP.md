# 後台改版（AD-01 ~ AD-14）

計畫與任務分解在 `logs/admin/01_ADMIN_REVAMP_PLAN.md`，決策是 D-234。本檔記錄實際執行。

## 開發計畫

| 順序 | 任務 | 依賴 | 狀態 |
|---|---|---|---|
| 1 | AD-01 共用元件 | — | ✅ 2026-10-07 |
| 2 | AD-02 外殼：側欄、頂欄、麵包屑、公司切換器 | AD-01 | ✅ 2026-10-07 |
| 3 | AD-03 ⌘K 指令面板與快捷鍵 | AD-02（`nav.ts`） | ✅ 2026-10-07 |
| 4 | AD-04 後端列表規格、AD-05 DataTable | — | ⏳ |
| 5 | AD-06 管理操作稽核、AD-07 詳情頁 | AD-04 | ⏳ |
| 6 | AD-09 RBAC（排在 P8 開放付款、TR-12 之前） | AD-06 | ⏳ |
| 7 | AD-08、AD-10、AD-11、AD-12、AD-13 | — | ⏳ |

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
