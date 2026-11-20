
import os
import json
import html
import re
import random
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHANNEL = "@znaehti"
HISTORY_FILE = "posted.json"

BOT_NAME = "FACT BOT"
MAX_DESCRIPTION = 850

FEEDS = {
    # КОСМОС
    "NASA — Космос": "https://www.nasa.gov/feed/",
    "NASA — Новости": "https://www.nasa.gov/rss/breaking_news.rss",
    "ScienceDaily — Космос": "https://www.sciencedaily.com/rss/space_time.xml",

    # ЖИВОТНЫЕ
    "ScienceDaily — Животные": "https://www.sciencedaily.com/rss/plants_animals.xml",
    "Smithsonian — Природа": "https://www.smithsonianmag.com/rss/science-nature/",

    # АВТОМОБИЛИ
    "Car and Driver": "https://www.caranddriver.com/rss/news.xml",
    "The Drive": "https://www.thedrive.com/feed",
    "Autoblog": "https://www.autoblog.com/.rss/feed/3d70fbb5-ef5e-44f3-a547-e60939496e82.xml",

    # ПРИРОДА И ПЛАНЕТА
    "NOAA — Планета": "https://www.noaa.gov/news/rss.xml",
    "ScienceDaily — Климат": "https://www.sciencedaily.com/rss/earth_climate.xml",

    # НАУКА И ЗДОРОВЬЕ
    "ScienceDaily — Наука": "https://www.sciencedaily.com/rss/all.xml",
    "ScienceDaily — Здоровье": "https://www.sciencedaily.com/rss/health_medicine.xml",

    # ТЕХНОЛОГИИ
    "ScienceDaily — Технологии": "https://www.sciencedaily.com/rss/computers_math.xml",

    # ИСТОРИЯ
    "Smithsonian — История": "https://www.smithsonianmag.com/rss/history/",
    "BBC — Наука и природа": "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
}


def fetch(url):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 FactBot/5.0"}
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
                        href = child.attrib.get("href", "")
                        rel = child.attrib.get("rel", "alternate")

                        if href and rel == "alternate":
                            link = href
                        elif not href and child.text:
                            link = child.text.strip()

                    elif name in ("description", "summary", "content"):
                        value = "".join(child.itertext()).strip()

                        if len(value) > len(description):
                            description = value

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


def split_text(text, max_bytes=450):
    chunks = []
    current = ""

    for word in text.split():
        candidate = (current + " " + word).strip()

        if len(candidate.encode("utf-8")) > max_bytes and current:
            chunks.append(current)
            current = word
        else:
            current = candidate

    if current:
        chunks.append(current)

    return chunks


def translate_to_russian(text):
    if not text:
        return ""

    chunks = split_text(text)
    translated_chunks = []

    for chunk in chunks:
        params = urllib.parse.urlencode({
            "q": chunk,
            "langpair": "en|ru"
        })

        url = "https://api.mymemory.translated.net/get?" + params

        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 FactBot/5.0"}
        )

        with urllib.request.urlopen(request, timeout=25) as response:
            result = json.loads(response.read().decode("utf-8"))

        if result.get("responseStatus") != 200:
            raise RuntimeError("Ошибка сервиса перевода")

        translated = (
            result.get("responseData", {})
            .get("translatedText", "")
            .strip()
        )

        if not translated or "MYMEMORY WARNING" in translated.upper():
            raise RuntimeError("Некорректный перевод")

        translated_chunks.append(translated)
        time.sleep(0.5)

    return " ".join(translated_chunks)


def get_category(source):
    source = source.lower()

    if any(word in source for word in ("nasa", "космос", "space")):
        return "🌌", "КОСМОС", "#космос"

    if any(word in source for word in ("живот", "природа", "animals")):
        return "🐾", "ЖИВОТНЫЕ И ПРИРОДА", "#природа"

    if any(word in source for word in ("car", "drive", "autoblog")):
        return "🚗", "АВТОМИР", "#авто"

    if any(word in source for word in ("климат", "noaa", "планета")):
        return "🌍", "НАША ПЛАНЕТА", "#планета"

    if any(word in source for word in ("здоров", "health", "medicine")):
        return "🧬", "ЗДОРОВЬЕ И НАУКА", "#наука"

    if any(word in source for word in ("технолог", "computers", "math")):
        return "⚡", "ТЕХНОЛОГИИ", "#технологии"

    if any(word in source for word in ("история", "history")):
        return "🏛", "ИСТОРИЯ", "#история"

    return "🔬", "ИНТЕРЕСНЫЙ ФАКТ", "#факты"


def load_history():
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as file:
            return json.load(file)

    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as file:
        json.dump(
            history[-1000:],
            file,
            ensure_ascii=False,
            indent=2
        )


def publish(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    data = urllib.parse.urlencode({
        "chat_id": CHANNEL,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true"
    }).encode()

    request = urllib.request.Request(url, data=data)

    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.loads(response.read().decode())

    if not result.get("ok"):
        raise RuntimeError(f"Ошибка Telegram: {result}")


def create_post(article):
    emoji, category, hashtag = get_category(article["source"])

    title_ru = translate_to_russian(article["title"])

    description = article["description"][:MAX_DESCRIPTION]
    description_ru = ""

    if description:
        description_ru = translate_to_russian(description)

    title_ru = html.escape(title_ru)
    description_ru = html.escape(description_ru)
    source = html.escape(article["source"])
    link = html.escape(article["link"], quote=True)

    message = (
        "━━━━━━━━━━━━━━━━━━\n"
        f"⚡ <b>{BOT_NAME}</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"{emoji} <b>{category}</b>\n\n"
        f"<b>{title_ru}</b>\n\n"
    )

    if description_ru:
        message += description_ru + "\n\n"

    message += (
        "━━━━━━━━━━━━━━━━━━\n"
        f"📰 <a href=\"{link}\">Читать первоисточник</a>\n"
        f"📡 Источник: {source}\n\n"
        f"{hashtag} #FactBot\n"
        "🧠 <b>Узнавай больше каждый день!</b>"
    )

    return message


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

    for article in unseen[:15]:
        try:
            print(f"Пробуем источник: {article['source']}")
            print(f"Заголовок: {article['title']}")

            message = create_post(article)

            publish(message)

            history.append(article["link"])
            save_history(history)

            print("Публикация успешно отправлена!")
            return

        except Exception as error:
            print(f"Ошибка материала: {error}")
            continue

    raise RuntimeError(
        "Не удалось перевести и опубликовать ни один материал"
    )


if __name__ == "__main__":
    main()
