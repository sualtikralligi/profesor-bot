import os
import re
import logging
import threading
import urllib.parse

import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
from flask import Flask
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, filters

BOT_TOKEN = os.environ.get("BOT_TOKEN")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7"
}

CATEGORY_URLS = [
    # Tatlı Su Kategorileri
    "https://www.akvaryum.com/malawi_cichlidleri_kategorisi_3.asp",
    "https://www.akvaryum.com/tanganyika_cichlidleri_kategorisi_2.asp",
    "https://www.akvaryum.com/victoria_cichlidleri_kategorisi_5.asp",
    "https://www.akvaryum.com/guney_amerika_cichlidleri_kategorisi_4.asp",
    "https://www.akvaryum.com/orta_amerika_cichlidleri_kategorisi_88.asp",
    "https://www.akvaryum.com/canli_doguranlar_kategorisi_5.asp",
    "https://www.akvaryum.com/characins_(tetra)_kategorisi_10.asp",
    "https://www.akvaryum.com/cyprinids_(sazansilar)_kategorisi_7.asp",
    "https://www.akvaryum.com/labirentliler_kategorisi_6.asp",
    "https://www.akvaryum.com/kedibaliklari_kategorisi_58.asp",
    "https://www.akvaryum.com/killifish_kategorisi_9.asp",
    "https://www.akvaryum.com/gokkusaklari_kategorisi_11.asp",
    "https://www.akvaryum.com/omurgasizlar_kategorisi_8.asp",
    "https://www.akvaryum.com/diğer_tatli_su_canlilari_kategorisi_12.asp",
    # Bitkiler & Deniz & Diğer
    "https://www.akvaryum.com/Bitkiler/",
    "https://www.akvaryum.com/Deniz/",
    "https://www.akvaryum.com/surungenler_kategorisi_35.asp",
    "https://www.akvaryum.com/hastaliklar_kategorisi_23.asp"
]

FIELD_LABELS = {
    "Latince Adı": "Latince Adı",
    "Coğrafik Kökeni": "Coğrafi Kökeni",
    "Yaşam Alanı": "Yaşam Alanı",
    "Beslenme Biçimi": "Beslenme",
    "Davranış Biçimi": "Davranışı",
    "Kendi Türlerine Davranışı": "Kendi Türüne Davranışı",
    "Yüzme Seviyesi": "Yüzme Seviyesi",
    "Cinsiyet Ayrımı": "Cinsiyet Ayrımı",
    "Üreme": "Üreme",
    "Sıcaklık": "Sıcaklık",
    "En Fazla Büyüdüğü Boy": "En Fazla Büyüdüğü Boy",
    "En Az Akvaryum Hacmi": "Min. Akvaryum Hacmi",
    "Su Sertliği": "Su Sertliği",
    "pH": "pH",
    "Zorluk Seviyesi": "Zorluk Seviyesi",
    "Genel Yorum": "Genel Yorum",
}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


def fetch_ddg_image(query: str):
    """DuckDuckGo üzerinden başlığa uygun ilk görseli çeker."""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.images(f"{query} akvaryum", max_results=1))
            if results:
                return results[0]["image"]
    except Exception as e:
        logger.warning("DuckDuckGo görsel çekme hatası: %s", e)
    return None


def find_fish_url_direct(fish_name: str):
    query = fish_name.lower().strip()
    words = query.split()

    candidates = []

    for cat_url in CATEGORY_URLS:
        try:
            resp = requests.get(cat_url, headers=HEADERS, timeout=8)
            if resp.status_code != 200:
                continue
            
            resp.encoding = resp.apparent_encoding or "windows-1254"
            soup = BeautifulSoup(resp.text, "html.parser")

            for a in soup.find_all("a", href=True):
                text = a.get_text(" ", strip=True).lower()
                href = a["href"]

                if text and all(w in text for w in words):
                    if href.endswith(".asp") and ("kategorisi" not in href):
                        if not href.startswith("http"):
                            href = urllib.parse.urljoin("https://www.akvaryum.com/", href)
                        
                        if text == query:
                            return href

                        candidates.append((len(text), href))
        except Exception as e:
            logger.warning("Kategori taranırken hata (%s): %s", cat_url, e)

    if candidates:
        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]

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
    title = title_tag.get_text(strip=True) if title_tag else "Canlı / Konu Detayı"

    page_text_blocks = soup.find_all(["li", "p", "div", "span", "b", "strong", "td", "tr"])
    data = {}
    for label in FIELD_LABELS:
        for block in page_text_blocks:
            text = block.get_text(" ", strip=True)
            if text.startswith(label + ":") or text.startswith(label + " :"):
                value = text.split(":", 1)[1].strip()
                if value and len(value) < 500:
                    data[label] = value
                break

    # Resim akvaryum.com yerine DuckDuckGo üzerinden bulunuyor
    image_url = fetch_ddg_image(title)

    return {
        "title": title,
        "data": data,
        "image_url": image_url,
        "source_url": url,
    }


def format_reply(info: dict) -> str:
    lines = [f"📖 *{info['title'].upper()} — BİLGİ KARTI*"]

    for label, display_name in FIELD_LABELS.items():
        if label in info["data"]:
            value = info["data"][label]
            if label == "Genel Yorum" and len(value) > 400:
                value = value[:400].rsplit(" ", 1)[0] + "…"
            lines.append(f"*{display_name}:* {value}")

    lines.append("\n💡 *Profesör Bilgi Sistemi*")
    return "\n".join(lines)


def extract_fish_name(text: str, bot_username: str = None):
    clean_text = text

    if bot_username:
        clean_text = re.sub(rf"@{re.escape(bot_username)}", "", clean_text, flags=re.IGNORECASE)

    clean_text = re.sub(r"@profesö[rr]|@profeso[rr]", "", clean_text, flags=re.IGNORECASE)
    clean_text = re.sub(r"@[A-Za-z0-9_]+", "", clean_text)
    clean_text = clean_text.strip(" :,-_").strip()

    return clean_text if clean_text else None


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message or not message.text:
        return

    bot_username = context.bot.username if context.bot else None

    if message.chat.type in ["group", "supergroup"]:
        is_mentioned = False
        if bot_username and f"@{bot_username.lower()}" in message.text.lower():
            is_mentioned = True
        elif "@profesör" in message.text.lower() or "@profesor" in message.text.lower():
            is_mentioned = True
        
        if not is_mentioned:
            return

    fish_name = extract_fish_name(message.text, bot_username)
    if not fish_name:
        return

    await context.bot.send_chat_action(chat_id=message.chat_id, action="typing")

    url = find_fish_url_direct(fish_name)
    if not url:
        example_handle = f"@{bot_username}" if bot_username else "@profesör"
        await message.reply_text(
            f"❌ Veritabanımızda “{fish_name}” ile eşleşen bir kayıt bulunamadı.\n"
            f"İsmi kontrol edip tekrar dener misin? (Örn: {example_handle} Türün İsmi)"
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
    bot_username = context.bot.username if context.bot else "profesör"
    await update.effective_message.reply_text(
        "Merhaba! Ben Profesör 🐠\n"
        f"Gruba `@{bot_username} <canlı adı>` yazarsan sana veritabanımızdan bilgi kartı getiririm.\n"
        f"Örnek: @{bot_username} neon tetra"
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
