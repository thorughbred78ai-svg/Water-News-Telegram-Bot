import os
import sys
import html
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import requests
import feedparser


# =========================
# Telegram 設定
# =========================

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    print("Error: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set.")
    sys.exit(1)


# =========================
# 搜尋設定
# =========================

KEYWORDS = ["水利", "水務", "颱風"]

# 稍微大於 60 分鐘，避免整點邊界遺漏
LOOKBACK_MINUTES = 70

GOOGLE_NEWS_RSS = (
    "https://news.google.com/rss/search"
    "?q={}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
)


# =========================
# 取得 Google News
# =========================

def fetch_news(keyword):
    url = GOOGLE_NEWS_RSS.format(quote(keyword))

    print(f"Fetching: {url}")

    parsed = feedparser.parse(url)

    items = []

    for entry in parsed.entries:
        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        pub_date = entry.get("published", "").strip()

        if title and link and pub_date:
            items.append(
                {
                    "title": title,
                    "link": link,
                    "pub_date": pub_date,
                    "keyword": keyword,
                }
            )

    print(f"Found {len(items)} items for keyword: {keyword}")

    return items


# =========================
# 解析發布時間
# =========================

def parse_pub_date(date_str):
    """
    Google News RSS 常見格式：
    Mon, 25 Sep 2026 08:00:00 GMT
    """

    try:
        clean = date_str.replace("GMT", "+0000")

        dt = datetime.strptime(
            clean,
            "%a, %d %b %Y %H:%M:%S %z",
        )

        return dt.astimezone(timezone.utc)

    except Exception as e:
        print(f"Date parse error for '{date_str}': {e}")
        return None


# =========================
# 發送 Telegram
# =========================

def send_telegram_message(text):
    api_url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    response = requests.post(
        api_url,
        json=payload,
        timeout=30,
    )

    response.raise_for_status()

    return response.json()


# =========================
# 主程式
# =========================

def main():
    now_utc = datetime.now(timezone.utc)

    cutoff = now_utc - timedelta(
        minutes=LOOKBACK_MINUTES
    )

    print(
        f"Current UTC time: "
        f"{now_utc.strftime('%Y-%m-%d %H:%M:%S')}"
    )

    print(
        f"Looking for news after: "
        f"{cutoff.strftime('%Y-%m-%d %H:%M:%S')}"
    )

    all_items = []
    seen_links = set()

    # -------------------------
    # 搜尋所有關鍵字
    # -------------------------

    for keyword in KEYWORDS:

        try:
            items = fetch_news(keyword)

            for item in items:

                # 避免相同新聞重複出現
                if item["link"] in seen_links:
                    continue

                pub_dt = parse_pub_date(
                    item["pub_date"]
                )

                if pub_dt is None:
                    continue

                # 只保留最近 70 分鐘的新聞
                if pub_dt >= cutoff:

                    item["pub_dt"] = pub_dt

                    all_items.append(item)

                    seen_links.add(item["link"])

        except Exception as e:

            print(
                f"Error processing keyword "
                f"'{keyword}': {e}"
            )

    # -------------------------
    # 沒有新聞
    # -------------------------

    if not all_items:

        print("No recent news found.")

        return

    # -------------------------
    # 最新新聞排前面
    # -------------------------

    all_items.sort(
        key=lambda x: x["pub_dt"],
        reverse=True,
    )

    # -------------------------
    # 建立標題
    # -------------------------

    header = (
        f"<b>🔔 每小時新聞播報</b> "
        f"<code>"
        f"{now_utc.strftime('%Y-%m-%d %H:%M UTC')}"
        f"</code>\n\n"
    )

    # -------------------------
    # 建立新聞列表
    # -------------------------

    lines = []

    for item in all_items:

        time_str = item["pub_dt"].strftime("%H:%M")

        # HTML escape，避免新聞標題中的
        # &, <, > 造成 Telegram HTML 錯誤
        safe_title = html.escape(
            item["title"]
        )

        # URL 也進行 HTML escape
        safe_link = html.escape(
            item["link"],
            quote=True,
        )

        line = (
            f'• <a href="{safe_link}">'
            f"{safe_title}"
            f"</a> "
            f"<code>"
            f"[{html.escape(item['keyword'])}] "
            f"{time_str}"
            f"</code>\n"
        )

        lines.append(line)

    # -------------------------
    # Telegram 單則訊息限制
    # -------------------------

    # Telegram message 上限約 4096 字元。
    # 預留一些空間，使用 4000 作為安全上限。
    MAX_MESSAGE_LENGTH = 4000

    messages = []

    current = header

    for line in lines:

        # 如果加入下一則會超過限制
        if (
            len(current)
            + len(line)
            > MAX_MESSAGE_LENGTH
        ):

            messages.append(current)

            current = header + line

        else:

            current += line

    # 加入最後一則
    if current.strip() != header.strip():
        messages.append(current)

    # -------------------------
    # 發送所有訊息
    # -------------------------

    total = len(messages)

    for index, message in enumerate(
        messages,
        start=1,
    ):

        try:

            print(
                f"Sending message "
                f"part {index}/{total}..."
            )

            send_telegram_message(message)

            print(
                f"Message part {index} sent successfully."
            )

        except Exception as e:

            print(
                f"Failed to send message "
                f"part {index}: {e}"
            )

            sys.exit(1)

    print(
        f"Done. Sent {len(all_items)} "
        f"news items in {total} message(s)."
    )


# =========================
# 程式入口
# =========================

if __name__ == "__main__":
    main()
