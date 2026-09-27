// The public site's two languages (D-002: zh-TW first, then en) and its few words of UI.
export const LANGS = ["zh-TW", "en"] as const;
export type Lang = (typeof LANGS)[number];

export function isLang(value: string): value is Lang {
  return (LANGS as readonly string[]).includes(value);
}

export const LANG_NAMES: Record<Lang, string> = { "zh-TW": "中文", en: "English" };

const WORDS = {
  "zh-TW": {
    site: "艾矽鯨",
    tagline: "AI 科技投資動向",
    latest: "最新報導",
    empty: "還沒有報導。",
    sources: "資料來源",
    published: "發布於",
    revised: "更新於",
    allStories: "所有報導",
    all: "全部",
    sections: {
      holdings: "大戶持股",
      figures: "名人持股",
      ai: "AI 科技",
      tw: "台股",
      us: "美股",
      crypto: "加密貨幣",
      institutions: "機構觀點",
      gold: "黃金",
      commodities: "期貨",
      fx: "外匯",
    },
    sectionsLabel: "報導分類",
    topics: { watch: "持股觀察" } as Record<string, string>,
    tagsLabel: (topic: string) => `${topic}的分類`,
    pagination: {
      label: "分頁",
      first: "第一頁",
      previous: "上一頁",
      next: "下一頁",
      last: "最後一頁",
      page: (n: number) => `第 ${n} 頁`,
      counter: (n: number, total: number) => `第 ${n}／${total} 頁`,
    },
    page: (n: number) => `第 ${n} 頁`,
    newerStory: "較新一篇",
    olderStory: "較舊一篇",
    markets: "主要市場指標",
    quoteNames: {
      taiex: "加權指數",
      "tw:2330": "台積電",
      "tw:2317": "鴻海",
      "tw:2454": "聯發科",
      "tw:2382": "廣達",
      "tw:2308": "台達電",
      "tw:0050": "元大台灣50",
      "tw:006208": "富邦台50",
      "us:NVDA": "輝達",
      "us:AVGO": "博通",
      "us:TSM": "台積電 ADR",
      "us:AMD": "超微",
      "us:MU": "美光",
      "us:MSFT": "微軟",
      "us:GOOGL": "Alphabet",
      "us:AMZN": "亞馬遜",
      "us:META": "Meta",
      "us:AAPL": "蘋果",
      "us:TSLA": "特斯拉",
      "us:QQQ": "那斯達克100 ETF",
      "us:VOO": "標普500 ETF",
      nasdaq: "那斯達克",
      us10y: "美國10年期公債",
      wti: "西德州原油",
      btc: "比特幣",
      eth: "以太幣",
    } as Record<string, string>,
    basis: { close: "收盤", prev_close: "前一交易日收盤", last: "最新價", "24h": "24 小時漲跌" } as Record<
      string,
      string
    >,
    marketsNote: "收盤或延遲資料，僅供參考",
    marketsCredit: (sources: string[]) => `市場資料：${sources.join("、")}。收盤或延遲資料，僅供參考。`,
    sourceNames: {
      TWSE: "臺灣證券交易所",
      FRED: "FRED（聖路易聯邦準備銀行）",
      Finnhub: "Finnhub",
      CoinGecko: "CoinGecko",
    } as Record<
      string,
      string
    >,
    chart: {
      title: "走勢",
      intervals: { intraday: "15分", day: "日", week: "週", month: "月" },
      intradayNote: "15 分鐘線為美東時間，成交量僅含 IEX 交易所。",
      average: (view: string, n: number) =>
        (
          {
            day: { 5: "週線", 20: "月線", 60: "季線", 120: "半年線", 240: "年線" },
            week: { 4: "月線", 13: "季線", 26: "半年線", 52: "年線" },
            month: { 3: "季線", 6: "半年線", 12: "年線", 24: "兩年線", 60: "五年線" },
          } as Record<string, Record<number, string>>
        )[view]?.[n] ?? `MA${n}`,
      averageTitle: (view: string, n: number) =>
        `${n} ${({ intraday: "根 15 分鐘", day: "日", week: "週", month: "個月" } as Record<string, string>)[view]}均線`,
      ohlc: { o: "開", h: "高", l: "低", c: "收" },
      volume: "成交量",
      lots: "張",
      none: "還沒有這檔股票的歷史價格。",
      preparing: "正在向交易所取得這檔股票的歷史價格，通常幾分鐘內完成，稍後重新整理即可。",
      source: (source: string, adjusted: boolean) =>
        `資料：${source}${adjusted ? "，已還原分割與股利" : ""}。僅供參考，不構成投資建議。`,
    },
    stock: {
      day: { open: "開盤", high: "最高", low: "最低", previous_close: "前收" } as Record<string, string>,
      marketCap: "總市值",
      holders: "大戶持股（13F）",
      holdersNote: (period: string, before: string | null) =>
        `${period} 季底的 13F 申報${before ? `，對比 ${before}` : ""}。13F 只揭露美股多頭部位，申報期限是季底後 45 天。`,
      holdersNone: "我們追蹤的投資人最近一季的 13F 沒有這檔股票。",
      holdersUs: "台股沒有 13F 申報；這裡是它美國存託憑證（TSM）的持有人。",
      twNo13f: "13F 只涵蓋美國上市證券，這檔台股沒有大戶申報資料。",
      investor: "投資人",
      action: "本季動作",
      shares: "持股",
      value: "市值",
      weight: "占投資組合",
      filing: "申報",
      changes: {
        new: "新建倉",
        increased: "加碼",
        decreased: "減碼",
        unchanged: "不變",
        sold_out: "出清",
      } as Record<string, string>,
      options: { PUT: "賣權（看跌）", CALL: "買權（看漲）" } as Record<string, string>,
      underlying: "標的股數",
      was: (n: string) => `前季 ${n}`,
      trades: "名人交易",
      tradesNote:
        "來自美國總統（OGE 278-T）與國會議員（STOCK Act）依法申報的交易報告。金額只有申報的區間；報告由 AI 轉錄、經人工對照原件核准後才顯示。",
      owners: { SP: "配偶", JT: "共同持有", DC: "子女" } as Record<string, string>,
      option: "選擇權",
      tradesNone: "我們追蹤的名人最近的交易申報沒有這檔股票。",
      tradesElsewhere: "美國總統與國會議員依法申報的交易，艾矽鯨不自行整理；可在這些追蹤網站查詢：",
      trackers: [
        ["川普的交易（Open Cabinet）", "https://open-cabinet.org/officials/trump-donald-j"],
        ["佩洛西的交易（Capitol Trades）", "https://www.capitoltrades.com/politicians/P000197"],
      ] as [string, string][],
      kinds: { purchase: "買進", sale: "賣出", "partial sale": "部分賣出", exchange: "交換" } as Record<string, string>,
      over: (n: string) => `${n} 以上`,
      late: "逾 30 天才申報",
      report: "原始申報",
      coverage: "我們的相關報導",
      coverageNone: "還沒有提到這檔股票的報導。",
      coveragePast: "這一頁沒有報導了。",
      back: "← 回到報導",
      noQuote: "目前沒有報價。",
      notice: "股價為收盤或延遲資料，持股來自 SEC 13F 申報，僅供參考，不構成投資建議。",
      noticeNo13f: "股價為收盤或延遲資料，僅供參考，不構成投資建議。",
    },
    scrollLeft: "往左捲動",
    scrollRight: "往右捲動",
    listen: "朗讀",
    stopListening: "停止朗讀",
    print: "列印",
    toDark: "切換為深色模式",
    toLight: "切換為淺色模式",
    readIn: "閱讀其他語言：",
    notice: "本站報導由 AI 新聞室撰寫、事實查核，並經人核准後發布。內容整理自公開資料，僅供參考，不構成投資建議；投資有風險，請自行判斷。",
    membersOnly: "這篇報導是會員專屬",
    membersOnlyWhy: "成為會員，就能閱讀全部會員專屬報導。",
    membersOnlyAlready: "已經是會員？",
    planName: { month: "月繳", year: "年繳" },
    planTerm: { month: "月", year: "年" },
    planChoose: { month: "選擇月繳", year: "選擇年繳" },
    planSaving: (percent: number) => `比月繳省 ${percent}%`,
    planOnce: "單次付款，不會自動扣款。到期前再買一次，會從原本的到期日往後延長。",
    planAgree: ["付款即表示你同意", "與", "。"],
    pricing: "會員方案",
    pricingClosed: "目前所有報導都免費閱讀，付費會員尚未開放。",
    pricingIntro: "艾矽鯨的報導大部分免費。成為會員，就能閱讀所有標示為會員專屬的報導。",
    pricingIncludes: [
      "閱讀全部會員專屬報導，中文與英文版本都包含",
      "單次付款，不會自動扣款，也不需要取消",
      "提早續購不會損失天數：新的期間接在原到期日之後",
      "付款後 7 天內可申請全額退款",
    ],
    pricingPayment: "付款由統一金流（PAYUNi）以信用卡處理，本站不會取得或儲存你的卡號。",
    pricingSignIn: "購買前需要先用 email 登入，會員資格會綁定在這個帳號上。",
    updated: "最後更新",
    sep: "：",
    doneTitle: "付款結果",
    doneChecking: "正在確認付款…",
    doneOk: (date: string) => `付款完成，你的會員資格到 ${date}。`,
    doneWaiting: (email: string) =>
      `還沒收到付款確認。如果你已經付款，請等幾分鐘再重新整理這一頁；仍有問題請寫信到 ${email}。`,
    doneSignedOut: "請先登入，才能確認你的會員資格。",
    doneBack: "回到報導",
    aside: (text: string) => `（${text}）`,
    terms: "服務條款",
    privacy: "隱私權政策",
    refund: "退款政策",
    operator: "經營者",
    contact: "聯絡信箱",
    phone: "電話",
    membersSoon: "付款功能即將開放，屆時就能在這裡成為會員。",
    membersStarting: "前往付款…",
    membersFailed: "沒辦法開始付款，請稍後再試一次。",
    signIn: "登入",
    signOut: "登出",
    watch: {
      title: "我的觀察清單",
      edit: "編輯清單",
      done: "完成",
      editLink: "編輯",
      showSide: "觀察清單",
      hideSide: "收起清單",
      noChart: "指數、利率、原油與加密貨幣沒有個股走勢圖，這裡只顯示最新數字。",
      emptyBoard: "清單是空的。按「編輯清單」搜尋並加入股票。",
      sample: "觀察清單範例・登入後自訂",
      link: "觀察清單",
      add: "☆ 加入觀察",
      added: "★ 已觀察",
      remove: "移除",
      drag: (name: string) => `拖曳調整「${name}」的順序`,
      dnd: {
        instructions: "按空白鍵拿起，用上下方向鍵移動，再按空白鍵放下；按 Esc 取消。",
        start: (name: string) => `已拿起「${name}」。`,
        over: (name: string, place: number) => `「${name}」移到第 ${place} 位。`,
        end: (name: string, place: number) => `「${name}」放在第 ${place} 位。`,
        cancel: (name: string) => `已取消，「${name}」回到原位。`,
      },
      reorderHint: "按住左側 ⋮⋮ 拖曳調整順序；跑馬燈與個股頁側欄會照這個順序排列。",
      signInToWatch: "登入後就能建立自己的觀察清單，在個股間快速切換。",
      empty: "還沒有觀察的股票。搜尋任何台股或美股加入，或從熱門股票挑選。",
      more: "熱門股票",
      search: "搜尋台股或美股：代號、股票名稱",
      searchLabel: "搜尋股票",
      noResults: "找不到符合的股票。",
      view: "查看",
      addShort: "＋ 加入",
      kinds: { stock: "股票", etf: "ETF", adr: "ADR" } as Record<string, string>,
      failed: "觀察清單暫時讀不到。",
      note: "觀察清單只有你看得到；行情為收盤或延遲資料，僅供參考，不構成投資建議。",
    },
    signedInAs: "已登入",
    member: "會員",
    memberUntil: "會員資格到期日",
    becomeMember: "成為會員",
    loginTitle: "登入",
    loginHint: "輸入你的 email，我們會寄一封登入連結給你。不需要密碼。",
    loginSend: "寄出登入連結",
    loginSent: "信寄出了。打開信箱裡的連結就能登入，連結 15 分鐘內有效。",
    loginFailed: "寄不出去，請稍後再試一次。",
    verifying: "登入中…",
    verifyFailed: "這個連結已經失效，請重新要求一次。",
  },
  en: {
    site: "AiSiWhale",
    tagline: "AI & tech investing",
    latest: "Latest stories",
    empty: "No stories yet.",
    sources: "Sources",
    published: "Published",
    revised: "Updated",
    allStories: "All stories",
    all: "All",
    sections: {
      holdings: "Holdings",
      figures: "Public figures",
      ai: "AI & Tech",
      tw: "Taiwan",
      us: "US stocks",
      crypto: "Crypto",
      institutions: "Institutional views",
      gold: "Gold",
      commodities: "Futures",
      fx: "Currencies",
    },
    sectionsLabel: "Sections",
    topics: { watch: "Holdings watch" } as Record<string, string>,
    tagsLabel: (topic: string) => `${topic}, by kind`,
    pagination: {
      label: "Pages",
      first: "First page",
      previous: "Previous page",
      next: "Next page",
      last: "Last page",
      page: (n: number) => `Page ${n}`,
      counter: (n: number, total: number) => `Page ${n} of ${total}`,
    },
    page: (n: number) => `Page ${n}`,
    newerStory: "Newer story",
    olderStory: "Older story",
    markets: "Markets",
    quoteNames: {
      taiex: "TAIEX",
      "tw:2330": "TSMC",
      "tw:2317": "Hon Hai",
      "tw:2454": "MediaTek",
      "tw:2382": "Quanta",
      "tw:2308": "Delta",
      "tw:0050": "Yuanta Taiwan 50",
      "tw:006208": "Fubon Taiwan 50",
      nasdaq: "Nasdaq",
      us10y: "US 10Y",
      wti: "WTI crude",
      btc: "Bitcoin",
      eth: "Ether",
    } as Record<string, string>,
    basis: { close: "Close", prev_close: "Previous close", last: "Latest", "24h": "24-hour change" } as Record<
      string,
      string
    >,
    marketsNote: "Closing or delayed figures, for reference only",
    marketsCredit: (sources: string[]) =>
      `Market data: ${sources.join(", ")}. Closing or delayed figures, for reference only.`,
    sourceNames: {
      TWSE: "Taiwan Stock Exchange",
      FRED: "FRED (Federal Reserve Bank of St. Louis)",
      Finnhub: "Finnhub",
      CoinGecko: "CoinGecko",
    } as Record<string, string>,
    chart: {
      title: "Price",
      intervals: { intraday: "15m", day: "Day", week: "Week", month: "Month" },
      intradayNote: "15-minute bars in US Eastern time; volume is IEX's only.",
      average: (view: string, n: number) =>
        view === "intraday" ? `MA${n}` : `${n}${({ day: "D", week: "W", month: "M" } as Record<string, string>)[view]}`,
      averageTitle: (view: string, n: number) =>
        `${n}-${({ intraday: "bar", day: "day", week: "week", month: "month" } as Record<string, string>)[view]} moving average`,
      ohlc: { o: "O", h: "H", l: "L", c: "C" },
      volume: "Volume",
      lots: "lots",
      none: "No price history for this stock yet.",
      preparing: "Fetching this stock's price history from the exchange; it usually takes a few minutes. Refresh later.",
      source: (source: string, adjusted: boolean) =>
        `Data: ${source}${adjusted ? ", adjusted for splits and dividends" : ""}. For reference only, not investment advice.`,
    },
    stock: {
      day: { open: "Open", high: "High", low: "Low", previous_close: "Prev. close" } as Record<string, string>,
      marketCap: "Market value",
      holders: "Big investors' holdings (13F)",
      holdersNote: (period: string, before: string | null) =>
        `13F filings for the quarter ended ${period}${before ? `, against ${before}` : ""}. A 13F shows only long positions in US-listed securities, filed up to 45 days after the quarter ends.`,
      holdersNone: "None of the investors we follow held it in their latest 13F.",
      holdersUs: "Taiwan stocks are not in 13F filings; these are the holders of its US listing (TSM).",
      twNo13f: "13F filings cover US-listed securities only; there are none for this Taiwan stock.",
      investor: "Investor",
      action: "This quarter",
      shares: "Shares",
      value: "Value",
      weight: "Of portfolio",
      filing: "Filing",
      changes: {
        new: "New",
        increased: "Added",
        decreased: "Cut",
        unchanged: "Unchanged",
        sold_out: "Sold out",
      } as Record<string, string>,
      options: { PUT: "puts (a bet on a fall)", CALL: "calls (a bet on a rise)" } as Record<string, string>,
      underlying: "Underlying shares",
      was: (n: string) => `was ${n}`,
      trades: "Public figures' trades",
      tradesNote:
        "From the transaction reports the President (OGE 278-T) and members of Congress (STOCK Act) must file. Amounts are the reports' ranges; the reports are transcribed by AI and shown only once a person has checked them against the original.",
      owners: { SP: "spouse", JT: "joint", DC: "child" } as Record<string, string>,
      option: "Option",
      tradesNone: "No recent transaction report of the figures we follow names it.",
      tradesElsewhere:
        "The President's and members of Congress's reported trades are not compiled by AiSiWhale; these trackers publish them:",
      trackers: [
        ["Trump's trades (Open Cabinet)", "https://open-cabinet.org/officials/trump-donald-j"],
        ["Pelosi's trades (Capitol Trades)", "https://www.capitoltrades.com/politicians/P000197"],
      ] as [string, string][],
      kinds: { purchase: "Bought", sale: "Sold", "partial sale": "Sold part", exchange: "Exchanged" } as Record<string, string>,
      over: (n: string) => `over ${n}`,
      late: "reported 30+ days late",
      report: "Report",
      coverage: "Our coverage",
      coverageNone: "No stories mention it yet.",
      coveragePast: "No stories on this page.",
      back: "← Back to the stories",
      noQuote: "No quote right now.",
      notice: "Prices are closing or delayed; holdings are from SEC 13F filings. For reference only, not investment advice.",
      noticeNo13f: "Prices are closing or delayed. For reference only, not investment advice.",
    },
    scrollLeft: "Scroll left",
    scrollRight: "Scroll right",
    listen: "Listen",
    stopListening: "Stop",
    print: "Print",
    toDark: "Switch to dark mode",
    toLight: "Switch to light mode",
    readIn: "Read in:",
    notice:
      "Stories are written and fact-checked by an AI newsroom and approved by a person before they are published. They summarise public information for reference only and are not investment advice; investing carries risk.",
    membersOnly: "This story is for members",
    membersOnlyWhy: "Members can read every members-only story.",
    membersOnlyAlready: "Already a member?",
    planName: { month: "Monthly", year: "Yearly" },
    planTerm: { month: "month", year: "year" },
    planChoose: { month: "Choose monthly", year: "Choose yearly" },
    planSaving: (percent: number) => `Save ${percent}% vs monthly`,
    planOnce: "Paid once; nothing renews by itself. Buying again before it ends adds to the time you have left.",
    planAgree: ["By paying you agree to the ", " and the ", "."],
    pricing: "Membership",
    pricingClosed: "Every story is free to read. Paid membership is not open yet.",
    pricingIntro: "Most AiSiWhale stories are free. Members can also read every story marked members-only.",
    pricingIncludes: [
      "Every members-only story, in Chinese and in English",
      "Paid once: nothing renews or is charged again, and there is nothing to cancel",
      "Renewing early loses nothing: the new period starts where the old one ends",
      "A full refund within 7 days of paying",
    ],
    pricingPayment: "Card payments are processed by PAYUNi (統一金流); your card number never reaches us.",
    pricingSignIn: "You sign in with your email before buying; the membership belongs to that account.",
    updated: "Last updated",
    sep: ": ",
    doneTitle: "Payment",
    doneChecking: "Confirming your payment…",
    doneOk: (date: string) => `Paid. Your membership runs until ${date}.`,
    doneWaiting: (email: string) =>
      `We have not had the payment confirmed yet. If you paid, reload this page in a few minutes; if it still says this, write to ${email}.`,
    doneSignedOut: "Sign in to see your membership.",
    doneBack: "Back to the stories",
    aside: (text: string) => ` (${text})`,
    terms: "Terms of Service",
    privacy: "Privacy Policy",
    refund: "Refund Policy",
    operator: "Operated by",
    contact: "Contact",
    phone: "Phone",
    membersSoon: "Paying is not open yet — this is where it will be.",
    membersStarting: "Opening the payment page…",
    membersFailed: "The payment page could not be opened. Please try again.",
    signIn: "Sign in",
    signOut: "Sign out",
    watch: {
      title: "My watchlist",
      edit: "Edit list",
      done: "Done",
      editLink: "Edit",
      showSide: "Watchlist",
      hideSide: "Hide list",
      noChart: "Indices, rates, oil and coins have no chart here; the latest figure only.",
      emptyBoard: "The list is empty. Press Edit list to search and add stocks.",
      sample: "Sample watchlist · sign in to make yours",
      link: "Watchlist",
      add: "☆ Watch",
      added: "★ Watching",
      remove: "Remove",
      drag: (name: string) => `Drag to move ${name}`,
      dnd: {
        instructions: "Press space to pick up, the arrow keys to move, space to drop; Escape cancels.",
        start: (name: string) => `Picked up ${name}.`,
        over: (name: string, place: number) => `${name} moved to position ${place}.`,
        end: (name: string, place: number) => `${name} dropped at position ${place}.`,
        cancel: (name: string) => `Cancelled; ${name} is back in place.`,
      },
      reorderHint: "Drag ⋮⋮ to reorder; the strip and the list beside each stock follow this order.",
      signInToWatch: "Sign in to keep your own watchlist and switch between stocks quickly.",
      empty: "No stocks yet. Search any Taiwan or US stock to add it, or pick a popular one.",
      more: "Popular stocks",
      search: "Search Taiwan or US stocks: code, ticker or name",
      searchLabel: "Search stocks",
      noResults: "No stock matches.",
      view: "View",
      addShort: "+ Add",
      kinds: { stock: "Stock", etf: "ETF", adr: "ADR" } as Record<string, string>,
      failed: "The watchlist could not be read just now.",
      note: "Only you can see your watchlist. Prices are closing or delayed, for reference only, not investment advice.",
    },
    signedInAs: "Signed in",
    member: "Member",
    memberUntil: "Member until",
    becomeMember: "Become a member",
    loginTitle: "Sign in",
    loginHint: "Type your email and we will send you a link. No password.",
    loginSend: "Send the link",
    loginSent: "Sent. Open the link in your inbox within 15 minutes.",
    loginFailed: "It could not be sent. Please try again.",
    verifying: "Signing you in…",
    verifyFailed: "This link no longer works. Ask for a new one.",
  },
} as const;

/** The site's sections (D-047), as the API names them. */
export const SECTIONS = [
  "holdings",
  "figures",
  "ai",
  "tw",
  "us",
  "crypto",
  "institutions",
  "gold",
  "commodities",
  "fx",
] as const;
export type Section = (typeof SECTIONS)[number];

export function isSection(value: unknown): value is Section {
  return typeof value === "string" && (SECTIONS as readonly string[]).includes(value);
}

/** The site's tabs (D-050). Most are one section — 黃金, 期貨 and 外匯 each a tab of their own
 * (D-067); 持股觀察 (``watch``) is two — the big investors' filings and the public figures' —
 * told apart inside it by tags. */
export const TOPICS = ["ai", "tw", "us", "crypto", "gold", "commodities", "fx", "institutions", "watch"] as const;
export type Topic = (typeof TOPICS)[number];

const TOPIC_SECTIONS: Record<Topic, readonly Section[]> = {
  watch: ["holdings", "figures"],
  ai: ["ai"],
  tw: ["tw"],
  us: ["us"],
  crypto: ["crypto"],
  institutions: ["institutions"],
  gold: ["gold"],
  commodities: ["commodities"],
  fx: ["fx"],
};

/** What ``?section=`` may say: a tab, or one of the sections inside a tab of several. */
export type Filter = Topic | Section;

export function isFilter(value: unknown): value is Filter {
  return isSection(value) || (typeof value === "string" && (TOPICS as readonly string[]).includes(value));
}

/** The sections a filter shows. */
export function sectionsOf(filter: Filter): Section[] {
  return isSection(filter) ? [filter] : [...TOPIC_SECTIONS[filter]];
}

/** The tab a section is under. */
export function topicOf(section: Section): Topic {
  return TOPICS.find((topic) => TOPIC_SECTIONS[topic].includes(section))!;
}

/** The tags inside a tab: its sections, when it has more than one. */
export function tagsOf(topic: Topic): readonly Section[] {
  return TOPIC_SECTIONS[topic].length > 1 ? TOPIC_SECTIONS[topic] : [];
}

/** A filter's name: a tab's, or a section's. */
export function filterName(lang: Lang, filter: Filter): string {
  const w = words(lang);
  return isSection(filter) ? w.sections[filter] : (w.topics[filter] ?? w.sections[filter as Section]);
}

export function words(lang: Lang) {
  return WORDS[lang];
}

export function formatDate(lang: Lang, iso: string): string {
  return new Intl.DateTimeFormat(lang, { dateStyle: "long", timeZone: "Asia/Taipei" }).format(
    new Date(iso),
  );
}
