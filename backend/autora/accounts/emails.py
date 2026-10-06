"""What a reader is sent (D-025, D-230): a link to check their address, a link to set a new
password, and — when somebody registers an address that already has an account — a note to its
owner. Sign-in links are no longer sent (D-230).

Written in zh-TW, the product's language (D-002). Each says what it is, how long it lasts, and
what to do if it was not them — which is nothing, because a link nobody opens does nothing.
The site's name comes first in every subject: a reader should know who it is from before
opening it.
"""

from __future__ import annotations

from urllib.parse import quote

from autora.infra.email import Message

DEFAULT_LANG = "zh-TW"

VERIFY_SUBJECT = "艾矽鯨｜請確認你的 email"
RESET_SUBJECT = "艾矽鯨｜重設密碼"
EXISTS_SUBJECT = "艾矽鯨｜有人用你的 email 註冊"


def _page(site_base_url: str, lang: str, path: str) -> str:
    return f"{site_base_url.rstrip('/')}/news/{quote(lang)}/{path}"


def verify_url(site_base_url: str, token: str, *, lang: str = DEFAULT_LANG) -> str:
    return f"{_page(site_base_url, lang, 'verify-email')}?token={quote(token)}"


def reset_url(site_base_url: str, token: str, *, lang: str = DEFAULT_LANG) -> str:
    return f"{_page(site_base_url, lang, 'reset-password')}?token={quote(token)}"


def _message(to: str, subject: str, lines: list[str], link: tuple[str, str] | None) -> Message:
    text = "你好，\n\n" + "\n\n".join(lines[:1])
    html = "<p>你好，</p>" + f"<p>{lines[0]}</p>"
    if link is not None:
        label, url = link
        text += f"\n\n{url}"
        html += f'<p><a href="{url}">{label}</a></p><p style="color:#666;font-size:12px">{url}</p>'
    for line in lines[1:]:
        text += f"\n\n{line}"
        html += f"<p>{line}</p>"
    return Message(to=to, subject=subject, text=text + "\n", html=html)


def verify_email(to: str, url: str, *, hours: int = 24) -> Message:
    return _message(
        to,
        VERIFY_SUBJECT,
        [
            f"請點下面的連結，確認這是你在艾矽鯨的 email。{hours} 小時內有效，只能用一次：",
            "如果你沒有在艾矽鯨註冊，不用做任何事，這封信可以直接刪除。",
        ],
        ("確認 email", url),
    )


def reset_email(to: str, url: str, *, minutes: int = 30) -> Message:
    return _message(
        to,
        RESET_SUBJECT,
        [
            f"點下面的連結就能設定你在艾矽鯨的新密碼，{minutes} 分鐘內有效，而且只能用一次：",
            "設定後，所有已登入的裝置都會被登出。",
            "如果這不是你本人要求的，不用做任何事，你的密碼不會改變。",
        ],
        ("設定新密碼", url),
    )


def account_exists_email(to: str, site_base_url: str, *, lang: str = DEFAULT_LANG) -> Message:
    """Somebody tried to register an address that already has an account. Its owner is told,
    and shown the way in; the person registering was told only to check this mailbox."""
    login = _page(site_base_url, lang, "login")
    forgot = _page(site_base_url, lang, "forgot-password")
    return _message(
        to,
        EXISTS_SUBJECT,
        [
            "有人剛剛用這個 email 在艾矽鯨註冊，但這個 email 已經有帳號了，所以沒有建立新帳號。",
            f"如果是你：請直接登入（{login}），忘記密碼或還沒設定過密碼，請到 {forgot} 設定。",
            "如果不是你，不用做任何事，你的帳號沒有任何改變。",
        ],
        None,
    )


def registration_closed_email(to: str, site_base_url: str, *, lang: str = DEFAULT_LANG) -> Message:
    """Somebody tried to register an address that may not be registered here (D-230: one on
    ADMIN_EMAILS with no account yet). Its owner is shown the ways in that prove the address
    themselves; the person registering was told only to check this mailbox."""
    login = _page(site_base_url, lang, "login")
    forgot = _page(site_base_url, lang, "forgot-password")
    return _message(
        to,
        EXISTS_SUBJECT,
        [
            "有人剛剛用這個 email 在艾矽鯨註冊，但這個 email 不能用註冊建立帳號，所以沒有建立。",
            f"如果是你：請到 {login} 選「使用 Google 繼續」，或到 {forgot} 設定密碼。",
            "如果不是你，不用做任何事。",
        ],
        None,
    )
