import asyncio
import os
import sys
import threading
from flask import Flask
from pyrogram import Client, filters

# ========== تنظیم Event Loop برای پایتون ۳.۱۴ ==========
if sys.version_info >= (3, 14):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

# ========== ربات تلگرام ==========
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

app = Client("test_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@app.on_message(filters.private)
async def echo(client, message):
    print(f"📩 پیام دریافت شد: {message.text}")
    await message.reply_text(f"✅ پیام شما: {message.text}")

async def main():
    print("🤖 ربات تست روشن شد...")
    await app.start()
    print("✅ ربات به تلگرام متصل شد.")
    await asyncio.Event().wait()

def run_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main())

# ========== Flask برای باز کردن پورت ==========
flask_app = Flask(__name__)

@flask_app.route('/')
@flask_app.route('/health')
def health():
    return "ربات تست روشن است!", 200

def run_flask():
    port = int(os.environ.get('PORT', 8000))
    flask_app.run(host='0.0.0.0', port=port)

# ========== اجرا ==========
if __name__ == "__main__":
    # ربات در یک Thread جداگانه
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Flask در Thread اصلی
    run_flask()
