# 新增後台頁面的檢查清單（AD-14）

> 適用：TR-10 交易頁、P6a 研究工作頁，以及之後任何 `/admin` 底下的頁面。
> 決策：D-234。元件與做法來自 AD-01～AD-13，執行紀錄見 `logs/devlog/08_ADMIN_REVAMP.md`。
> 標「🔒 測試會擋」的項目沒做到時，CI 會失敗（`frontend/web/src/features/admin-ui/conventions.test.ts`、`backend/tests/api/test_admin_permissions.py`、`test_admin_audit.py`）。

## 1. 頁面放進外殼

- [ ] **在 `features/admin-ui/nav.ts` 加一個項目**：分組、`label`、`href`、圖示、`go` 快捷字母（`g` 再按這個字母），需要權限時加 `need`。底下還有子頁就把前綴放進 `also`。🔒 `/admin` 底下每一頁都要在導覽地圖上（例外只有登入頁與純轉址頁），這樣才有麵包屑、側欄位置、⌘K 指令面板。
- [ ] **頁面外框用 `AdminPage` + `PageHeader`**（`features/admin-ui/PageHeader.tsx`）：列表頁 `width="wide"`、閱讀頁 `width="read"`；標題、說明、右上角動作都交給 `PageHeader`，不要自己寫 `mx-auto max-w-…`。
- [ ] **公司相關的頁面包在 `CompanyScope` 裡**，連到其他頁時用 `withCompany(href, company.id)`，才會帶著 `?company=`。
- [ ] **載入、空、錯誤**一律用 `states.tsx` 的 `LoadingState`、`EmptyState`、`ErrorState`，放在 `AdminPage` 裡面（載入中也看得到麵包屑）。

## 2. 列表

- [ ] **後端**：列表回傳 `Page[...]`，參數用 `Listing`（`cursor`、`limit`、`q`）加上自己的 `sort` Literal 和篩選，查詢交給 `page_rows`（SQL）或 `page_list`（已在記憶體），見 `autora_api/pagination.py`。不要一次回傳全部。
- [ ] **前端**：`useListState`（搜尋、排序、篩選、頁碼都在網址）＋`ListToolbar`＋`DataTable`＋`Pager`。排序用 `sortControl`、篩選用 `FilterDef`、需要的話用 `views="…"` 存篩選器。
- [ ] **詳情**：點列可以用 `usePeek` 先開側邊預覽；詳情頁用 `DetailLayout`／`Properties`，旁邊放 `ActivityTimeline`（這筆資料的操作紀錄）。
- [ ] **匯出**（需要的話）：在列表路由旁加 `…/export`，參數照抄列表，呼叫 `export.csv_export(...)`、`fetch` 直接呼叫列表函式；路由要註冊在 `/{id}` 路由**前面**。前端在 `ListToolbar` 傳 `onExport`。見 AD-13 與 `autora_api/export.py`。
- [ ] 狀態用 `StatusLozenge`，看板用 `features/board/`（狀態移動的規則放 `moves.json`，前後端共用）。

## 3. 權限與稽核

- [ ] **每一條會修改資料的後台路由都要在 `autora_api/permissions.py` 的 `ROUTES` 加權限鍵**（方法＋路由樣板）。🔒 漏了 `test_admin_permissions.py` 會失敗。需要新的鍵時加進 `ALL` 與適當角色的 `ROLE_PERMISSIONS`，並在 `features/access/AccessPage.tsx` 補上說明。
  - **交易頁（TR-10）用 `trading:view` 與 `trading:approve`**（D-248，已在權限表），兩個都只有 owner 和 finance 有：
    - 交易頁的**每一條讀取路由**（決定、訂單、損益、風險拒絕）都要在 `ROUTES` 加 `("GET", 路由): trading:view`；讀取預設是全部角色都能看，不加就會漏給 editor 和 viewer；
    - 核准交易的寫入路由對應 `trading:approve`，前端用 `useCan("trading:approve")` 決定是否顯示核准按鈕；
    - 導覽項目加 `need: "trading:view"`，editor 和 viewer 的側欄就不會出現交易頁。
  - **研究頁（P6a）用 `research:view` 與 `research:run`**（D-251，已在權限表），**只有 owner 有**：
    - 研究頁的每一條讀取路由（任務列表、結果）都要在 `ROUTES` 加 GET 的 `research:view`；
    - 啟動、取消、重跑研究任務的寫入路由對應 `research:run`；
    - 導覽項目加 `need: "research:view"`，其他角色的側欄不會出現研究頁。
  - 之後其他新的鍵，**加之前先和使用者確認哪些角色可以做**（AD-09 只定了四種角色）。
  - 讀取預設所有後台角色都能看；只有敏感的讀取（操作紀錄、讀者錢包）在 `ROUTES` 裡加 GET 的鍵。
- [ ] **前端用 `useCan("鍵")` 決定要不要顯示按鈕或表單**，側欄項目用 `need`。🔒 頁面要求的鍵必須是某條路由真的有的鍵（`x-permission`，從 openapi.json 讀）。後端一樣會擋（403），前端隱藏只是不讓人點到一定會失敗的東西。
- [ ] **在 `features/audit/labels.ts` 的 `ACTION_LABEL` 為每條新寫入路由取中文名稱**。🔒 有權限鍵的寫入路由沒有名稱會失敗。
- [ ] 寫入一律經過 `Operator`（`require_operator`），稽核中介層會自動記錄，不必在 handler 裡寫。公開（不需登入）的寫入路由要加進 `test_admin_audit.py` 的 `PUBLIC_WRITES`。

## 4. 互動

- [ ] **對話框**：確認用 `ConfirmDialog`，其他用 `Modal`／`Drawer`（`features/admin-ui/Dialog.tsx`，原生 `<dialog>`，已 portal 到 body，可以放在表單裡）。不要引入 Radix 或其他元件庫（D-234 ⑤）。
- [ ] **結果提示用 `useToast()`**，錯誤用 `"danger"`。
- [ ] **按鈕用 `Button`／`buttonClass`**，顏色只用 token（`text-muted`、`bg-accent`…），不要寫死色碼。
- [ ] 需要通知管理員的事件，接上 AD-10 的通知（頂欄鈴鐺與每日摘要，`accounts/admin_digest.py`）。
- [ ] 只有繁體中文，不做 i18n（D-234 ④）。

## 5. 驗證

- [ ] 前端加測試後跑 `pnpm exec tsc --noEmit`（vitest 不檢查型別）。
- [ ] 改了 API 要跑 `python backend/scripts/gen_openapi.py` 和 `pnpm gen-api`。
- [ ] 在真實瀏覽器（e2e 環境）截圖看過一次，包括手機寬度（390px）不出現橫向捲動。
