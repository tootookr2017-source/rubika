import os
import threading
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ========== Flask ==========
flask_app = Flask(__name__)

@flask_app.route('/')
@flask_app.route('/health')
def health():
    return "ربات روشن است!", 200

def run_flask():
    port = int(os.environ.get('PORT', 8000))
    flask_app.run(host='0.0.0.0', port=port)

# ========== ربات ==========
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("سلام! ربات فعال است.")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"📩 پیام دریافت شد: {update.message.text}")
    await update.message.reply_text(f"✅ پیام شما: {update.message.text}")

def run_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    print("🤖 ربات روشن شد...")
    app.run_polling()

# ========== اجرا ==========
if __name__ == "__main__":
    # Flask را در Thread جداگانه اجرا کن (پورت باز می‌شود)
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # ربات را در Main Thread اجرا کن (اینجا asyncio کار می‌کند)
    run_bot()
