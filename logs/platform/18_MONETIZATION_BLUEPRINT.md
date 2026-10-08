# 18 會員、鯨幣與 AI Office 架構藍圖（Monetization Blueprint v1.2）

2026-10-06 定稿（D-218～D-229）。本文件是 **架構與產品藍圖**，不是實作：寫入時沒有改任何程式、schema、API、前端或 PayUni。
後續每個 Phase 開工前，仍要由使用者另行派工。上層約束是 §1 的十二項決定；實作若和它們衝突，先停下來問，不自行改。

來源：v1.0（現況盤點＋完整藍圖）→ v1.1（五項前提）→ 使用者拍板十項 → v1.2（本文件）→ 補充決定 A、C。

> **之後的決定（以這兩條為準，本文其餘段落保留 v1.2 原文）**
> - **D-231（價格）**：D-218 的「VIP NT$149／月」**暫緩**。正式目錄維持 D-161：月繳 NT$30、年繳 NT$300（即將開放），因為 PayUni 申請與審核的就是這兩個價格。本文所有寫 NT$149 的地方（§1、§3、§17、§18 的 P2 與 P8、§19 R-15、§21），在 D-231 之下都讀作「目錄價格，目前是 NT$30／NT$300」。日後若真的改成 NT$149：先完成 PayUni 申請變更與審核，再以一筆新的決策改目錄，最後由 P8 開放付款。D-161、D-218 本身都不修改。
> - **D-232（P8 前置條件）**：comp 在 T 被撤銷時，期間內買的付費權益從 T 開始、給完整的購買期間；撤銷 comp 不得縮短付費權益，也不得把 comp 剩下的期間算進付費期間。Payment／Order 保持不可變；有效 VIP 改由各筆 grant（paid、comp）的區間計算。**這是 P8 第一階段的工作，必須在重新開放 PayUni 與結帳之前完成**（見 §18 的 P8）。

---

## 1. 已拍板的上層約束

| 決策 | 內容 |
|---|---|
| D-218 VIP 定價 | FREE：NT$0、每月 50 鯨幣、錢包上限 100。VIP：**NT$149／月**、每月 500 鯨幣、錢包上限 1,000。**先不改 PayUni 商品與正式付款**，先跑通「會員 → 鯨幣 → 功能消費」 |
| D-219 VIP 降級 | 到期降為 FREE：不追扣、保留餘額、只停 VIP 額度；之後 FREE 發放仍受 FREE 上限（餘額 850 → 發放 0） |
| D-220 退款不受上限 | 退款完整恢復原消費；上限只限制每月發放、活動發放等發放型入帳；Admin 調整超上限須明確執行並留 ledger |
| D-221 原創 IP | 正式角色 100% 原創；repo 與公開 Demo 的第三方角色只是 prototype；公開 Demo 換角色是**獨立小任務**，不和 Gacha 綁；EmployeeTemplate 只預留 IP metadata，不做完整 IP 管理 |
| D-222 FREE 發放資格 | MVP：當月至少一次有效登入才發 FREE 額度；做成可設定的 eligibility rule，**Coin Core 不認識「登入」** |
| D-223 鯨幣不是貨幣 | 只由平台發放；不販售、不轉讓、不交易、不提領、不兌現；是 platform usage resource |
| D-224 不把 AI 成本寫進鯨幣帳務 | `COIN_COST_BASIS_TWD` 只做營運分析；Coin Core 只處理 grant／spend／refund／adjustment／balance／ledger／idempotency／cap；各功能 coin cost 獨立設定 |
| D-225 研究分 P6a／P6b | P6a 研究任務基礎設施只給 Admin 與內部測試；P6b 對使用者開放須等律師確認；之前 `research.allowed_types = []` |
| D-226 MVP 不做 Creator Economy | 「委託 → 發布 → 閱讀量 → 回饋鯨幣」列 Future |
| D-227 付款與購幣延後 | 不做鯨幣購買、Coin Store、Stripe／PayUni 購幣；Buy Me a Coffee 與會員、鯨幣完全分離 |
| D-228 Admin 授予 VIP | `source = admin_comp`，必記 reason、actor、access_until；不建 order／payment；Entitlement 只看有效會籍期間，不因來源不同而不同 |
| D-229 MVP 指標 | 以鯨幣消費比例驗證，不以「500 幣花完」為成功標準；不為增加消費場景而讓律師先答 R1 |

**錢流方向（D-223）**：`Real Money → VIP → Monthly Grant → Platform Features`，不是 `Real Money → Coin → Cash／Reward`。

**VIP 價格與既有決策的關係（避免把 NT$30 誤認為現行規格）**：

| 項目 | 說明 |
|---|---|
| D-161 | 舊有的 VIP NT$30／PayUni 定價決策，**保留為歷史紀錄，不刪、不改、不重用編號** |
| D-218 | 新的會員與鯨幣架構的定價決策：VIP **NT$149／月**；在新架構中取代 D-161 |
| NT$30 | 舊有／目前程式裡的狀態（`seed_membership.py`、定價頁、PayUni 商品） |
| NT$149 | 新架構的目標價格；P8 之前不改 PayUni 商品 |
| P2 | 在**後端**關閉現有 NT$30 結帳路徑（`membership_open` 閘門） |
| P8 | 才重新開放 NT$149 實際收款 |
| P8 之前 | 以 Admin 授予（`source = admin_comp`，D-228）取得 VIP |
| **D-231（之後）** | NT$149 暫緩；目錄維持 D-161 的月繳 NT$30、年繳 NT$300。上面寫 NT$149 的兩列，目前讀作「目錄價格」 |

---

## 2. 產品定位

**矽鯨 AI 情報局＝一間你看得到、借得到、收藏得到的 AI 情報辦公室。**

| 層次 | 使用者得到什麼 | 現況 |
|---|---|---|
| 閱讀 | AI 產出的投資與科技情報（13F 持股、台美股、AI 產業） | ✅ 新聞室 |
| 觀看 | AI 員工工作（3D Office、團隊聊天） | ⚠️ 公開 Office 是腳本 Demo（D-155）；真實即時串流只給 operator |
| 使用 | Watchlist、特殊文章、（未來）委託研究 | ⚠️ 只有 Watchlist |
| 擁有 | 自己的 Office、員工收藏 | ❌ |

原則：
- **內容可信度優先**；擁有、抽卡是加值，不可碰內容正確性與法律界線。
- **公司 Runtime 是唯一的工廠**：使用者不會得到自己的 AI 公司，而是在平台公司上的 Job、View 與收藏。

---

## 3. 現況架構與建議架構的差異

| 主題 | 現況（2026-10-06） | 建議 | 原因 |
|---|---|---|---|
| 身分 | `readers.email` 唯一、小寫；只有 magic link；無頻率限制 | 加 `reader_identities(provider, subject)`；Google 以 `sub` 為鍵；只在 `email_verified` 時依 email 自動綁定 | 加 OAuth 不產生重複使用者 |
| 權限 | 只有 reader／operator 兩級；VIP 判斷散在 `site.lock_for`、`public.py`、前端 `isMember()`；`SITE_MEMBERSHIP_OPEN` **只在前端** | 後端單一 `can(viewer, capability)`，`/api/me` 回 capability 清單，前端只顯示 | 權限不散落前端 |
| 會籍 | 只能由 payment 產生；月付 NT$30（D-161）；狀態 ACTIVE／EXPIRED，依日期判斷 | VIP＝現有 membership 產品；新增 `source`（payment／admin_comp）；價格 NT$149（D-218，暫不改 PayUni） | D-218、D-228 |
| 付款 | PayUni 一次性付款；`payments` 只增不改；多層冪等 | 保留；加 `payment_events`；修四個既有 bug（§13） | 稽核與重放 |
| 鯨幣 | 不存在；`company/ledger.py` 是公司的真錢帳 | 新的 reader 側 Wallet domain，**與公司 `transactions` 分帳** | 兩種東西不能混 |
| 文章存取 | `articles.access ∈ {free, members}` + `SIGN_IN_SECTIONS`；伺服器只送節錄 | 加 `coin`、`coin_price`、`article_unlocks` | 防重複付費 |
| Office | `companies` 就是 Office（租戶根）；只有 cycle 能啟動 LLM；每個 agent 同時只能一個 run；有班表；全域每日上限 3 美元 | 使用者 Office 不是 company；平台公司加「委託席」部門（獨立 agents 與預算）；新增「確認的 Job」為第二個 LLM 啟動來源 | 不讓使用者任務與新聞室互相搶資源 |
| 成本 | `model_calls` 精確到 run／task／workflow_run；Tavily 等工具成本**只在事件上**，不預留不設上限；`per_day_usd` 沒人讀 | 工具成本計量；`CallContext.job_id`；委託席獨立預算 | 付費任務前必須先能算成本 |
| Watchlist | 每位讀者一份、50 檔、在 DB；D-060：agents 不能讀 | 保留；未來「每天研究我的 Watchlist」由 Commission 側把代號複製進 job input，agents 仍不讀 Watchlist | 守住個資隔離牆 |
| 隔離牆 | import-linter 禁止 company／runtime／agents import `autora.accounts`；公司只看到 `reader:<id>` | **所有新設計都保留這道牆**；跨越只用 opaque ref 與 outbox event | 個資不進 agent |

---

## 4. Domain 邊界

```
┌──────────── Reader 側（有個資；company／runtime／agents 不得 import）──────────────┐
│ Identity        readers, reader_identities, reader_sessions, login_tokens           │
│ Entitlement     （服務，不建表）Viewer + can()                                     │
│ Wallet          coin_accounts, coin_txns, coin_entries, coin_wallets                │
│ Grant           （服務）GrantPolicy + EligibilityRule                              │
│ Content Access  article_unlocks                                                     │
│ Commission      research_requests                                                   │
│ Collection      employee_templates, gacha_pools, gacha_draws, user_employees        │
│ Office（view）  offices, office_assignments                                         │
│ Watchlist       watchlist_items（現有）                                             │
└──────────────────────────── 只用 opaque ref ＋ outbox event 跨越 ──────────────────┘
┌──────────── Company 側（無個資）─────────────────────────────────────────────────────┐
│ Commerce        prices, orders, payments, memberships, customers（現有）+ payment_events│
│ Newsroom        articles（access + coin_price）                                     │
│ Runtime         companies, roles, agents, workflow_runs, tasks, agent_runs, model_calls│
│ Jobs            jobs（commission_ref, research_type, cost_cap, state）               │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Final Domain Model

### 5.1 Employee、Role、Agent、Task、Job、Execution

| 概念 | 現況對應 | 定案 |
|---|---|---|
| Office（平台） | `companies` | 保留 |
| Office（使用者） | 無 | `offices`：view＋偏好容器，**不在執行路徑上** |
| Role | `roles` + `key` | 保留 |
| Agent capability | 程式裡的 `AgentBehavior(role, task_name)` + tools + model_policy | 保留；Capability＝Role × Behavior × Tools |
| Employee（平台） | `agents` 一列：persona（Ada、Rei、Mari…）＋執行身分＋預算 | **`agents` 就是平台員工**，不另建 Agent 表 |
| Employee（使用者收藏） | 無 | `employee_templates` + `user_employees`，**與 `agents` 完全解耦** |
| Task / Execution | `tasks` / `agent_runs` + `agent_steps` | 保留 |
| Job | 無（最近的是沒有客戶的 `workflow_runs`） | 新增 `jobs`，與 workflow_run 一對一 |

執行鏈：

```
User ─► ResearchRequest（reader 側）─► Job（company 側）─► WorkflowRun ─► Task ─► AgentRun ─► Result
  │                                                                  ▲
  └─► Office（view／偏好）─► UserEmployee（展示、preset）─────────────┘ 只傳 preset_key，不驅動執行
```

收藏的員工只影響**展示與輸出格式的 preset**（語氣、報告模板、3D 造型），**不得影響預算、模型或內容正確性**。
一位使用者可以有多個 Office（`offices.reader_id` 不唯一、`is_default` 標記一個），MVP 只做 default。

### 5.2 Entity 清單

| Entity | 狀態 | Phase | 關鍵欄位與約束 |
|---|---|---|---|
| readers | 現有 | — | email 唯一、小寫 |
| reader_identities | 新增 | P1 | (provider, subject) 唯一；email_at_link；verified_at |
| memberships | 小改 | P2 | 加 `source`（payment／admin_comp）、reason、actor；admin_comp 不需 payment |
| payment_events | 新增 | P2 | 付款通知原始紀錄；(provider, trade_no, status) 唯一 |
| coin_accounts | 新增 | P3 | owner_type（reader／system）；system：ISSUANCE、BURN、ESCROW、ADJUSTMENT |
| coin_txns | 新增 | P3 | kind、`idempotency_key` 唯一、ref_type／ref_id、actor、`reverses_txn_id` 唯一、meta |
| coin_entries | 新增 | P3 | txn_id、account_id、amount（帶正負號整數）；只增不改；每筆 txn 加總為 0 |
| coin_wallets | 新增 | P3 | reader_id 主鍵、balance 快取（`CHECK ≥ 0`），可由 entries 重算 |
| articles.access（+`coin`）、coin_price | 小改 | P4 | 沿用 `may_read`／`preview` |
| article_unlocks | 新增 | P4 | (reader_id, article_id) 唯一、coin_txn_id、price_paid |
| offices | 新增 | P5 | reader_id、kind、is_default、theme、settings |
| model_calls.job_id、CallContext.job_id、工具成本 | 小改 | P5 | 每個 job 的成本可加總 |
| jobs | 新增 | P6a | commission_ref（opaque）、research_type、state、cost_cap_usd、cost_actual_usd、workflow_run_id |
| research_requests | 新增 | P6a | reader_id、request_id 唯一、prompt、research_type、coin_cost、hold_txn_id、job_ref、state |
| employee_templates | 新增 | P7 | key、name、role_affinity、rarity、asset_key、preset_key、ip_origin、license_type、license_reference、commercial_use_allowed、status（ACTIVE／DRAFT／RETIRED） |
| gacha_pools／gacha_draws／user_employees／office_assignments | 新增 | P7 | draw 只增不改並記 pool_version；(reader, template) 唯一並記 copies |

**不需要獨立 Entity**：ArticleAccess（是 `articles.access` 欄位）、ResearchResult（沿用 `documents` 或 private article）、Watchlist 父表（目前一人一份就夠）。
**延後**：subscriptions、coin_lots、REWARD_POOL、多 Office、Office 等級。

### 5.3 設定（集中，不散落在商業邏輯）

```
COIN_GRANT:
  FREE_MONTHLY_COIN_GRANT = 50      FREE_WALLET_CAP = 100
  VIP_MONTHLY_COIN_GRANT  = 500     VIP_WALLET_CAP  = 1000
  MONTHLY_GRANT_ELIGIBILITY = { free: "signed_in_this_month", vip: "always" }
FEATURE_COIN_COST:              # 功能標價，與 AI 成本沒有程式依賴（D-224）
  article_default = 5（文章可用 coin_price 覆寫）
  research_standard = 50   research_deep = 150   gacha_single = 100
RESEARCH:
  allowed_types = []            # 律師確認前為空（D-225）
  internal_only = true
```

- 每筆發放與消費都把當下套用的參數寫進 `coin_txns.meta`，之後改數字仍可追溯。
- `COIN_COST_BASIS_TWD` 只出現在營運報表，Wallet／Ledger 不讀它。
- 以上數字是 MVP 暫定值，調整時另記一筆 D 決策，不改資料模型。

---

## 6. 權限模型

只由後端 `can(viewer, capability)` 判斷；`Viewer = { reader_id?, tier: PUBLIC | FREE | VIP, is_admin, vip_until }`。

| Capability | PUBLIC | FREE | VIP | ADMIN |
|---|---|---|---|---|
| 免費文章、市場資訊 | ✅ | ✅ | ✅ | ✅ |
| 持股、名人區完整內容 | ❌ | ✅ | ✅ | ✅ |
| VIP 文章 | ❌ | ❌ | ✅ | ✅（預覽） |
| COIN 文章 | ❌ | 用幣 | 用幣 | ✅ |
| Watchlist | ❌ | ✅ 50 檔 | ✅ | — |
| Office | 腳本 Demo | Demo＋摘要 | 完整即時同步（去敏） | 後台全貌 |
| 每月鯨幣 | — | 50／上限 100（需資格） | 500／上限 1,000 | — |
| 抽卡、收藏 | ❌ | ❌ | ✅（P7） | — |
| 研究任務 | ❌ | ❌ | **❌（P6b 前）** | ✅ 內部測試（P6a） |
| 結帳 | ❌ | 後端 `membership_open = false` 時擋下 | 同左 | — |
| 授予 VIP、調整鯨幣、設定 COIN 文章 | ❌ | ❌ | ❌ | ✅（皆留紀錄） |

Admin 沿用 `ADMIN_EMAILS` ＋ magic link（或 Google）；不提供只靠密碼的管理員登入。

---

## 7. 身分模型

```
readers            一人一列；email＝已驗證的主要信箱
reader_identities  (reader_id, provider: email_link | google | password, subject, email_at_link, verified_at)
                   UNIQUE(provider, subject)
reader_credentials (reader_id, password_hash)   ← 只有開放密碼登入時才建（延後）
```

綁定規則：
1. Google 登入先找 (google, sub)，找到就登入。
2. 找不到且 `email_verified = true` → 用小寫 email 找 reader → 自動綁定。
3. 都找不到 → 新建 reader 與 identity。
4. 密碼註冊（延後）必須先驗證 email；未驗證不得綁到既有帳號。
5. 以 Google `sub` 為鍵，換 Gmail 不影響。
6. Gmail 的點與加號不做正規化（只轉小寫），避免誤合併。

同時補上 magic link 與登入的頻率限制。

---

## 8. 鯨幣經濟

### 8.1 帳務模型（雙分錄，不是一個 `user.coins` 欄位）

| kind | 從 → 到 | 受上限 | 冪等鍵 |
|---|---|---|---|
| MONTHLY_GRANT | ISSUANCE → reader | ✅ | `grant:{tier}:{reader}:{YYYY-MM}` |
| PROMOTION_GRANT | ISSUANCE → reader | ✅ | `promo:{campaign}:{reader}` |
| ADMIN_ADJUSTMENT | ADJUSTMENT ↔ reader | ✅（可明確 override） | `adj:{request_id}` |
| SPEND | reader → BURN | — | `spend:article:{reader}:{article}`（D-249）／`gacha:{request_id}` |
| HOLD／CAPTURE／RELEASE | reader ↔ ESCROW → BURN | — | `job:{request_id}:hold｜capture｜release` |
| REFUND | BURN → reader（帶 `reverses_txn_id`） | ❌ | `refund:{original_txn_id}` |
| ~~PURCHASE／TRANSFER／WITHDRAW~~ | **不定義**（D-223、D-227） | | |

```
 ISSUANCE ── MONTHLY_GRANT／PROMOTION_GRANT（受上限）──► Reader Wallet
 ADJUSTMENT ◄──── ADMIN_ADJUSTMENT（±，超上限要 override）────► Reader Wallet
 Reader ── SPEND ─────────► BURN                （COIN 文章、抽卡）
 Reader ── HOLD ──► ESCROW ── CAPTURE ──► BURN  （研究任務）
                      └── RELEASE ──► Reader    （不受上限）
 BURN ── REFUND（反轉原 SPEND）──► Reader       （不受上限）
```

### 8.2 規則

- **發放公式**：`grant = min(MONTHLY_GRANT[tier], max(0, WALLET_CAP[tier] − balance))`。
- **降級**（D-219）：保留餘額；之後依 FREE 規則，餘額 ≥ 100 時發放 0。
- **退款**（D-220）：完整恢復，不受上限；同一筆 txn 只能被反轉一次；退款金額不超過原消費。
- **Admin 調整**：預設受上限；超上限須 `override_cap = true` 並寫進 meta；扣款不得使餘額 < 0。
- **發放觸發（延遲發放）**：讀者當月第一次有身分驗證的請求時，由 Grant 服務依 `MONTHLY_GRANT_ELIGIBILITY[tier]` 判斷資格後呼叫 `Wallet.grant`。VIP 若要不登入也到帳，可另加每月 1 日的排程，共用同一個冪等鍵。
- **月中升級**：VIP 的冪等鍵和 FREE 不同，所以當月可再收一次 VIP 額度，仍受 VIP 上限。
- **tier 判斷**：以發放當下 Entitlement 的有效會籍期間為準，不看會籍來源（D-228）。

### 8.3 不變式與防護

- **對帳等式**（每日檢查）：`Σ ISSUANCE + Σ ADJUSTMENT + Σ readers + Σ ESCROW + Σ BURN = 0`；`coin_wallets.balance` ＝ 該讀者 entries 加總。
- **防重複扣款**：`idempotency_key` 唯一；前端每個動作產生 request_id，重試時沿用。
- **防並發**：同一交易內 `SELECT … FROM coin_wallets WHERE reader_id = ? FOR UPDATE` → 檢查 → 寫 entries → 更新快取；`CHECK (balance >= 0)`。沿用 `task_manager` 與 `CostGuard` 的鎖定方式。
- **防無限增殖**：只有白名單 kind 能從 ISSUANCE 出帳；發放有上限；不可轉讓與兌現；ledger 只增不改（比照 `payments` 的 `autora_forbid_mutation` trigger）。
- **與公司帳分開**：公司 `transactions`（真錢、TWD）與鯨幣 ledger 永不混帳。

### 8.4 為未來保留的擴充

- **購幣**（目前不做）：新增 `coin_lots`（依來源分批、花費順序、退款回原批次），再用一次 migration 把現有餘額轉成一批「既有發放」。核心 ledger 不需要改。
- **到期**：目前以上限取代到期；需要時再隨 lots 一起加。
- **回饋**（D-226 延後）：屆時回饋只能來自其他讀者已花掉的幣（轉帳），不得新鑄幣。

---

## 9. AI Office 架構

1. **使用者的 Office 不是 company**：company 帶有 cycle、預算、ledger、CEO 與 worker，每位 VIP 一間會讓成本與複雜度失控。使用者 Office＝(a) 平台 Office 的去敏即時 view、(b) 自己 job 的進度、(c) 自己擺放的員工（展示）。
2. **平台公司加「委託席」部門**：同樣的 role key、另一組 `agents` 列與 project 預算。讓使用者任務與每日新聞室不互搶「每個 agent 同時一個 run」的名額，也不互搶每日成本上限。
3. **第二個 LLM 啟動來源**：cycle 之外，新增「已確認的 Job」，仍須通過 PolicyEngine 與 CostGuard。
4. **班表與交付時間**：worker 只在班表時段工作（平日 15:00–21:00），交付時間要寫成「下一個班次內」；要加班時沿用 `worker_overtime` 上限。
5. **VIP 即時同步**：新增公開唯讀 projection，欄位白名單（員工動作、任務標題、自己的 job 進度）；**不含**成本、prompt、審批意見、他人的 job；用獨立頻道，不開放 operator WebSocket 給讀者。

---

## 10. 文章存取

- `articles.access ∈ { free, members(VIP), coin }` ＋ `coin_price`（1～100，預設 5）；`SIGN_IN_SECTIONS`（holdings、figures、institutions）維持區塊規則，但設成 COIN 的文章要付幣（COIN 優先，D-249）。
- 解鎖（同一交易）：若 `article_unlocks` 已有就直接回成功、不扣款 → 鎖錢包、寫 SPEND（`spend:article:{reader}:{article}`；帳務規定 SPEND 的鍵以 `spend:` 開頭，原寫的 `unlock:` 不合，D-249 更正）→ 寫 unlock。冪等鍵與唯一索引是最後防線。
- COIN 文章對所有人都要用幣（不因 VIP 自動解鎖）；改價不影響已解鎖者；解鎖後永久可讀。
- MVP 只有 Admin 能設定 COIN 與價格（AI 總編可設 VIP 的現行規則不變；總編終審不改動 COIN 文章）。
- 下架不自動退幣；改價或改回免費，已解鎖者照樣可讀。
- **P4 已實作（D-249，遷移 0082）**：`POST /api/me/unlocks/{article_id}`（201 解鎖、200 已解鎖不扣款、402 餘額不足附 `need`／`held`）、`GET /api/me/unlocks`；錢包明細的文章消費附標題與網址；後台閱讀權限三選一。

---

## 11. 員工與抽卡（P7）

- Template 與擁有分開：`employee_templates`（含 IP metadata 與 status）↔ `user_employees`。
- 只有 `status = ACTIVE` 且 `commercial_use_allowed = true` 的模板能進卡池。
- 重複：`copies + 1` 轉為等級或碎片，**不退鯨幣**。
- 機率公開、版本化，每次抽卡記 `pool_version`；保底由伺服器判斷；RNG 在伺服器端並留紀錄。
- 員工能力只限展示與輸出格式 preset，與執行系統解耦。

---

## 12. 研究任務（P6a／P6b）

> P6a 的後台研究工作頁照 `logs/admin/02_NEW_ADMIN_PAGE.md` 做（AD-14）；看研究用 `research:view`、啟動研究用 `research:run`，都只有 owner（D-251）。

### 12.1 LEGAL REVIEW REQUIRED

本節**不是法律結論**，只把需要律師判斷的維度拆開，讓律師的回答能直接對應到系統設定。

| 維度 | 低 ←→ 高 |
|---|---|
| 研究對象 | 產業、技術主題 → 指名個別有價證券 |
| 輸出性質 | 事實與資料整理 → 正反論點並陳 → 帶結論的意見或建議 |
| 個人化 | 所有人看到同一份 → 依使用者 Watchlist 或持股客製 |
| 對價關係 | 免費 → 鯨幣（由 VIP 付費間接取得）→ 直接付費 |
| 散布範圍 | 只有委託人看得到 → 公開發布 |

| 代號 | 產品定位 | 例子 |
|---|---|---|
| R1 | 產業與技術研究 | 「CoWoS 產能與先進封裝供應鏈整理」 |
| R2 | 公開資料彙整 | 「台積電近 8 季財報與 13F 持有機構整理」 |
| R3 | 個股正反論點並陳、不下結論 | 等同現行 `newsroom.no_advice` 允許的寫法 |
| R4 | 依個人 Watchlist 每日自動研究 | 「每天早上研究我的 Watchlist」 |
| R5 | 個人化建議（目標價、買賣、配置） | **系統一律拒絕** |

### 12.2 架構如何承接律師結論

- `research_type` 為列舉；每個類型對應一個 workflow template、輸出格式與政策閘門。
- `research.allowed_types = []`（律師結論前不變）；`internal_only = true` 時只有 Admin／內部名單可用。
- 入口分類器判定 R5 就拒絕並退幣；所有輸出必經 `no_advice` 審稿。
- 輸出預設只有委託人可讀；公開發布是另一個開關（且受 D-226 限制）。

### 12.3 流程與狀態機

```
QUOTED → CONFIRMED(hold) → QUEUED → RUNNING → DELIVERED(capture)
                         ↘ CANCELLED(release)   ↘ FAILED(release)
```

1. 送出 → `can(research, type)` → 分類 → 依 `FEATURE_COIN_COST` 報價 → 使用者確認。
2. 同一交易：HOLD（reader → ESCROW）＋ `research_requests` CONFIRMED ＋ outbox `ResearchRequested`。
3. Company 側建立 job 與 workflow_run（只傳 topic、代號、預算、`commission_ref`）。
4. `research_commission_v1`：researcher → analyst → writer → editor（含 `no_advice`）→ deliver；委託席 agents 執行，model 與工具呼叫帶 job_id，CostGuard 以 `jobs.cost_cap` 為上限。
5. 成功：CAPTURE。失敗、政策拒絕、逾時（SLA，例如 48 小時）：RELEASE，**MVP 一律全額退幣**。

| 情境 | 處理 |
|---|---|
| 扣了幣但 job 沒建立 | 不會發生：預扣與 request 同交易，建立失敗就整筆回滾 |
| job 建立但一直沒開始 | 逾時 → FAILED → RELEASE |
| 執行到一半失敗 | runtime 先重試 3 次；仍失敗 → FAILED → 全額退 |
| 審稿以 `no_advice` 拒絕 | FAILED(policy) → 全額退，告知原因 |
| BLOCKED_BUDGET | 等下一個預算週期，逾時規則照樣適用 |

退款永遠是鯨幣，不退現金。

---

## 13. 付款架構

| 項目 | 資料 | 成功後 |
|---|---|---|
| VIP（P8 起） | orders → payments（現有）→ memberships | 會籍期間；之後發放由 Grant 服務處理 |
| VIP（MVP 內測） | 只有 memberships（`source = admin_comp`） | 同上（D-228） |
| 鯨幣購買 | **不做**（D-227） | — |
| Buy Me a Coffee | **系統外**，只放外部連結 | 無權益、無鯨幣 |
| payment_events | 每則付款通知的原始紀錄 | 稽核、重放 |

**P2 必須先處理的現有問題**（只修正與關閉，不改 PayUni 商品）：
1. 結帳與付款通知之間價格被退役 → `purchase()` 拋錯 → notify 回 500，已付款卻沒有會籍，PayUni 一直重送。
2. 已 PAID 的訂單又收到未付款通知 → `abandon` 拋錯 → 500。
3. 後端 `/api/checkout` 不檢查 `membership_open`，只要 PayUni 金鑰在就能以 NT$30 下單。
4. PENDING 訂單永遠不會變 EXPIRED。

> **處理狀態**：第 3 項在 P2-A 完成（結帳一律 403）；第 1、2、4 項與 `payment_events` 在 P2-B 完成——退役價格照既有訂單履約（退役只禁止新下單）、已付款訂單收到失敗通知時確認收到但不變更、PENDING 超過 24 小時由 worker 標為 EXPIRED，EXPIRED 之後收到合法付款仍正常履約。見 `logs/devlog/07_PHASE_7.md` 的 P2-B 一節。

---

## 14. 資料流

**A. Google 登入（P1）**：`/auth/google/start`（state＋PKCE）→ Google → callback → 驗 id_token → 依 §7 綁定 → 建 session、設 cookie → 發 `ReaderSignedIn` event。

**B. VIP 取得**：MVP 為 Admin 授予（admin_comp）；P8 起為付款 → payment_events → `purchase()`；兩者都發 `MembershipGranted`，之後流程只看會籍期間。

**C. 每月發放**：見 §8.2。

**D. COIN 文章（P4）**：讀 → `lock_for` = coin → 回節錄＋價格＋是否已解鎖；解鎖見 §10。

**E. 抽卡（P7）**：鎖錢包 → SPEND（`gacha:{request_id}`）→ 伺服器抽（機率＋保底，記 pool_version）→ `gacha_draws` → upsert `user_employees`，同一交易。

**F／G. 研究與 Office 執行（P6a）**：見 §12.3。

**H. VIP Office 同步（P5）**：events → 去敏 projection → 讀者頻道。

**I. Admin 調整**：ADJUSTMENT ↔ reader，附原因與 actor；超上限要 `override_cap`。

---

## 15. 錢流與 AI 成本

```
卡／ATM ──► PayUni（T+7 撥款；個人帳戶每月 20 萬上限）
        ──► notify ──► payment_events ──► payments（只增不改）──► transactions(REVENUE, TWD)
                                      └─► memberships（VIP 期間）
公司成本：model_calls（USD）＋ Tavily（USD，目前不入帳）＋ Render／Vercel／Neon／R2
        ──► transactions(EXPENSE, model_cost per cycle × project)
Buy Me a Coffee ──► 外部平台 ──► 經營者（系統帳外）
```

- **鯨幣價格不與 AI 成本 1:1 綁定**（D-224）：各功能 coin cost 是設定值；AI 實際成本另由 usage／cost tracking 分析。
- **營運上要監控的是**：VIP 營收 → AI 成本（LLM、Search、Image、Storage、Infrastructure）→ 毛利；再回頭調整每月額度與各功能 coin cost。
- **開放付費 AI 任務前必須補的成本缺口**：(a) 工具與搜尋成本沒有預留、上限與入帳；(b) `per_day_usd` 沒人讀；(c) business unit 預算沒有強制；(d) `model_calls` 沒有 job_id；(e) 全域每日 3 美元上限共用，委託席需要獨立預算。
- 每個 job 記 `cost_actual_usd`，與報價的鯨幣數並列，作為分析資料。

---

## 16. MVP 指標（D-229）

- `grant_users`、`spend_users`
- `granted_coins`、`spent_coins`
- coin utilization rate = spent ÷ granted
- monthly active coin users
- COIN 文章解鎖率
- 抽卡轉換率
- VIP → 鯨幣消費轉換率

不把「每月 500 幣花完」當成功標準。

---

## 17. MVP 邊界

| MVP 內 | MVP 外 |
|---|---|
| Google 登入與身分綁定 | Email＋密碼登入 |
| Entitlement 服務、後端擋結帳 | 開放 VIP 實際收款（P8；價格依 D-231，目前是 NT$30／NT$300） |
| Admin 授予 VIP（admin_comp） | 定期定額 |
| Coin Core：grant／spend／refund／adjustment／cap／對帳 | 購幣、Coin Store、轉讓、提領 |
| COIN 文章 | 使用者發布、Creator Economy |
| VIP Office 即時同步（去敏）、default office | 多 Office、Office 等級 |
| P6a 研究基礎設施（只給 Admin 與內部） | **P6b 一般會員研究（等律師）** |
| 公開 Demo 換掉 placeholder 角色（獨立小任務） | Employee Skill、限定池、季節活動 |
| （P7 抽卡視原創素材就緒，可算 MVP+） | |

---

## 18. 實作計畫（P0～P8）

| Phase | 依賴 | 範圍 | 資料庫 | 後端 | 前端 | 測試 | 風險 |
|---|---|---|---|---|---|---|---|
| **P0 文件化** | — | 本文件與 D-218～D-229；律師提問清單（§21） | — | — | — | 列出 diff | 編號衝突 |
| **P1 Authentication** | P0 | Google OAuth、身分綁定、magic link 與登入頻率限制 | `reader_identities`（回填既有 email_link） | OAuth start／callback、綁定規則、`ReaderSignedIn` | Google 按鈕、帳號頁顯示登入方式 | 綁定矩陣（先 Google／先 email／未驗證／換 email）、不產生重複使用者、CSRF | 重複使用者、帳號被接管 |
| **P2 Membership & Entitlement** | P1 | `can()`、`/api/me` capabilities、後端 `membership_open` 閘門、Admin 授予 VIP、`payment_events`、修 §13 四個問題、~~VIP 文案 NT$149~~（D-231：價格不改，維持 NT$30／NT$300） | memberships 加 source／reason／actor；`payment_events` | Entitlement 服務、授予 API、notify 修正 | 移除前端權限判斷、授予 VIP 後台 | 授予與到期、降級、notify 重放與並發、退役價格 | 動到正式付款路徑（只關閉與修正） |
| **P3 Whale Coin Core** | P2 | 帳戶、txn／entries、錢包快取、Grant＋Eligibility、上限、退款、調整、每日對帳 | `coin_accounts`／`coin_txns`／`coin_entries`／`coin_wallets`；只增不改 trigger | Wallet 服務（只有內部 API）、延遲發放 hook、後台調整 | 餘額與明細頁、後台調整頁 | **100 個並發消費、重複發放、上限邊界（849／850／1000）、退款超上限、降級保留、對帳等式** | 並發、錯誤鑄幣路徑 |
| **P4 Paid Content** | P3 | COIN 文章 | articles 加 `coin`、`coin_price`；`article_unlocks` | 解鎖交易、`lock_for` 擴充、admin 定價 | 解鎖按鈕、已解鎖標示 | 重複解鎖不扣款、餘額不足、改價 | 重複扣款 |
| **P5 AI Office** | P2（與 P3、P4 可並行） | 去敏 projection＋讀者頻道、`offices`、委託席部門與預算、工具成本計量、job_id、CostGuard 補 per_day | `offices`；budgets；`model_calls.job_id`；工具成本欄位 | projection、gateway 頻道、CostGuard | 依 tier 分層的 Office 頁 | 去敏（不得出現成本與 prompt）、成本計量 | 資料外洩、Neon 運算 |
| **P6a Research Infra** | P3、P5 | 請求、報價、預扣、job、交付、退款、分類器（R5 拒絕）、`allowed_types = []`、internal_only | `research_requests`、`jobs` | 第二 LLM 啟動來源、`research_commission_v1`、SLA 逾時、outbox 交接 | 只有後台與內測介面 | 失敗、逾時、政策拒絕全額退；成本對報價；一般 VIP 被擋 | 成本超支、誤對外開放 |
| **P6b Public Research** | P6a＋**律師結論** | 依結論設定 `allowed_types`、文案、輸出格式 | — | 設定值 | 讀者研究介面 | 每個開放類型的政策測試 | **LEGAL REVIEW REQUIRED** |
| **P7 Employee／Gacha** | P3＋原創素材 | 模板、卡池、抽卡、收藏、Office 擺放（只展示） | `employee_templates`（含 IP metadata）、`gacha_pools`／`gacha_draws`、`user_employees`、`office_assignments` | 抽卡交易、保底、機率版本、只抽 ACTIVE＋可商用模板 | 抽卡、公開機率、圖鑑 | 機率統計、保底、並發、重複 | 機率型商品規範（需法律確認）、IP |
| **P8 Payment（VIP 收款）** | P2＋法律與稅務確認＋**D-232** | **第一階段：D-232 的權益區間（paid grant 與 comp grant 各自計算，Payment／Order 不可變），完成前不得重開結帳**；之後打開 `membership_open`（價格依 D-231，改價須先改 PayUni 申請）；定期定額另決；Buy Me a Coffee 外部連結 | prices 新增一筆；（如需要）`subscriptions` | 修正後的 notify 流程 | 定價頁開放購買 | 正式環境小額實測 | 消保、稅務、個人帳戶額度 |
| **T-IP（獨立小任務）** | 無 | 公開 Demo 換掉或下架 placeholder 角色 | — | — | `public/` 素材、Demo 腳本 | 視覺檢查 | 已在公開站展示 |

**不能放在同一個 Phase**：
- P3 與任何購幣功能。
- P6a 與 P6b。
- P7 與 P6。
- T-IP 與 P7。
- P1 與密碼登入。
- P5 的去敏同步與 P7 的收藏。
- P2 與 P8 的實際收款。
- **工具成本計量（P5）完成前，不開任何付費 AI 任務。**

### 依賴圖

```
P0 ──► P1 ──► P2 ──┬──► P3 ──┬──► P4
                   │         ├──► P7 ◄── 原創素材就緒
                   │         └──┐
                   ├──► P5 ─────┴──► P6a ──► P6b ◄── 律師結論
                   └──► P8 ◄── 法律與稅務確認
T-IP（獨立，隨時可做）
```

關鍵路徑：P0 → P1 → P2 → P3 → P4（最小閉環）。

---

## 19. 風險清單

| ID | 風險 | 可能性／影響 | 緩解 | 階段 |
|---|---|---|---|---|
| R-01 | 研究功能觸及投顧相關法規 | 中／高 | P6a／P6b 分開、`allowed_types = []`、R5 拒絕、`no_advice` 審稿 | P6 |
| R-02 | 現有 NT$30 結帳只在前端擋 | 中／高 | 後端閘門 | P2 |
| R-03 | notify 在退役價格、已付款又收失敗通知時回 500 | 低／高 | 修正＋測試 | P2 |
| R-04 | 錢包並發或重複扣款 | 中／高 | 列鎖、唯一冪等鍵、CHECK | P3 |
| R-05 | 錯誤的鑄幣路徑造成通膨 | 低／高 | ISSUANCE 白名單、每日對帳 | P3 |
| R-06 | 退款被上限吃掉或重複退款 | 低／中 | 退款不受上限、reverses 唯一 | P3 |
| R-07 | MVP 能花幣的地方少 | 高／中 | 以消費比例為指標（D-229） | — |
| R-08 | 去敏同步外洩成本、prompt 或他人資料 | 中／高 | 欄位白名單 projection、獨立頻道 | P5 |
| R-09 | 研究成本超支或排擠新聞室每日額度 | 中／中 | 委託席獨立預算、job cost cap、工具成本計量 | P5、P6a |
| R-10 | 班表造成 job 交付慢 | 高／低 | 文案寫「下一個班次內」；必要時加班 | P6a |
| R-11 | placeholder 角色仍在公開站 | 已發生／中 | T-IP | 隨時 |
| R-12 | 大量 FREE 帳號領幣 | 中／低 | eligibility、不可轉讓、FREE 不能用研究 | P3 |
| R-13 | Google 帳號被綁到別人的帳號 | 低／高 | 只在 email_verified 時綁；以 sub 為鍵 | P1 |
| R-14 | 抽卡機率爭議 | 中／中 | 公開機率、版本、伺服器端 RNG 紀錄 | P7 |
| R-15 | 漲到 NT$149 後轉換率不明 | 高／中 | 先用 admin_comp 內測，再開收款 | P2→P8 |

---

## 20. 安全與防濫用

| 風險 | 緩解 |
|---|---|
| 偽造或重放 PayUni 通知 | 已有 HashInfo＋AES-GCM 驗證；`payment_events` 唯一防重放 |
| magic link 無頻率限制 | 依 IP 與 email 節流 |
| OAuth CSRF、帳號接管 | state＋PKCE；只在 email_verified 綁定；以 sub 為鍵 |
| Prompt injection（使用者請求操控 agent） | 請求只當資料；研究流程只開 search＋fetch；輸出必經審稿 |
| 個資流到 agent | 保留 import-linter 隔離牆；job 只拿 opaque ref |
| 研究任務洗量 | 每人每日 job 上限、同時 1～2 件、分類器拒絕不相關或違規請求 |
| 抽卡爭議 | 抽後不退（寫進條款）、公開機率 |
| Admin bearer 預設值 `change-me` | 正式環境已拒絕，維持 |

---

## 21. 需要法律確認的項目（不提供法律結論）

1. **自訂研究**：R1～R5 是否涉及《證券投資信託及顧問法》與相關管理規則；以鯨幣（由 VIP 付費間接取得）作為對價是否影響判斷；只給委託人與公開發布的差異；依 Watchlist 自動研究（R4）屬於哪一類。
2. **鯨幣**：只送不賣、無現金價值、不可轉讓時，是否仍受預付型商品、電子票證或點數相關規範；服務條款寫法（無現金價值、平台可調整、停止服務時的處理）。
3. **抽卡**：機率型商品的揭露義務與格式；用免費取得的幣抽卡是否仍適用。
4. **VIP NT$149 月費**：數位內容退費（現行 D-034：7 天內全額退）、定期定額的扣款告知與取消。
5. **Google OAuth**：隱私權政策需新增的內容（Google sub、姓名）。
6. **公開 Demo 的第三方角色**：已公開展示的處理方式。
7. **稅務**：VIP 收入、個人經營者（PayUni 個人帳戶）身分。

---

## 22. 明確延後的項目

| 項目 | 依據 |
|---|---|
| 鯨幣購買、Coin Store、Stripe／PayUni 購幣、`PURCHASE` kind、`coin_lots` | D-223、D-227 |
| 鯨幣轉讓、交易、提領、兌現 | D-223 |
| Creator Economy（發布 → 閱讀量 → 回饋）、REWARD_POOL | D-226 |
| 一般會員研究（P6b） | D-225 |
| 改 PayUni 商品、開放實際收款 | D-218 |
| 鯨幣到期 | 由上限取代 |
| 定期定額 subscriptions | P8 另決 |
| Email＋密碼登入 | — |
| 多 Office、Office 等級、成就、排行榜、Employee Skill、限定池、季節活動 | YAGNI |
| 完整 IP 管理系統 | D-221（只預留 metadata） |
| 依 Watchlist 每日自動研究 | 跟 P6b 與律師結論 |
| Crypto、ETF、AI 圖片、影片、Podcast | Future |
