
import os
import json
import re
import html
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHANNEL = "@znaehti"
HISTORY_FILE = "posted.json"

FEEDS = {
    "NASA": "https://www.nasa.gov/feed/",
    "NOAA": "https://www.noaa.gov/news/rss.xml",
    "Smithsonian": "https://www.smithsonianmag.com/rss/latest_articles/",
    "ScienceDaily": "https://www.sciencedaily.com/rss/all.xml",
    "BBC Science": "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
}

def fetch(url):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 FactBot/1.0"}
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read()

def get_articles():
    articles = []

    for source, url in FEEDS.items():
        try:
            root = ET.fromstring(fetch(url))

            for item in root.iter():
                tag = item.tag.split("}")[-1].lower()

                if tag not in ("item", "entry"):
                    continue

                title = ""
                link = ""

                for child in item:
                    name = child.tag.split("}")[-1].lower()

                    if name == "title":
                        title = "".join(child.itertext()).strip()

                    elif name == "link":
                        link = child.attrib.get("href", "") or (child.text or "").strip()

                if title and link:
                    articles.append({
                        "title": title,
                        "link": link,
                        "source": source
                    })

        except Exception as error:
            print(f"Ошибка RSS {source}: {error}")

    return articles

def words(text):
    return set(re.findall(r"[a-zа-яё0-9]{3,}", text.lower()))

def similarity(first, second):
    a = words(first)
    b = words(second)

    if not a or not b:
        return 0

    return len(a & b) / len(a | b)

def load_history():
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as file:
        json.dump(history[-500:], file, ensure_ascii=False, indent=2)

def find_story(articles, history):
    articles.sort(key=lambda item: len(words(item["title"])), reverse=True)

    for article in articles:
        if article["link"] in history:
            continue

        matches = []

        for other in articles:
            if other["source"] == article["source"]:
                continue

            if similarity(article["title"], other["title"]) >= 0.30:
                matches.append(other)

        if matches:
            sources = {article["source"]}
            sources.update(item["source"] for item in matches)

            if len(sources) >= 2:
                return article, matches[0]

    return None, None

def publish(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    data = urllib.parse.urlencode({
        "chat_id": CHANNEL,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "false"
    }).encode()

    request = urllib.request.Request(url, data=data)

    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.loads(response.read().decode())

    if not result.get("ok"):
        raise RuntimeError(f"Telegram error: {result}")

def main():
    if not TOKEN:
        raise RuntimeError("Не найден секрет TELEGRAM_BOT_TOKEN")

    history = load_history()
    articles = get_articles()

    print(f"Получено материалов: {len(articles)}")

    first, second = find_story(articles, history)

    if not first:
        print("Не найдено подходящей новости из двух источников.")
        return

    title = html.escape(first["title"])
    source1 = html.escape(first["source"])
    source2 = html.escape(second["source"])

    link1 = html.escape(first["link"], quote=True)
    link2 = html.escape(second["link"], quote=True)

    message = (
        f"🔎 <b>А знаете ли вы?</b>\n\n"
        f"{title}\n\n"
        f"📰 Источники:\n"
        f'• <a href="{link1}">{source1}</a>\n'
        f'• <a href="{link2}">{source2}</a>\n\n'
        f"Подписывайтесь на канал ❤️"
    )

    publish(message)

    history.append(first["link"])
    save_history(history)

    print("Публикация успешно отправлена!")

if __name__ == "__main__":
    main()
