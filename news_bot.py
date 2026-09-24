import os
import sys
import requests
import feedparser
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
import html

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    print("Error: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set.")
    sys.exit(1)

KEYWORDS = ["水利", "水務", "颱風"]
# 稍微大於 60 分鐘，避免整點邊界遺漏
LOOKBACK_MINUTES = 70
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"


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
            items.append({
                "title": title,
                "link": link,
                "pub_date": pub_date,
                "keyword": keyword
            })
    return items


def parse_pub_date(date_str):
    # Google News RSS 時間格式範例: Mon, 25 Sep 2026 08:00:00 GMT
    try:
        clean = date_str.replace("GMT", "+0000")
        dt = datetime.strptime(clean, "%a, %d %b %Y %H:%M:%S %z")
        return dt.astimezone(timezone.utc)
    except Exception as e:
        print(f"Date parse error for '{date_str}': {e}")
        return None


def send_telegram_message(text):
    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    resp = requests.post(api_url, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def main():
    now_utc = datetime.now(timezone.utc)
    cutoff = now_utc - timedelta(minutes=LOOKBACK_MINUTES)

    all_items = []
    seen_links = set()

    for keyword in KEYWORDS:
        try:
            items = fetch_news(keyword)
            for item in items:
                if item["link"] in seen_links:
                    continue
                pub_dt = parse_pub_date(item["pub_date"])
                if pub_dt is None:
                    continue
                if pub_dt >= cutoff:
                    item["pub_dt"] = pub_dt
                    all_items.append(item)
                    seen_links.add(item["link"])
        except Exception as e:
            print(f"Error processing keyword '{keyword}': {e}")

    if not all_items:
        print("No recent news found.")
        return

    # 依發布時間由新到舊排序
    all_items.sort(key=lambda x: x["pub_dt"], reverse=True)

    header = f"<b>🔔 每小時新聞播報</b> <code>{now_utc.strftime('%Y-%m-%d %H:%M UTC')}</code>"
    
    lines = []
    for item in all_items:
        time_str = item["pub_dt"].strftime("%H:%M")
        safe_title = html.escape(item["title"])
        line = f'• <a href="{item["link"]}">{safe_title}</a> <code>[{item["keyword"]}] {time_str}</code>'
        lines.append(line)

    # Telegram 單則訊息上限 4096 字元，超過則拆分多則
    messages = []
    current = header
    for line in lines:
        if len(current) + len(line) + 1 > 4000:
            messages.append(current)
            current = header + line + "
"
        else:
            current += line + "
"
    if current.strip() and current != header:
        messages.append(current)

    for i, msg in enumerate(messages, 1):
        try:
            print(f"Sending message part {i}/{len(messages)}...")
            send_telegram_message(msg)
        except Exception as e:
            print(f"Failed to send message part {i}: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
