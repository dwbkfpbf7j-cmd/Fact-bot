import os
import json
import html
import re
import random
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
        headers={"User-Agent": "Mozilla/5.0 FactBot/2.0"}
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read()


def clean_text(text):
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

                title = ""
                link = ""
                description = ""

                for child in item:
                    name = child.tag.split("}")[-1].lower()

                    if name == "title":
                        title = "".join(child.itertext()).strip()

                    elif name == "link":
                        link = (
                            child.attrib.get("href", "")
                            or (child.text or "").strip()
                        )

                    elif name in ("description", "summary", "content"):
                        description = "".join(child.itertext()).strip()

                title = clean_text(title)
                description = clean_text(description)

                if title and link.startswith("http"):
                    articles.append({
                        "title": title,
                        "description": description,
                        "link": link,
                        "source": source
                    })

            print(f"{source}: лента обработана")

        except Exception as error:
            print(f"Ошибка RSS {source}: {error}")

    return articles


def translate_to_russian(text):
    if not text:
        return ""

    url = "https://translate.googleapis.com/translate_a/single"

    params = urllib.parse.urlencode({
        "client": "gtx",
        "sl": "auto",
        "tl": "ru",
        "dt": "t",
        "q": text[:3000]
    })

    request = urllib.request.Request(
        f"{url}?{params}",
        headers={"User-Agent": "Mozilla/5.0"}
    )

    with urllib.request.urlopen(request, timeout=25) as response:
        result = json.loads(response.read().decode("utf-8"))

    translated = "".join(
        part[0]
        for part in result[0]
        if part and part[0]
    )

    if not translated:
        raise RuntimeError("Не удалось перевести материал")

    return translated.strip()


def load_history():
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as file:
        json.dump(history[-1000:], file, ensure_ascii=False, indent=2)


def publish(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    data = urllib.parse.urlencode({
        "chat_id": CHANNEL,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": "false"
    }).encode()

    request = urllib.request.Request(url, data=data)

    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.loads(response.read().decode())

    if not result.get("ok"):
        raise RuntimeError(f"Ошибка Telegram: {result}")


def main():
    if not TOKEN:
        raise RuntimeError("Не найден секрет TELEGRAM_BOT_TOKEN")

    history = load_history()
    articles = get_articles()

    print(f"Всего получено материалов: {len(articles)}")

    unseen = [
        article for article in articles
        if article["link"] not in history
    ]

    if not unseen:
        raise RuntimeError("Новых материалов нет")

    random.shuffle(unseen)

    article = unseen[0]

    print(f"Выбран источник: {article['source']}")
    print(f"Заголовок: {article['title']}")

    title_ru = translate_to_russian(article["title"])

    description_ru = ""
    if article["description"]:
        description_ru = translate_to_russian(
            article["description"][:2500]
        )

    title_ru = html.escape(title_ru)
    description_ru = html.escape(description_ru)
    source = html.escape(article["source"])
    link = html.escape(article["link"], quote=True)

    message = (
        "🔎 <b>А знаете ли вы?</b>\n\n"
        f"<b>{title_ru}</b>\n\n"
    )

    if description_ru:
        message += f"{description_ru[:2500]}\n\n"

    message += (
        f"📰 <b>Источник:</b> "
        f'<a href="{link}">{source}</a>\n\n'
        "Подписывайтесь на канал ❤️"
    )

    publish(message)

    history.append(article["link"])
    save_history(history)

    print("Публикация успешно отправлена!")


if __name__ == "__main__":
    main()
