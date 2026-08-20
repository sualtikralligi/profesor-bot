import os
import logging
from telegram.ext import ApplicationBuilder, MessageHandler, filters
from aiohttp import web
import asyncio

# Token
TOKEN = "7920321173:AAF2AE2DIbsFU7R4mVRwBC8jrpwLnhkNgXI"

# Basit bir fonksiyon (İçeriği koruduk)
async def handle_ping(request):
    return web.Response(text="Bot Aktif ve Çalışıyor!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    # Render'ın verdiği portu kullan
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Web sunucusu {port} portunda başlatıldı.")

# Botun ana mantığı buraya gelecek (Daha önceki mesaj yakala fonksiyonunu aynen koru)
# (Buraya önceki main.py'daki `bilgi_servisi_ara` ve `mesaj_yakala` fonksiyonlarını yapıştır, 
# sadece en alttaki `if __name__ == '__main__'` kısmını aşağıdakine göre değiştir.)

if __name__ == '__main__':
    # Önce web sunucusunu, sonra botu başlat
    loop = asyncio.get_event_loop()
    loop.create_task(start_web_server())
    
    app = ApplicationBuilder().token(TOKEN).build()
    # ... handler'ları ekle ...
    app.run_polling()
