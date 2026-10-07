// The site's three policies, in both languages (D-034): terms, privacy, refunds.
//
// Written to match what the code does, so a change to one is a change to the other:
// - one-time payments that never renew, a month or a year (memberships.purchase);
// - buying early adds to the end, buying after a lapse starts from the payment (_membership);
// - card payments on PAYUNi's page, and the card never reaches us (checkout.ts, payuni.py);
// - sign-in by email and password (Argon2id hash) or Google; a confirmation link valid 24 hours,
//   a reset link valid 30 minutes that signs out every device; a session cookie for 60 days
//   (accounts, D-230);
// - the email address lives only in the readers table; the rest of the system knows a reader
//   by an id (D-018, D-025);
// - reads are counted with a random id that changes every day (session.ts).
//
// No prices here: the pricing page shows what the API charges, and a policy that repeats a
// number is a policy that goes stale the day the price changes.
import type { Lang } from "./i18n";
import type { Operator } from "./operator";

export type Block = string | readonly string[];
export interface Section {
  heading: string;
  body: readonly Block[];
}
export interface LegalDoc {
  title: string;
  updated: string;
  sections: readonly Section[];
}

export const LEGAL_PAGES = ["terms", "privacy", "refund"] as const;
export type LegalPage = (typeof LEGAL_PAGES)[number];

const UPDATED = "2026-10-06";
const TERMS_UPDATED = "2026-10-07"; // 鯨幣 (P3-C-3)

function who(op: Operator, lang: Lang): string {
  if (lang === "en") return op.owner ? `${op.brand} (${op.owner})` : op.brand;
  return op.owner ? `${op.brand}（負責人：${op.owner}）` : op.brand;
}

function terms(lang: Lang, op: Operator): LegalDoc {
  if (lang === "en") {
    return {
      title: "Terms of Service",
      updated: TERMS_UPDATED,
      sections: [
        {
          heading: "1. Who we are",
          body: [
            `AiSiWhale (艾矽鯨, aisiwhale.com, "the site") is run by ${who(op, lang)} ("we"). By using the site you agree to these terms. Contact: ${op.email}.`,
          ],
        },
        {
          heading: "2. The service",
          body: [
            "The site publishes news in Chinese and English. Stories are researched, written and fact-checked by an AI newsroom, and each one is approved by a person before it is published.",
            "Most stories are free. Some are marked members-only; members can read all of them for as long as their membership lasts.",
            "Stories are for general information. They are not investment, legal, medical or other professional advice, and you should not rely on them alone for such decisions. If you find an error, tell us and we will correct it.",
          ],
        },
        {
          heading: "3. Signing in",
          body: [
            "You sign in with your email address and a password, or with your Google account. A password needs at least 8 characters; we keep only a one-way hash of it and cannot see it.",
            "When you register with an email address we send a link to confirm it, valid for 24 hours. If you forget your password you can ask for a reset link, valid for 30 minutes; setting a new password signs you out on every device.",
            "If you sign in with Google using an email address that already has a confirmed account here, both ways lead to the same account.",
            "Keep your password and your mailbox secure: anybody who can open your email can use a reset link to take over your account.",
          ],
        },
        {
          heading: "4. Membership and payment",
          body: [
            [
              "Membership is sold for a month or for a year. The current prices are on the Membership page and are shown again before you pay.",
              "Each purchase is a single payment. Nothing renews or is charged again by itself.",
              "Membership starts once the payment provider confirms the payment, normally within moments.",
              "A month ends on the same day of the next month (or that month's last day if there is no such day); a year ends on the same day a year later.",
              "Buying again before your membership ends adds the new period to its end, so you lose nothing by renewing early. Buying after it has ended starts from the day you pay.",
              "Payments are processed by PAYUNi (統一金流). Card details are entered on PAYUNi's page and never reach us.",
              "A change in price applies only to later purchases. What you have already paid for does not change.",
            ],
            "Refunds are covered by the Refund Policy.",
          ],
        },
        {
          // Whale Coins (D-223, D-219, D-235): a product draft. For a lawyer to confirm before it is
          // relied on: that coins are not an electronic stored-value instrument or prepaid value
          // under Taiwan law, and how changes to the rules are announced and take effect. What
          // happens to coins when an account is closed is left out until that is confirmed.
          heading: "5. Whale Coins",
          body: [
            [
              "Whale Coins are points the site gives members, under the rules posted on the site at the time (for example, each month), to use certain features here. They cannot be bought with money.",
              "Whale Coins are not legal tender, an electronic stored-value instrument or prepaid value, and have no cash value.",
              "Whale Coins may not be sold, transferred, given away or traded, exchanged for cash or anything else, or withdrawn.",
              "There are limits on how many Whale Coins are given and how many may be held; coins beyond a limit are not given.",
              "A change in your membership (for example, VIP ending) does not take back coins you already hold.",
              "We may change how many Whale Coins are given, the limits, and the features they can be used for; changes are posted on the site.",
            ],
          ],
        },
        {
          heading: "6. Use of the content",
          body: [
            "The stories and the site belong to us or to their stated sources. You may read them, share links to them and quote short passages with attribution.",
            "You may not republish members-only stories in full, share your account, or copy the site in bulk by scraping or automated means.",
          ],
        },
        {
          heading: "7. Changes and interruptions",
          body: [
            "We may change or stop parts of the site. If we stop selling membership altogether, or the site is unavailable for a long time through our fault, members will be refunded for the unused whole months of their membership.",
            "We may update these terms. Changes are posted on this page with a new date; they do not reduce what you have already paid for.",
          ],
        },
        {
          heading: "8. Liability",
          body: [
            "We work to keep the site accurate and available but cannot promise it will always be either. To the extent the law allows, our liability to you is limited to what you paid us in the twelve months before the claim.",
          ],
        },
        {
          heading: "9. Law",
          body: [
            "These terms are governed by the laws of the Republic of China (Taiwan). The Taiwan Taipei District Court is the court of first instance, except where the law provides otherwise.",
          ],
        },
      ],
    };
  }
  return {
    title: "服務條款",
    updated: TERMS_UPDATED,
    sections: [
      {
        heading: "一、經營者",
        body: [
          `艾矽鯨（AiSiWhale，aisiwhale.com，以下稱「本站」）由 ${who(op, lang)}（以下稱「我們」）經營。使用本站即表示你同意本條款。聯絡信箱：${op.email}。`,
        ],
      },
      {
        heading: "二、服務內容",
        body: [
          "本站以中文與英文發布新聞。報導由 AI 新聞室蒐集資料、撰寫並查核事實，每一篇在發布前都經過人工核准。",
          "大部分報導免費閱讀；部分報導標示為會員專屬，會員在會員期間內可以閱讀全部會員專屬報導。",
          "報導僅供一般資訊參考，不構成投資、法律、醫療或其他專業建議，請勿僅憑報導做出此類決定。發現錯誤請告訴我們，我們會更正。",
        ],
      },
      {
        heading: "三、登入",
        body: [
          "你可以用 email 與密碼，或用 Google 帳號登入本站。密碼至少 8 個字元；我們只保存無法還原的雜湊值，看不到你的密碼。",
          "用 email 註冊後，我們會寄一封確認信，連結 24 小時內有效。忘記密碼時可以申請重設連結，30 分鐘內有效；設定新密碼後，所有已登入的裝置都會被登出。",
          "如果你用 Google 登入時使用的 email，已經在本站註冊並完成確認，兩種方式會進入同一個帳號。",
          "請妥善保管你的密碼與信箱：能打開你信箱的人，可以透過重設連結取得你的帳號。",
        ],
      },
      {
        heading: "四、會員與付款",
        body: [
          [
            "會員分為月繳（一個月）與年繳（一年）兩種方案，目前價格列在「會員方案」頁面，付款前也會再次顯示。",
            "每次購買都是單次付款，不會自動續約或自動扣款。",
            "金流服務商確認付款後即開通會員資格，通常在付款完成後幾秒內。",
            "一個月的會員期間到次月同一日為止（次月沒有該日時，到該月最後一日）；一年到隔年同一日為止。",
            "會員期間尚未結束前再次購買，新的期間會接在原到期日之後，提早續購不會損失天數；到期後才購買，從付款當日起算。",
            "付款由統一金流（PAYUNi）處理，信用卡資料在統一金流的付款頁面輸入，本站不會取得或儲存你的卡號。",
            "價格調整只適用於之後的購買，已購買的會員期間不受影響。",
          ],
          "退款依「退款政策」辦理。",
        ],
      },
      {
        // 鯨幣（D-223、D-219、D-235）：產品條款草稿，見英文版的說明——「不是電子票證或儲值金」與
        // 規則調整的公告方式待律師確認；帳號停用後鯨幣如何處理，確認前不寫入。
        heading: "五、鯨幣",
        body: [
          [
            "鯨幣是本站依當時公告的規則發放給會員（例如每月發放）、用於使用本站特定功能的點數，不能以金錢購買。",
            "鯨幣不是法定貨幣、電子票證或儲值金，沒有現金價值。",
            "鯨幣不得販售、轉讓、贈與或交易，也不得兌換現金或其他財物，不得提領。",
            "鯨幣的發放與持有都有上限；超過上限的部分不會發放。",
            "會員資格變更（例如 VIP 到期）時，已持有的鯨幣不會因此被收回。",
            "我們可能調整鯨幣的發放數量、上限與可使用的功能，調整會公布在本站。",
          ],
        ],
      },
      {
        heading: "六、內容的使用",
        body: [
          "本站的報導與網站內容屬於我們或所標示的來源。你可以閱讀、分享報導連結，並在註明出處的情況下引用少量段落。",
          "請勿全文轉載會員專屬報導、與他人共用帳號，或以爬蟲等自動化方式大量複製本站內容。",
        ],
      },
      {
        heading: "七、服務變更與中斷",
        body: [
          "我們可能調整或停止本站的部分功能。若我們停止販售會員資格，或因我們的原因使本站長時間無法使用，會依會員尚未使用的完整月數退款。",
          "我們可能修改本條款，修改後會公布在本頁並更新日期；修改不會減少你已經付費取得的權益。",
        ],
      },
      {
        heading: "八、責任限制",
        body: [
          "我們會盡力維持本站內容正確、服務穩定，但無法保證永遠如此。在法律允許的範圍內，我們對你的賠償責任以你在請求前 12 個月內支付給我們的金額為上限。",
        ],
      },
      {
        heading: "九、準據法與管轄",
        body: [
          "本條款以中華民國法律為準據法。如有爭議，以臺灣臺北地方法院為第一審管轄法院，但法律另有規定者，從其規定。",
        ],
      },
    ],
  };
}

function privacy(lang: Lang, op: Operator): LegalDoc {
  if (lang === "en") {
    return {
      title: "Privacy Policy",
      updated: UPDATED,
      sections: [
        {
          heading: "1. Who is responsible",
          body: [
            `Your personal data is handled by ${who(op, lang)}, which runs AiSiWhale. Questions and requests: ${op.email}.`,
          ],
        },
        {
          heading: "2. What we collect, and why",
          body: [
            [
              "Your email address and password, when you register: the email address to send you confirmation and password-reset emails and to recognise your account; the password only as a one-way hash.",
              "If you sign in with Google: your Google account id, your email address, and whether Google has confirmed that address — to recognise your account. We do not receive your name, photo or anything else from your Google account.",
              "A sign-in cookie: to keep you signed in, for up to 60 days. While you sign in with Google, a second cookie lasting 10 minutes checks that the sign-in started in your browser.",
              "Sign-in attempts: to stop password guessing we count attempts to sign in, register and reset a password, by a one-way hash of your IP address and of the email address used — never the address itself. The counts are deleted after about a day.",
              "Your orders and payments (plan, amount, time, the payment provider's reference): to grant your membership and keep accounts.",
              "Reading counts: when you open a story, your browser sends a random id that it replaces every day. It cannot be linked to you or followed from one day to the next, and nothing else about you is sent.",
            ],
            "We do not collect your card number, your name, your address or your phone number. We do not use advertising or third-party tracking.",
          ],
        },
        {
          heading: "3. Who else sees it",
          body: [
            [
              "PAYUNi (統一金流), to take your payment. We pass your email address so that PAYUNi can send your receipt; your card details go to PAYUNi directly.",
              "Google, when you choose to sign in with it: Google confirms who you are and knows that you signed in to this site.",
              "Resend, which delivers our confirmation and password-reset emails, receives your email address for that purpose.",
              "Our hosting provider stores the data on our behalf.",
            ],
            "Inside our own system, your email address is kept only in the account table. The software that runs the newsroom and the business — including its AI agents — knows members only by an anonymous id.",
            "We do not sell your data. We disclose it to others only when the law requires it.",
          ],
        },
        {
          heading: "4. How long we keep it",
          body: [
            "Your account stays until you ask us to delete it. Payment records are kept for as long as accounting and tax law require (at least five years), even after the account is deleted. The tokens in confirmation and password-reset links are kept only as one-way hashes; a confirmation link stops working once used or after 24 hours, and a reset link once used or after 30 minutes. Sign-in session tokens are likewise kept only as one-way hashes; a session ends at once when you sign out, and otherwise when the session lifetime set by the system runs out.",
          ],
        },
        {
          heading: "5. Your rights",
          body: [
            `Under Taiwan's Personal Data Protection Act you may ask to see or copy your data, correct it, have us stop using it, or delete it. Write to ${op.email} from the address on your account and we will answer within 30 days.`,
          ],
        },
        {
          heading: "6. Changes",
          body: ["If this policy changes, the new version is posted here with a new date."],
        },
      ],
    };
  }
  return {
    title: "隱私權政策",
    updated: UPDATED,
    sections: [
      {
        heading: "一、蒐集者",
        body: [
          `你的個人資料由經營艾矽鯨的 ${who(op, lang)} 負責處理。有任何問題或請求，請寫信到 ${op.email}。`,
        ],
      },
      {
        heading: "二、我們蒐集的資料與用途",
        body: [
          [
            "Email 與密碼：你註冊時提供。Email 用來寄送確認信與重設密碼信、辨識你的帳號；密碼只以無法還原的雜湊值保存。",
            "Google 登入：如果你選擇用 Google 登入，我們會從 Google 取得你的 Google 帳號編號、email，以及 Google 是否已確認這個 email，用來辨識你的帳號；不會取得你的姓名、照片或其他 Google 資料。",
            "登入 cookie：讓你保持登入，最長 60 天。用 Google 登入的過程中，另有一個 10 分鐘的 cookie，用來確認登入是從你的瀏覽器開始的。",
            "登入嘗試紀錄：為了防止有人猜密碼，我們會計算登入、註冊與重設密碼的嘗試次數，以 IP 位址與所用 email 經過無法還原的雜湊後計算，不保存原始內容，約一天後刪除。",
            "訂單與付款紀錄（方案、金額、時間、金流服務商的交易編號）：用來開通會員資格與記帳。",
            "閱讀統計：你打開報導時，瀏覽器會送出一個每天更換的隨機編號。這個編號無法對應到你本人，也無法跨日追蹤，除此之外不會送出任何關於你的資訊。",
          ],
          "我們不蒐集你的卡號、姓名、地址或電話，也不使用廣告或第三方追蹤工具。",
        ],
      },
      {
        heading: "三、會接觸到資料的第三方",
        body: [
          [
            "統一金流（PAYUNi）：處理付款。我們會提供你的 email，讓統一金流寄送付款通知；信用卡資料由你直接在統一金流的頁面輸入。",
            "Google：你選擇用 Google 登入時，由 Google 確認你的身分，Google 會知道你登入了本站。",
            "Resend：代我們寄送確認信與重設密碼信，因此會收到你的 email。",
            "主機服務商：代我們保存資料。",
          ],
          "在本站系統內部，你的 email 只存放在帳號資料表中。負責新聞室與營運的程式（包括其中的 AI 代理）只以匿名編號辨識會員。",
          "我們不會出售你的資料，除非法律要求，也不會提供給其他人。",
        ],
      },
      {
        heading: "四、保存期間",
        body: [
          "帳號會保留到你要求刪除為止。付款紀錄依會計與稅務法規保存（至少五年），帳號刪除後仍會保留。確認信與重設密碼連結的 token 僅以無法還原的雜湊值保存；確認連結使用後或 24 小時後失效，重設密碼連結使用後或 30 分鐘後失效。登入 session 的 token 亦僅以無法還原的雜湊值保存，登出後立即失效，並依系統設定的 session 期限自動失效。",
        ],
      },
      {
        heading: "五、你的權利",
        body: [
          `依個人資料保護法，你可以請求查詢、閱覽或複製你的資料，請求補充或更正，請求停止蒐集、處理或利用，或請求刪除。請用帳號的 email 寫信到 ${op.email}，我們會在 30 日內回覆。`,
        ],
      },
      {
        heading: "六、政策修改",
        body: ["本政策如有修改，會公布在本頁並更新日期。"],
      },
    ],
  };
}

function refund(lang: Lang, op: Operator): LegalDoc {
  if (lang === "en") {
    return {
      title: "Refund Policy",
      updated: UPDATED,
      sections: [
        {
          heading: "1. Within 7 days: a full refund",
          body: [
            "Within 7 days of paying, you can ask for a full refund of that payment, for any reason. The membership that payment bought ends when the refund is made.",
          ],
        },
        {
          heading: "2. After 7 days",
          body: [
            "Membership is digital content that can be used as soon as it is paid for, so a payment is not refunded after 7 days. Your membership continues to its end date.",
            "The exception is our fault: if we stop selling membership, or the site is unavailable for a long time because of us, you are refunded for the unused whole months (see the Terms of Service).",
          ],
        },
        {
          heading: "3. How to ask",
          body: [
            `Write to ${op.email} from the email address on your account, with the date and amount of the payment. We reply within 3 working days.`,
            "Refunds go back to the card you paid with, through PAYUNi. How soon it appears on your statement depends on your card issuer, usually 7 to 14 working days.",
          ],
        },
        {
          heading: "4. Nothing renews by itself",
          body: [
            "No plan renews or charges you again automatically, so there is nothing to cancel. If you do not buy again, your membership simply ends on its end date.",
          ],
        },
      ],
    };
  }
  return {
    title: "退款政策",
    updated: UPDATED,
    sections: [
      {
        heading: "一、付款後 7 天內：全額退款",
        body: [
          "付款後 7 天內，不論原因，都可以申請該筆付款全額退款。退款完成時，該筆付款所購買的會員期間同時終止。",
        ],
      },
      {
        heading: "二、超過 7 天",
        body: [
          "會員資格屬於付款後立即可以使用的數位內容，超過 7 天的付款不予退款，會員資格照常使用到到期日。",
          "例外是可歸責於我們的情形：我們停止販售會員資格，或因我們的原因使本站長時間無法使用時，會依尚未使用的完整月數退款（見服務條款）。",
        ],
      },
      {
        heading: "三、申請方式",
        body: [
          `請用帳號的 email 寫信到 ${op.email}，註明付款日期與金額。我們會在 3 個工作天內回覆。`,
          "退款透過統一金流退回原付款的信用卡。退款出現在帳單上的時間依發卡銀行而定，通常為 7 至 14 個工作天。",
        ],
      },
      {
        heading: "四、不會自動續扣",
        body: [
          "所有方案都不會自動續約或自動扣款，因此不需要取消。沒有再次購買，會員資格就在到期日結束。",
        ],
      },
    ],
  };
}

export function legalDoc(page: LegalPage, lang: Lang, op: Operator): LegalDoc {
  return { terms, privacy, refund }[page](lang, op);
}
