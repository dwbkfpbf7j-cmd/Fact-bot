# Fact-bot
 bot for interesting facts

import os
import re
import json
import html
import hashlib
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHANNEL = "@znaehti"

FEEDS = {
    "NASA": "https://www.nasa.gov/feed/",
    "NOAA": "https://www.noaa.gov/rss.xml",
    "Smithsonian": "https://www.smithsonianmag.com/rss/science-nature/",
    "ScienceDaily": "https://www.sciencedaily.com/rss/all.xml",
    "BBC Science": "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
}

STATE_FILE = Path("posted.json")

STOPWORDS = set("""
the and for with from that this have has was are were into about
your their they them what when where which who will would could
а и в на с по для что это как из к от о об при над под
""".split())


def fetch(url):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "FactBot/1.0"}
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read()


def clean(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def get_articles():
    articles = []

    for source, url in FEEDS.items():
        try:
            root = ET.fromstring(fetch(url))

            for item in root.iter():
                tag = item.tag.split("}")[-1].lower()

                if tag not in ("item", "entry"):
                    continue

                fields = {}

                for child in item:
                    name = child.tag.split("}")[-1].lower()
                    value = child.attrib.get("href", "") if name == "link" else child.text or ""

                    if name not in fields or value:
                        fields[name] = value

                title = clean(fields.get("title", ""))
                link = fields.get("link", "")
                summary = clean(
                    fields.get("description", "")
                    or fields.get("summary", "")
                    or fields.get("encoded", "")
                )

                if title and link.startswith("http"):
                    articles.append({
                        "source": source,
                        "title": title,
                        "summary": summary[:1200],
                        "link": link
                    })

        except Exception as error:
            print("Feed error:", source, error)

    return articles


def words(text):
    return {
        word.lower()
        for word in re.findall(r"[a-zа-яё0-9]{4,}", text.lower())
        if word.lower() not in STOPWORDS
    }


def similarity(first, second):
    a = words(first)
    b = words(second)

    if not a or not b:
        return 0

    common = a & b
    return len(common) / min(len(a), len(b))


def load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return []


def save_state(state):
    STATE_FILE.write_text(
        json.dumps(state[-200:], ensure_ascii=False, indent=2)
    )


def find_confirmed(articles, posted):
    best = None
    best_score = 0

    for i, first in enumerate(articles):
        for second in articles[i + 1:]:
            if first["source"] == second["source"]:
                continue

            score = similarity(
                first["title"],
                second["title"]
            )

            if score < 0.30:
                continue

            digest = hashlib.sha256(
                (first["title"] + second["title"]).encode()
            ).hexdigest()

            if digest in posted:
                continue

            if score > best_score:
                best_score = score
                best = (first, second, digest)

    return best


def publish(first, second):
    title = html.escape(first["title"])
    summary = html.escape(first["summary"][:700])
    source1 = html.escape(first["source"])
    source2 = html.escape(second["source"])

    message = (
        "💡 <b>А ЗНАЕТЕ ЛИ ВЫ?</b>\n\n"
        f"<b>{title}</b>\n\n"
        f"{summary}\n\n"
        "🔎 <b>Материалы для сверки:</b>\n"
        f'1. <a href="{html.escape(first["link"], quote=True)}">{source1}</a>\n'
        f'2. <a href="{html.escape(second["link"], quote=True)}">{source2}</a>\n\n'
        "#АЗнаетеЛиВы #ИнтересныеФакты"
    )

    data = json.dumps({
        "chat_id": CHANNEL,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }).encode()

    request = urllib.request.Request(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data=data,
        headers={"Content-Type": "application/json"}
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.loads(response.read())

    if not result.get("ok"):
        raise RuntimeError("Telegram rejected the message")

    print("Post published successfully")


def main():
    print("Searching for interesting materials...")

    articles = get_articles()
    print("Articles found:", len(articles))

    posted = load_state()
    match = find_confirmed(articles, posted)

    if not match:
        print("No sufficiently matching independent sources. Skipping.")
        return

    first, second, digest = match

    publish(first, second)

    posted.append(digest)
    save_state(posted)


if __name__ == "__main__":
    main()
