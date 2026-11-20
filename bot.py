import os
import json
import html
import re
import random
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import urljoin

# =====================================================
# НАСТРОЙКИ
# =====================================================

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHANNEL = "@znaehti"

HISTORY_FILE = "posted.json"
TRACKING_FILE = "tracking.json"

BOT_NAME = "FACT BOT"
MAX_DESCRIPTION = 850
FACT_HOUR_UTC = 8
USER_AGENT = "Mozilla/5.0 FactBot/6.0"

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

DAILY_FACTS = [
    "У осьминога три сердца. Два перекачивают кровь через жабры, а третье — к остальным органам.",
    "На Венере сутки длиннее года: планета вращается вокруг своей оси медленнее, чем обращается вокруг Солнца.",
    "Пчёлы могут сообщать другим пчёлам направление и расстояние до источника пищи с помощью особого танца.",
    "Свет от Солнца достигает Земли примерно за 8 минут и 20 секунд.",
    "Акулы появились на Земле раньше первых деревьев.",
    "У жирафа, как и у человека, семь шейных позвонков.",
    "Самая большая пустыня Земли — Антарктида.",
    "У коал уникальные отпечатки пальцев.",
    "Молния может нагревать воздух вокруг себя до температуры выше температуры поверхности Солнца.",
    "На Луне следы астронавтов могут сохраняться очень долго из-за отсутствия ветра и дождя.",
    "Синий кит — самое крупное известное животное, когда-либо жившее на Земле.",
    "В космосе звук не распространяется так, как на Земле, потому что для него нужна материальная среда.",
]


# =====================================================
# ФАЙЛЫ И ДАННЫЕ
# =====================================================

def load_json(filename, default):
    try:
        with open(filename, "r", encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(filename, data):
    temporary = filename + ".tmp"
    with open(temporary, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    os.replace(temporary, filename)


def load_history():
    history = load_json(HISTORY_FILE, [])
    return history if isinstance(history, list) else []


def save_history(history):
    # Сохраняем прежний формат posted.json — список ссылок.
    save_json(HISTORY_FILE, history[-1000:])



def load_tracking():
    try:
        with open("tracking.json", "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return {
            "total": 0,
            "sources": {},
            "categories": {},
            "last_daily_fact": ""
        }


def save_tracking(data):
    try:
        with open("tracking.json", "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Ошибка сохранения статистики: {e}")

        
    defaults = {
        "total_posts": 0,
        "news_posts": 0,
        "daily_facts": 0,
        "sources": {},
        "categories": {},
        "last_daily_fact": "",
        "subscribers": None,
        "previous_subscribers": None,
        "subscriber_change": None,
        "last_updated": "",
    }

    for key, value in defaults.items():
        data.setdefault(key, value)

    return data


# =====================================================
# ЗАГРУЗКА И ОБРАБОТКА
# =====================================================

def fetch(url, timeout=25):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def clean_text(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


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

    translated_chunks = []

    for chunk in split_text(text):
        params = urllib.parse.urlencode({
            "q": chunk,
            "langpair": "en|ru"
        })
        url = "https://api.mymemory.translated.net/get?" + params
        request = urllib.request.Request(
            url,
            headers={"User-Agent": USER_AGENT}
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
            raise RuntimeError("Сервис перевода вернул некорректный результат")

        translated_chunks.append(translated)
        time.sleep(0.5)

    return " ".join(translated_chunks)


# =====================================================
# КАТЕГОРИИ
# =====================================================

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


# =====================================================
# ИЗОБРАЖЕНИЯ ИЗ RSS И СТРАНИЦ СТАТЕЙ
# =====================================================

def find_image_in_html(fragment, base_url):
    if not fragment:
        return ""

    patterns = [
        r'<img[^>]+src=["\']([^"\']+)["\']',
        r'<img[^>]+data-src=["\']([^"\']+)["\']',
        r'<img[^>]+data-original=["\']([^"\']+)["\']',
    ]

    for pattern in patterns:
        match = re.search(pattern, fragment, re.IGNORECASE)
        if match:
            candidate = urljoin(base_url, html.unescape(match.group(1)))
            if candidate.startswith(("http://", "https://")):
                return candidate

    return ""


def get_rss_image(item, article_link):
    for element in item.iter():
        name = element.tag.split("}")[-1].lower()

        if name in ("thumbnail", "content"):
            candidate = element.attrib.get("url") or element.attrib.get("href")
            mime_type = element.attrib.get("type", "").lower()

            if candidate and (
                name == "thumbnail"
                or mime_type.startswith("image/")
            ):
                candidate = urljoin(article_link, candidate)
                if candidate.startswith(("http://", "https://")):
                    return candidate

        if name == "enclosure":
            candidate = element.attrib.get("url", "")
            mime_type = element.attrib.get("type", "").lower()

            if candidate and (mime_type.startswith("image/") or not mime_type):
                candidate = urljoin(article_link, candidate)
                if candidate.startswith(("http://", "https://")):
                    return candidate

        if name in ("description", "summary", "encoded"):
            candidate = find_image_in_html(
                "".join(element.itertext()),
                article_link
            )
            if candidate:
                return candidate

    return ""


def get_page_image(article_link):
    """Ищет og:image на странице только выбранной статьи."""
    try:
        page = fetch(article_link, timeout=12).decode(
            "utf-8",
            errors="ignore"
        )

        meta_tags = re.findall(
            r"<meta\b[^>]*>",
            page,
            flags=re.IGNORECASE
        )

        for tag in meta_tags:
            property_match = re.search(
                r"""(?:property|name)\s*=\s*["']([^"']+)["']""",
                tag,
                re.IGNORECASE
            )
            content_match = re.search(
                r"""content\s*=\s*["']([^"']+)["']""",
                tag,
                re.IGNORECASE
            )

            if not property_match or not content_match:
                continue

            property_name = property_match.group(1).lower()
            if property_name in ("og:image", "twitter:image"):
                candidate = urljoin(
                    article_link,
                    html.unescape(content_match.group(1))
                )
                if candidate.startswith(("http://", "https://")):
                    return candidate

    except Exception as error:
        print(f"Не удалось получить картинку страницы: {error}")

    return ""


# =====================================================
# ЧТЕНИЕ RSS
# =====================================================

def get_articles():
    articles = []

    for source, feed_url in FEEDS.items():
        try:
            root = ET.fromstring(fetch(feed_url))

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

                    elif name in ("description", "summary", "content", "encoded"):
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
                        "source": source,
                        "image": get_rss_image(item, link),
                    })

            print(f"{source}: лента обработана")

        except Exception as error:
            print(f"Ошибка RSS {source}: {error}")

    return articles


# =====================================================
# TELEGRAM
# =====================================================

def telegram_api(method, data):
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    encoded = urllib.parse.urlencode(data).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=encoded,
        headers={"User-Agent": USER_AGENT}
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.loads(response.read().decode("utf-8"))

    if not result.get("ok"):
        raise RuntimeError(f"Ошибка Telegram: {result}")

    return result.get("result")


def publish_text(message):
    telegram_api("sendMessage", {
        "chat_id": CHANNEL,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    })


def publish_photo(image_url, caption):
    telegram_api("sendPhoto", {
        "chat_id": CHANNEL,
        "photo": image_url,
        "caption": caption,
        "parse_mode": "HTML",
    })


def publish_article(article, message):
    image_url = article.get("image", "")

    # Telegram ограничивает подпись к фото 1024 символами.
    if image_url and len(message) <= 1000:
        try:
            publish_photo(image_url, message)
            print("Публикация с изображением отправлена!")
            return
        except Exception as error:
            print(f"Не удалось отправить фото: {error}")

    publish_text(message)
    print("Текстовая публикация отправлена!")


# =====================================================
# СОЗДАНИЕ НОВОСТНОГО ПОСТА
# =====================================================

def create_post(article):
    emoji, category, hashtag = get_category(article["source"])

    title_ru = translate_to_russian(article["title"])
    description = article["description"][:MAX_DESCRIPTION]
    description_ru = translate_to_russian(description) if description else ""

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
        f'📰 <a href="{link}">Читать первоисточник</a>\n'
        f"📡 Источник: {source}\n\n"
        f"{hashtag} #FactBot\n"
        "🧠 <b>Узнавай больше каждый день!</b>"
    )

    return message


# =====================================================
# СТАТИСТИКА КАНАЛА
# =====================================================

def get_member_count():
    try:
        result = telegram_api("getChatMemberCount", {
            "chat_id": CHANNEL
        })
        return int(result)
    except Exception as error:
        print(f"Не удалось получить число подписчиков: {error}")
        return None


def update_subscriber_stats(tracking):
    count = get_member_count()

    if count is None:
        return

    previous = tracking.get("subscribers")
    tracking["previous_subscribers"] = previous
    tracking["subscribers"] = count

    if previous is not None:
        tracking["subscriber_change"] = count - previous
    else:
        tracking["subscriber_change"] = 0


def record_news_stats(tracking, article):
    _, category, _ = get_category(article["source"])

    tracking["total_posts"] += 1
    tracking["news_posts"] += 1

    tracking["sources"][article["source"]] = (
        tracking["sources"].get(article["source"], 0) + 1
    )

    tracking["categories"][category] = (
        tracking["categories"].get(category, 0) + 1
    )


# =====================================================
# ФАКТ ДНЯ
# =====================================================

def publish_daily_fact(tracking):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if tracking.get("last_daily_fact") == today:
        print("Факт дня сегодня уже публиковался.")
        return

    fact = random.choice(DAILY_FACTS)

    message = (
        "━━━━━━━━━━━━━━━━━━\n"
        "⚡ <b>FACT BOT</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "🧠 <b>ФАКТ ДНЯ</b>\n\n"
        f"💡 {html.escape(fact)}\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🌍 Мир полон удивительного!\n\n"
        "#ФактДня #интересное #FactBot"
    )

    publish_text(message)

    tracking["last_daily_fact"] = today
    tracking["daily_facts"] += 1
    tracking["total_posts"] += 1

    print("Факт дня опубликован!")


# =====================================================
# ОСНОВНОЙ ЗАПУСК
# =====================================================

def main():
    if not TOKEN:
        raise RuntimeError("Не найден секрет TELEGRAM_BOT_TOKEN")

    history = load_history()
    tracking = load_tracking()

    now = datetime.now(timezone.utc)

    print("===================================")
    print("FACT BOT — запуск")
    print("Время UTC:", now.strftime("%Y-%m-%d %H:%M"))
    print("===================================")

    # Получаем новости
    articles = get_articles()
    print(f"Всего получено материалов: {len(articles)}")

    unseen = [
        article for article in articles
        if article["link"] not in history
    ]

    random.shuffle(unseen)

    published_news = False

    # Пробуем до 15 новых материалов, чтобы пережить ошибки перевода.
    for article in unseen[:15]:
        try:
            print("Источник:", article["source"])
            print("Заголовок:", article["title"])

            # Если RSS не дал изображение, ищем его на странице статьи.
            if not article.get("image"):
                article["image"] = get_page_image(article["link"])

            message = create_post(article)
            publish_article(article, message)

            # Записываем ссылку только после успешной отправки.
            history.append(article["link"])
            save_history(history)

            record_news_stats(tracking, article)
            published_news = True

            print("Новость успешно опубликована!")
            break

        except Exception as error:
            print(f"Ошибка материала: {error}")
            continue

    if not published_news:
        print("В этом запуске новость не опубликована.")

    # Факт дня публикуется при первом запуске после 08:00 UTC.
    if now.hour >= FACT_HOUR_UTC:
        try:
            publish_daily_fact(tracking)
        except Exception as error:
            print(f"Ошибка публикации факта дня: {error}")

    # Обновляем статистику подписчиков.
    update_subscriber_stats(tracking)

    tracking["last_updated"] = datetime.now(timezone.utc).isoformat()

    save_tracking(tracking)

    print("===================================")
    print("ИТОГОВАЯ СТАТИСТИКА")
    print("Всего публикаций:", tracking["total_posts"])
    print("Новостей:", tracking["news_posts"])
    print("Фактов дня:", tracking["daily_facts"])
    print("Подписчиков:", tracking["subscribers"])
    print("Изменение подписчиков:", tracking["subscriber_change"])
    print("===================================")


if __name__ == "__main__":
    main()
