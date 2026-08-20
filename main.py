import os
import logging
import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from aiohttp import web
import asyncio

# Telegram Bot Token
TOKEN = "7920321173:AAF2AE2DIbsFU7R4mVRwBC8jrpwLnhkNgXI"

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def bilgi_servisi_ara(balik_adi):
    try:
        url = f"https://www.akvaryum.com/Arama/?q={balik_adi}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            return "⚠️ Sunucuya şu an ulaşılamıyor, lütfen kısa bir süre sonra tekrar deneyin."

        soup = BeautifulSoup(response.text, 'html.parser')
        a_tag = soup.find('a', href=lambda href: href and 'asp' in href)
        
        if not a_tag:
            return f"❌ Veritabanımızda **{balik_adi}** ile ilgili doğrudan bir bilgi kaydı bulunamadı. Lütfen ismi kontrol edip tekrar deneyin."
        
        detay_url = "https://www.akvaryum.com/" + a_tag['href']
        detay_res = requests.get(detay_url, headers=headers, timeout=10)
        detay_soup = BeautifulSoup(detay_res.text, 'html.parser')
        
        icerik = detay_soup.find('div', id='icerik') or detay_soup.find('body')
        
        if not icerik:
            return "❌ İlgili türe ait bilgi kartı oluşturulamadı."

        metin = icerik.get_text(separator=' ', strip=True)[:650]
        
        return (
            f"📖 **{balik_adi.upper()} — BİLGİ KARTI**\n\n"
            f"{metin}...\n\n"
            f"💡 *İzmir Akvaryum Hobicileri Özel Bilgi Servisi*"
        )

    except Exception as e:
        return "⚠️ Sistemde geçici bir aksama yaşandı. Lütfen daha sonra tekrar deneyin."

async def mesaj_yakala(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    mesaj = update.message.text.strip()
    
    if mesaj.lower().startswith("@profesör") or mesaj.lower().startswith("@profesor"):
        parcalar = mesaj.split(maxsplit=1)
        if len(parcalar) < 2:
            await update.message.reply_text("Lütfen bilgi almak istediğin canlı adını girin. Örn: `@profesör betta`", parse_mode="Markdown")
            return

        balik_adi = parcalar[1]
        await update.message.reply_text(f"🔍 **{balik_adi}** bilgileri sistemden sorgulanıyor...")
        
        cevap = bilgi_servisi_ara(balik_adi)
        await update.message.reply_text(cevap, parse_mode="Markdown", disable_web_page_preview=True)

async def handle_ping(request):
    return web.Response(text="Bot Aktif ve Calisiyor!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

async def main():
    # Web sunucusunu başlat (Render için gerekli)
    await start_web_server()
    
    # Telegram botunu başlat
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), mesaj_yakala))
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    
    # Çalışır durumda tut
    await asyncio.Event().wait()

if __name__ == '__main__':
    asyncio.run(main())
