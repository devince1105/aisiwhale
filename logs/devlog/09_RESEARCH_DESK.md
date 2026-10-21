# 研究台（D-256）：新聞室轉為投資研究

說明、資料缺口與風險清單在 `logs/research/03_RESEARCH_DESK.md`；私人研究室（0-B）的設計在 `logs/research/04_PRIVATE_LAB_DESIGN.md`；決策是 D-256。本檔記錄實際執行。

## 開發計畫

| 順序 | 任務 | 依賴 | 狀態 |
|---|---|---|---|
| R-01 | 選題依研究價值排序，候選題材附上公司與事件標記 | — | ✅ 2026-10-21 |
| R-02 | 四種文章格式，存在 `stories.seed.format`；新增「個股研究」「策略研究」分類 | R-01 | ✅ 2026-10-21 |
| R-03 | 研究員、分析師、寫手依格式拿到工作說明；研究快報為預設格式 | R-02 | ✅ 2026-10-21 |
| R-04 | 本站自算紀錄：`market_snapshot`、`run_backtest` | — | ✅ 2026-10-21 |
| R-05 | 個股研究與策略研究的委派工具 | R-02、R-04 | ✅ 2026-10-21 |
| R-06 | 檢查：多空與風險、推論、段落結構、不給當下訊號、自算紀錄必附 | R-03 | ✅ 2026-10-21 |
| R-07 | 推送與部署 | 使用者確認 | ✅ 2026-10-21 |
| R-08 | 上線一週後檢視：重試與浪費（`newsroom_waste.py`）、審批結果、新分頁的文章 | R-07 | ⏳ |
| D1–D6 | 資料缺口（財報、股利、法人、日程、交易日曆、文章與個股關聯） | 授權決定 | ⏳ 另列待辦 |
| P-L1–P-L3 | 私人研究室 | 使用者確認設計 | ⏳ |

---

## 2026-10-21：R-01～R-06

### 背景

Phase 0 盤點（2026-10-21）的結論：Agent 執行層與查證層都可以直接沿用，但選題只看題材分數，文章只有一種「新聞」格式，也沒有回測。使用者重新校正方向（0-A）：重點是改 Agent 的報導方向與內容流程，法規與授權另列風險清單，不能擋住實作。

### 做了什麼

| 檔案 | 內容 |
|---|---|
| `research.py`（新） | 四種格式、事件詞表（中文任意位置比對；英文從字首比對，結尾最多 4 個字元）、研究價值公式、各職位的格式說明、段落大綱檢查、「目前符合進場條件」這類說法的檢查、多空與風險的最低數量 |
| `backtest.py`（新） | 指標（SMA、標準差、Wilder RSI、ATR、前 N 日最高與最低）、三條固定規則、成本、回測（收盤判斷、次日開盤成交、樣本內外切分）、證據文字 |
| `snapshot.py`（新） | 股價數據：收盤價、52 週高低、各期報酬、均線、RSI、波動度、量比，以及「本站沒有哪些資料」 |
| `tools/research.py`（新） | `market_snapshot`、`run_backtest`（研究員用）；`commission_company_report`、`commission_strategy_study`（總編用）。委派被拒（題材比例、公司上限）時，為這次委派建立的題材會被刪除，不會變成候選 |
| `tools/commission.py` | 拆出 `put_to_work`；`commission_story` 新增 `format` 參數，預設依標記決定 |
| `agents/editor_in_chief.py` | 新提示詞（仍以公司使命判斷讀者）；候選依研究價值排序並附標記；追蹤股票清單 |
| `agents/researcher.py` | 格式說明、兩個新工具；策略研究以回測為紀錄，一個來源就夠；新 validator `computed_record_included` |
| `agents/analyst.py` | `AnalysisNote` 新增多方、空方、風險、推論、資料缺口欄位；新 validator `research_sides` |
| `agents/writer.py` | 寫稿說明加上格式大綱、多空與風險論點、推論、資料缺口 |
| `tools/drafts.py` | `write_draft` 對研究格式檢查段落與不給當下訊號 |
| `policy.py` | 四個新動作的權限；`research` 分類時效 720 小時、`strategy` 2160 小時 |
| `sources.py`、`routers/public.py`、前端 `i18n.ts` | 新分類 `research`、`strategy`；分頁放在「AI 科技」之後 |

### 刻意沒做的事

- 沒改 `workflow.py`、`agents/editor.py`、`tools/review.py`、`simulation.py`：d254 worktree（D-254 簡化審稿）在這幾個檔案有尚未提交的改動，合併時兩邊都要重跑測試。
- 沒有新增遷移：d255 worktree 已經先佔用 0084。
- 文章與個股的關聯表（待辦 D6）要等遷移編號整理後再做。

### 遇到的問題

- 依專案記憶，工作要在自己的 worktree 進行。但我先用 `cd` 進 d255 查看，工作階段的工作目錄就被切到了別人的 worktree。後來改用 `EnterWorktree` 開了自己的 `research-r1`，沒有在 d255 改任何東西。
- 總編的提示詞一開始寫死「你的讀者投資台美股」。但示範用的流明市新聞室也共用這份提示詞，既有測試因此擋下。改回以公司使命判斷讀者，研究價值的說明放在後面。
- 追蹤股票清單一開始用 JSON 欄位做 `GROUP BY`。Postgres 把 select 與 group by 裡的鍵各綁成一個參數，判定兩者不是同一個運算式而拒絕執行。改成取出資料後在 Python 裡取最新日期。
- 英文事件詞原本用子字串比對，`order` 會比對到 `border`、`ban` 會比對到 `bank`。改成從字首比對，並把 `ban` 換成 `export ban`、`fine` 換成 `fined`。

### 驗證

- 新測試：
  - `tests/newsroom/test_research_desk.py`：15 項，純函式；回測用的是測試專用的合成數列。
  - `tests/newsroom/test_research_tools.py`：10 項，使用資料庫。
- 既有測試裡，以下幾處原本寫死工具清單、分類清單或分頁清單，依這次的改動更新：
  - `test_editor_in_chief.py`
  - `agents/test_research.py`
  - `test_markets.py`
  - `runtime/policy/test_policy.py`（權限矩陣）
  - 前端 `redesign.test.tsx`
- 後端（依目錄分開跑，自己的資料庫 `autora_r256`）：

  | 目錄 | 結果 |
  |---|---|
  | `newsroom` | 650 通過 |
  | `api` | 361 通過 |
  | `e2e` | 8 通過 |
  | `runtime` | 939 通過 |
  | 其餘目錄 | 692 通過 |

- 靜態檢查：`ruff check`、`ruff format --check`、`lint-imports` 全過。
- 前端：`tsc --noEmit`、`eslint`、`vitest` 1049 項、`gen-api:check` 全過；OpenAPI 已重新產生。
- 瀏覽器預覽：在 worktree 本機的 3005 埠，用這個分支的前端接正式 API。首頁分頁依序為：全部、AI 科技、個股研究、策略研究、台股…
  - 點「個股研究」時，正式環境的舊 API 回 422，因為它還不認得這個分類。這是部署順序的風險，已記在 `03_RESEARCH_DESK.md` §4.4。
  - 預覽伺服器自動改了 `tsconfig.json`，已還原。

## 2026-10-21：R-07 推送與部署

### 先後端、後前端

本機預覽時，新前端打舊 API 會得到 422。為了避免新分頁比 API 先上線，把原本的提交拆成兩個，分兩次推送：

1. **`bda83c1`（後端與 API 型別）**
   - 只有這個提交時，前端不含新分頁；`tsc`、站台與新聞室的 `vitest`（265 項）、`gen-api:check` 都通過。
   - 推送後 CI 39573383930 的 python、web、e2e 全部通過。
   - Render 在 17:05 部署 api 與 worker，部署狀態都是 success（17:06、17:07）。
   - Vercel 在 16:59 已先部署這個提交；因為它不含新分頁，不受影響。
2. **確認 API 已上線**
   - `GET /api/public/articles?lang=zh-TW&section=research` 回 200（空清單）。
   - 不存在的分類仍回 422。
   - 第一次寫的檢查漏了 `lang` 參數，所以等了 20 分鐘都是 422。那個 422 是缺參數造成的，不是分類的問題；補上參數後才是有效的檢查。
3. **`29453d8`（分頁）**：Vercel 在 17:28 部署成功。

兩個提交加起來，和原本驗證過的 `506f9e4` 內容完全相同（`git diff` 為空）。

### 正式環境檢查（17:30）

- **網站**：
  - www.aisiwhale.com 的分頁依序為：全部、AI 科技、個股研究、策略研究、台股…
  - 「個股研究」「策略研究」都正常顯示「還沒有報導。」，沒有錯誤頁。
  - 首頁仍列出 15 篇文章。
- **排程**：部署後照常執行（17:25–17:27 的 `cluster_stories`、`fill_prices`、`poll_sources`、`refresh_prices` 等），連續失敗次數都是 0。
- **總編選題**：今天的選題（cycle 30）在 15:11 用舊程式跑完，委派 3 篇。用新程式的第一輪選題是 10/22 上班後（約 15:10）。今天已委派的題材沒有 `seed.format`，會照一般新聞處理。

### 發現：寫手從 10/18 起被自動暫停（與 D-256 無關）

- **發生了什麼**：10/18 18:11–18:14，緯創背書保證那篇的第 2 輪修改，寫手連續 3 次 `MaxStepsExceeded`（8 次模型呼叫都沒有最終答案）。20:30 系統以「3 runs in a row failed」**暫停整個寫手**（`AGENT_PAUSED`，由系統觸發）。
- **影響**：之後總編每天照常委派 3 篇，但撰稿任務一直停在 READY。目前有 6 篇在等（10/20、10/21 各 3 篇），10/18 之後只發布了 2 篇。今天模型花費只有 US$0.066。
- **待使用者處理**：要在後台恢復寫手（`resume_agent` 只有人能做）。恢復後，這 6 篇會開始撰稿。
- **建議後續修正**：
  - 單一題材失敗不應暫停整個職位；
  - 寫手 `max_steps`（8）對研究格式可能不夠，D-256 新增的檢查會讓修正次數變多。

## 提交紀錄

| 提交 | 內容 | CI |
|---|---|---|
| `bda83c1` | D-256 研究台第一階段（後端、API 型別、文件） | 39573383930 ✅（python、web、e2e）；Render 17:05 部署 |
| `29453d8` | D-256 網站「個股研究」「策略研究」分頁 | 39577116292 ✅（python、web、e2e）；Vercel 17:28 部署 |
