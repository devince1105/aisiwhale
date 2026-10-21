# 私人投資研究室（Private Investment Lab）：第一階段架構盤點與設計

> 2026-10-21，對應需求 0-B。本階段**只設計、不實作**：沒有新增資料表、API 或頁面。
> 盤點基準是 `a2d9f0e` 與 D-256 分支。標記：【確認】表示看過程式；【推論】表示由程式推得；【待確認】表示 repo 內無法判定。

## 一、目標與邊界

- **用途**：一個只有專案擁有者（owner）能用的研究工作區，用來整理個人財務、持股、投資目標，並研究台股、美股與交易策略。
- **不是公開產品**：私人研究結果不會自動發布到公開網站；個人財務資料也不會進入新聞室或任何讀者看得到的流程。
- **本階段先做**：一般財務分析、公開資料研究、情境試算、風險分析、歷史策略驗證。
- **法規確認前不啟用**：個人化買賣指令、個人化目標價、個人化資產配置建議（見第七節）。

## 二、現有架構盤點（與私人研究室相關的部分）

| 項目 | 現況 | 對私人研究室的意義 |
|---|---|---|
| owner 身分 | 後台 RBAC 有 owner、editor、finance、viewer 四種角色；`ADMIN_EMAILS` 與 bearer token 永遠是 owner（`backend/api/autora_api/deps.py:173-218`、`permissions.py`）【確認】 | 可以沿用：私人研究室只開給 owner |
| owner 專屬權限鍵 | `research:view`、`research:run` 只在 owner 的權限集合裡（D-251，`permissions.py:33-39`），目前沒有任何路由使用【確認】 | 建議另立 `lab:view`、`lab:write`，同樣只給 owner。不和 P6a 共用，因為 P6a 將來可能開放給其他角色 |
| 預設讀取權限 | GET 路由除非列在 `ROUTES`，否則**任何後台角色都能讀**（`permissions.py:82-127`）【確認】 | 私人研究室的每一條路由（包括 GET）都要在 `ROUTES` 加權限鍵 |
| 後台操作紀錄 | `AuditMiddleware` 會把每個後台寫入的 **JSON body** 存進 `admin_actions`，只遮蔽密碼、token、secret，而且表是 append-only（`backend/api/autora_api/audit.py:74-90`、`db/models/audit.py:44`）【確認】 | **財務數字會被永久記錄**。必須讓私人研究室的路由只記路徑與欄位名稱，不記數值 |
| Agent 執行紀錄 | `agent_steps.blob_key` 會把完整的 prompt 與回應存進 R2 私有 bucket（T-210，`db/models/tasks.py:219-220`）；`tasks.output` 存 agent 的結構化輸出；`TOOL_COMPLETED` 事件存工具摘要（`runtime/events/catalog.py:210-216`）【確認】 | 如果私人研究室走共用的 agent runtime，個人資料會進入這些紀錄 |
| 後台頁面 | 任務、trace、時間軸、3D 辦公室都讀上述紀錄（`/admin/tasks/[taskId]`、`/admin/trace/[runId]`、`/admin/timeline`、`/admin/office`）；editor 與 viewer 也能看【確認／推論】 | 私人研究室的 LLM 工作**不能**走共用任務佇列，否則其他後台角色看得到 |
| 即時推播 | WebSocket 把事件推給後台辦公室（`realtime/gateway.py`）【確認】 | 私人研究室不發即時事件，或只發不含內容的事件 |
| 模型閘道 | 所有模型呼叫都經過 `runtime/models/gateway.py`；正式環境的供應商由 Render 的 `MODEL_PROVIDER` 決定（`sync:false`，D-053 記錄為 OpenAI）【確認＋待確認】 | 私人資料送到第三方模型前，要先確認該供應商 API 的資料保留與訓練政策【待確認】 |
| 搜尋與向量 | 研究員的 `web_search` 走 Tavily；證據會切段，再經 NVIDIA 產生向量（`.env.example`）【確認】 | 查詢字串與證據內容都會送到第三方，不能含個人財務資料 |
| 計算工具 | D-256 的 `backtest.py`、`snapshot.py` 是純函式，不依賴新聞室流程【確認】 | 可以直接重用來做策略驗證與持股的價格數據 |
| 日線資料 | 追蹤的 20 檔有約 5 年日線；其他個股要有人開過個股頁才會開始抓（`securities.py`）【確認】 | 使用者指定的股票若不在追蹤範圍，要先觸發抓取；資料不足時要明確標示，不可補造 |
| 錯誤紀錄 | worker 與 API 用 `log.warning`、`log.exception`，輸出到 Render 的日誌【確認】 | 私人研究室的錯誤訊息不可帶金額或持股明細 |
| 資料庫備份 | Neon 有時間點還原（PITR）【推論，依 Neon 服務】 | 刪除的資料在備份保留期內仍可能存在；不能宣稱「刪了就不存在」 |

## 三、最小可行方案

### 3.1 模組位置
- 新增 `backend/autora/domains/private_lab/` 作為獨立領域，在 `app.py` 註冊，依照 `ARCHITECTURE_V2_1` 的擴充方式。
- import-linter 新增兩條規則：
  - `private_lab` 不得 import `domains.newsroom` 的寫入模組（publisher、tools、workflow）；只允許 import 純計算模組（`backtest`、`snapshot`）與唯讀的行情函式（`price_history.history`）。
  - `domains.newsroom` 不得 import `private_lab`。

### 3.2 資料表（P-L1 才建，屬於遷移）

每張表都有 `company_id`、`owner_reader_id`，以及建立與修改時間。

| 表 | 內容 | 資料狀態 |
|---|---|---|
| `lab_profile_items` | 資產、負債、每月現金流、投資預算、財務目標（類別、名稱、金額、幣別、日期） | 每筆都有 `status`：`confirmed`、`estimated`、`missing`；只有 `confirmed` 會進入正式計算，`estimated` 會在結果上標示 |
| `lab_holdings` | 持股（市場、代號、股數、成本、帳戶標籤） | 同上 |
| `lab_research_notes` | 個股研究（代號、研究日期、資料來源清單、支持與反對證據、版本號） | 保留每個版本 |
| `lab_scenarios` | 情境試算（假設參數、結果、計算程式版本） | 結果一律標為「試算」 |
| `lab_backtests` | 策略驗證（規則、成本假設、樣本數、樣本內外統計、最大回撤、資料期間、程式版本） | 重用 `backtest.run` |

不和 `stories`、`claims`、`articles`、`evidence` 共用任何表，也沒有外鍵連過去。

### 3.3 權限與路由
- API 一律放在 `/api/admin/lab/*`，使用 `lab:view`（GET）與 `lab:write`（寫入），兩個鍵都只在 owner 的權限集合裡。`test_admin_permissions` 鎖住「只有 owner」。
- 回應一律加 `Cache-Control: private, no-store`。
- 操作紀錄：`audit.py` 對 `/api/admin/lab/` 只記方法、路徑、狀態碼與欄位名稱，**不記 body 的值**；加測試鎖住這一點。
- 前台：後台新增「私人研究室」頁，nav 設 `need: "lab:view"`；公開網站完全不出現。

### 3.4 計算與 LLM 的分工
- **由程式計算**（P-L2）：
  - 淨資產、現金流、緊急預備金月數；
  - 持股市值、集中度（單一持股、產業）、匯率曝險；
  - 情境試算與敏感度分析（例如市場跌 10%、20%、30% 時的損失；定期定額在不同報酬假設下的結果）；
  - 策略回測（`backtest.py`）。

  所有結果都標示「依假設試算，不代表未來報酬」。
- **LLM 只做公開資料研究**（P-L3）：
  - 個股研究走專用的研究流程，只送公開資訊（代號、公開財報、新聞），不把持股數量、金額或財務檔案放進 prompt；
  - 這個流程**不走共用的 tasks 佇列與 agent_steps blob**，而是直接呼叫 gateway，trace 只記 token 與費用，不記內容；
  - 研究結果存入 `lab_research_notes`，不發布。
- **把個人資料送進 LLM**（例如「用我的持股解釋風險」）：預設關閉；要使用時，每次都要 owner 明確同意，而且要先確認模型供應商的資料保留條款。

### 3.5 如何確保私人資料不會進入公開發布流程

| 防線 | 做法 | 驗收方式 |
|---|---|---|
| 1. 資料分表 | 私人資料只在 `lab_*` 表；公開網站只讀 `articles`、`article_versions` 與行情表 | 測試：所有 `/api/public/*` 回應不含任何 `lab_*` 資料 |
| 2. 發布只有一條路 | 只有 `newsroom.publish` 服務節點能把 `articles` 改成 PUBLISHED；私人研究室沒有建立 story、article 的程式路徑 | import-linter 規則與一個靜態測試：`private_lab` 不 import newsroom 的寫入模組 |
| 3. 不走共用 agent runtime | 私人研究室不建 `tasks`，不寫 `agent_steps` blob；editor、viewer 看得到的任務、trace、時間軸、辦公室頁都不會出現私人內容 | 測試：私人研究室的動作不新增 `tasks`、`agent_steps`、事件 |
| 4. 不記數值 | `admin_actions` 只記路徑與欄位名稱；錯誤訊息不帶金額 | 測試：私人研究室的寫入之後，`admin_actions.input` 只有 `body_keys` |
| 5. 第三方傳輸 | 預設不把個人資料送到模型、搜尋或向量服務；只送公開資訊 | 程式檢查：送往 gateway 的 prompt 由白名單欄位組成 |
| 6. 只有 owner | `lab:*` 權限鍵只給 owner；每條 GET 都要有權限鍵 | `test_admin_permissions` |

**不能保證的事**（不可對外宣稱「資料絕對不外傳」）：

- 資料存在 Neon（新加坡）與 Render，受這兩家的保存與備份政策約束；
- 送到模型供應商的內容，受其 API 條款約束；
- 後台 owner 帳號的安全性，取決於 Google 登入或密碼，以及管理信箱本身的安全。

## 四、資料流

```
owner（後台，lab:write）
   │  手動輸入或確認：財務檔案、持股（confirmed／estimated／missing）
   ▼
/api/admin/lab/*  ── audit 只記路徑與欄位名稱 ──▶ admin_actions
   │
   ▼
lab_* 表（Neon）◀── 純計算：snapshot、backtest、集中度、情境（程式）◀── price_bars（唯讀）
   │
   ├──▶ 後台「私人研究室」頁（只有 owner，no-store）
   │
   └──▶（P-L3）公開資料研究：只送代號與公開資訊 ──▶ 模型閘道 ──▶ lab_research_notes
                                                     （不寫 tasks、agent_steps、事件）

公開網站 ◀── articles（新聞室）   ✗ 沒有任何從 lab_* 出去的箭頭
```

## 五、分階段計畫與驗收

| 階段 | 內容 | 驗收條件 | 粗估 |
|---|---|---|---|
| **P-L0**（本文件） | 盤點與設計 | 本文件經使用者確認 | 完成 |
| **P-L1** | `lab_*` 表與遷移、`lab:*` 權限鍵、audit 不記數值、後台頁面的手動輸入與確認（不含 LLM） | 第三節第 1、4、6 項防線的測試全過；非 owner 角色讀取一律 403 | 3–5 天 |
| **P-L2** | 計算：淨資產、現金流、集中度、曝險、情境與敏感度、策略驗證（重用 `backtest.py`，支援使用者自訂參數，但結果要存規則、成本、樣本數與樣本外表現） | 每個公式都有測試；`estimated`、`missing` 的資料在結果上標示；資料不足時拒絕計算，不補造 | 4–6 天 |
| **P-L3** | 公開資料的個股研究，不走共用 runtime、不送個人資料 | 第 3、5 項防線的測試全過；研究結果有日期、來源、版本 | 4–6 天 |
| **P-L4**（待審查） | 個人化建議類功能 | 律師意見 | — |

## 六、需要你決定才能進入 P-L1 的事

只有這一項：**模型供應商**。P-L3 要把公開資料研究交給哪個模型，以及是否接受「個人資料永遠不送模型」這個預設。P-L1、P-L2 不用模型，所以不受影響，可以先做。

## 七、需要進一步審查的功能（獨立列出，不擋其他功能）

| 功能 | 疑慮 | 本階段的替代做法 |
|---|---|---|
| 依我的財務與持股，給出「該買或該賣什麼」 | 個人化買賣建議（R5） | 只呈現集中度、曝險與情境試算的數字，不產生指令 |
| 個人化目標價 | 個股價位預測 | 只呈現他人具名的目標價，並附出處 |
| 個人化資產配置建議、再平衡建議 | 自動化投資顧問（管理規則第 25 條之 1） | 只提供使用者自己輸入配置比例後的試算，由使用者自己比較 |
| 把私人研究室開給其他使用者 | 收費加個人化會碰到投顧法；個資處理也要另外規範 | 不做；只給 owner |
