import asyncio
import os
from pyrogram import Client, filters

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

if __name__ == "__main__":
    asyncio.run(main())
