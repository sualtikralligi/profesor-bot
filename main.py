import os
import re
import logging
import threading
import urllib.parse

import requests
from bs4 import BeautifulSoup
from flask import Flask
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, filters

BOT_TOKEN = os.environ.get("BOT_TOKEN")
TRIGGER_WORDS = ["@profesör", "@profesor"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}

FIELD_LABELS = {
    "Latince Adı": "Latince Adı",
    "Coğrafik Kökeni": "Kökeni",
    "Beslenme Biçimi": "Beslenme",
    "Davranış Biçimi": "Davranışı",
    "Kendi Türlerine Davranışı": "Kendi Türüne Davranışı",
    "Yüzme Seviyesi": "Yüzme Seviyesi",
    "Sıcaklık": "Sıcaklık",
    "En Fazla Büyüdüğü Boy": "Maks. Boy",
    "En Az Akvaryum Hacmi": "Min. Akvaryum Hacmi",
    "Su Sertliği": "Su Sertliği",
    "pH": "pH",
    "Zorluk Seviyesi": "Zorluk Seviyesi",
}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


def find_fish_url(fish_name: str):
    query = f"site:akvaryum.com {fish_name}"
    try:
        resp = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers=HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning("Arama isteği başarısız: %s", e)
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    for a in soup.select("a.result__a"):
        href = a.get("href", "")
        if "uddg=" in href:
            parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
            href = parsed.get("uddg", [href])[0]

        if "akvaryum.com" in href and re.search(r"tatlisur_\d+_\d+\.asp", href):
            return href

    return None


def parse_fish_page(url: str):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning("Kayıt çekilemedi: %s", e)
        return None

    resp.encoding = resp.apparent_encoding or "windows-1254"
    soup = BeautifulSoup(resp.text, "html.parser")

    title_tag = soup.find("h1") or soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else fish_name_fallback(url)

    page_text_blocks = soup.find_all(["li", "p", "div", "span", "b", "strong"])
    data = {}
    for label in FIELD_LABELS:
        for block in page_text_blocks:
            text = block.get_text(" ", strip=True)
            if text.startswith(label + ":") or text.startswith(label + " :"):
                value = text.split(":", 1)[1].strip()
                if value:
                    data[label] = value
                break

    comment = None
    for block in page_text_blocks:
        text = block.get_text(" ", strip=True)
        if text.startswith("Genel Yorum:"):
            comment = text.split(":", 1)[1].strip()
            break

    image_url = None
    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        image_url = og_image["content"]
    else:
        img_tag = soup.find("img", src=re.compile(r"foto_arsiv"))
        if img_tag and img_tag.get("src"):
            image_url = urllib.parse.urljoin(url, img_tag["src"])

    return {
        "title": title,
        "data": data,
        "comment": comment,
        "image_url": image_url,
        "source_url": url,
    }


def fish_name_fallback(url: str) -> str:
    slug = url.rstrip("/").split("/")[-1]
    slug = re.sub(r"_tatlisur_\d+_\d+\.asp$", "", slug)
    return slug.replace("_", " ").title()


def format_reply(info: dict) -> str:
    lines = [f"📖 *{info['title'].upper()} — BİLGİ KARTI*"]

    for label, display_name in FIELD_LABELS.items():
        if label in info["data"]:
            lines.append(f"*{display_name}:* {info['data'][label]}")

    if info.get("comment"):
        comment = info["comment"]
        if len(comment) > 500:
            comment = comment[:500].rsplit(" ", 1)[0] + "…"
        lines.append(f"\n_{comment}_")

    lines.append("\n💡 *Profesör Bilgi Sistemi*")
    return "\n".join(lines)


def extract_fish_name(text: str):
    lowered = text.lower()
    for trigger in TRIGGER_WORDS:
        idx = lowered.find(trigger)
        if idx != -1:
            after = text[idx + len(trigger):].strip()
            after = after.lstrip(":,-").strip()
            if after:
                return after
    return None


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message or not message.text:
        return

    fish_name = extract_fish_name(message.text)
    if not fish_name:
        return

    await context.bot.send_chat_action(chat_id=message.chat_id, action="typing")

    url = find_fish_url(fish_name)
    if not url:
        await message.reply_text(
            f"❌ Veritabanımızda “{fish_name}” ile eşleşen bir kayıt bulunamadı.\n"
            f"İsmi kontrol edip tekrar dener misin? (Örn: @profesör betta splendens)"
        )
        return

    info = parse_fish_page(url)
    if not info:
        await message.reply_text("⚠️ Kayda ulaşıldı ama bilgi kartı oluşturulurken bir sorun oldu, tekrar dener misin?")
        return

    reply_text = format_reply(info)

    try:
        if info.get("image_url"):
            await message.reply_photo(
                photo=info["image_url"],
                caption=reply_text,
                parse_mode=ParseMode.MARKDOWN,
            )
        else:
            await message.reply_text(reply_text, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
    except Exception as e:
        logger.warning("Yanıt gönderilemedi, düz metne düşülüyor: %s", e)
        await message.reply_text(reply_text, disable_web_page_preview=True)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "Merhaba! Ben Profesör 🐠\n"
        "Gruba `@profesör <canlı adı>` yazarsan sana veritabanımızdan bilgi kartı getiririm.\n"
        "Örnek: @profesör neon tetra"
    )


flask_app = Flask(__name__)


@flask_app.route("/")
def health_check():
    return "Profesör bot ayakta 🐠", 200


def run_flask():
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN ortam değişkeni tanımlı değil!")

    threading.Thread(target=run_flask, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot polling başlatılıyor...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
