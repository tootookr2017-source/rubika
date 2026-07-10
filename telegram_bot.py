import os
import threading
import logging
import json
import time
import uuid
import shutil
import re
from pathlib import Path
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from rubpy import Client as RubikaClient
import requests

# ========== تنظیمات ==========
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========== متغیرهای محیطی ==========
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("OWNER_TELEGRAM_ID", 0))
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
ALLOWED_USERS_FILE = "/tmp/walrus/allowed_users.json"  # تغییر مسیر

# ========== مسیرهای ذخیره‌سازی (با استفاده از /tmp) ==========
BASE_DIR = Path("/tmp/walrus")
DOWNLOAD_DIR = BASE_DIR / "downloads"
SESSION_DIR = BASE_DIR / "sessions"
QUEUE_FILE = BASE_DIR / "queue/tasks.jsonl"
PROCESSING_FILE = BASE_DIR / "queue/processing.json"
FAILED_FILE = BASE_DIR / "queue/failed.jsonl"

# ایجاد دایرکتوری‌ها
BASE_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
SESSION_DIR.mkdir(parents=True, exist_ok=True)
QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)

# ========== توابع مدیریت کاربران ==========
def load_allowed_users():
    try:
        with open(ALLOWED_USERS_FILE, "r") as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()

def save_allowed_users(users):
    with open(ALLOWED_USERS_FILE, "w") as f:
        json.dump(list(users), f)

def is_user_allowed(user_id: int) -> bool:
    if user_id == ADMIN_ID:
        return True
    return user_id in load_allowed_users()

# ========== توابع مدیریت صف و فایل ==========
def append_task(task: dict):
    with open(QUEUE_FILE, "a") as f:
        f.write(json.dumps(task) + "\n")

def pop_first_task():
    if not QUEUE_FILE.exists():
        return None
    with open(QUEUE_FILE, "r") as f:
        lines = f.readlines()
    if not lines:
        return None
    first = json.loads(lines[0])
    with open(QUEUE_FILE, "w") as f:
        f.writelines(lines[1:])
    return first

def save_processing(task: dict):
    with open(PROCESSING_FILE, "w") as f:
        json.dump(task, f)

def load_processing():
    if PROCESSING_FILE.exists():
        with open(PROCESSING_FILE, "r") as f:
            return json.load(f)
    return None

def clear_processing():
    if PROCESSING_FILE.exists():
        PROCESSING_FILE.unlink()

def append_failed(task: dict, error: str):
    with open(FAILED_FILE, "a") as f:
        f.write(json.dumps({"task": task, "error": error}) + "\n")

def queue_size():
    if not QUEUE_FILE.exists():
        return 0
    with open(QUEUE_FILE, "r") as f:
        return sum(1 for _ in f)

def is_cancelled(task_id: str) -> bool:
    return False  # ساده‌سازی شده

# ========== آپلود به روبیکا ==========
async def upload_to_rubika(file_path: str, file_name: str, session_name: str, target: str = "me"):
    try:
        client = RubikaClient(name=session_name)
        await client.__aenter__()
        uploaded = await client.upload(file_path, file_name=file_name)
        await client.send_message(
            object_guid=target,
            file_inline=uploaded
        )
        await client.__aexit__(None, None, None)
        return True
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        return False

# ========== ربات تلگرام ==========
def get_main_keyboard():
    keyboard = [
        [KeyboardButton("📊 Status"), KeyboardButton("📋 Transfers")],
        [KeyboardButton("🧹 Cleanup"), KeyboardButton("🛑 Cancel")],
        [KeyboardButton("⚙️ Settings")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        await update.message.reply_text("⛔ شما دسترسی ندارید. درخواست دسترسی برای ادمین ارسال شد.")
        await context.bot.send_message(
            ADMIN_ID,
            f"👤 کاربر [{user_id}](tg://user?id={user_id}) درخواست دسترسی داده است."
        )
        return
    
    await update.message.reply_text(
        "سلام! ربات آماده است.\n"
        "📤 هر فایلی بفرستی به روبیکا آپلود میشه.",
        reply_markup=get_main_keyboard()
    )

async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        await update.message.reply_text("⛔ شما دسترسی ندارید.")
        return
    
    q_size = queue_size()
    processing = load_processing()
    active = "هیچ" if not processing else f"{processing.get('file_name', 'نامشخص')}"
    
    await update.message.reply_text(
        f"📊 وضعیت ربات:\n"
        f"🔄 صف: {q_size}\n"
        f"🚀 در حال آپلود: {active}"
    )

async def transfers_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        await update.message.reply_text("⛔ شما دسترسی ندارید.")
        return
    
    await update.message.reply_text("📋 لیست انتقال‌ها... (در حال توسعه)")

async def cleanup_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        await update.message.reply_text("⛔ شما دسترسی ندارید.")
        return
    
    count = 0
    for file in DOWNLOAD_DIR.iterdir():
        if file.is_file() and time.time() - file.stat().st_mtime > 86400:
            file.unlink()
            count += 1
    
    await update.message.reply_text(f"🧹 پاک‌سازی انجام شد. {count} فایل حذف شد.")

async def settings_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        await update.message.reply_text("⛔ شما دسترسی ندارید.")
        return
    
    await update.message.reply_text(
        "⚙️ تنظیمات:\n"
        f"📱 ادمین: {ADMIN_ID}\n"
        f"📁 مسیر دانلود: {DOWNLOAD_DIR}"
    )

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        await update.message.reply_text("⛔ شما دسترسی ندارید.")
        return
    
    message = update.message
    file_id = None
    file_name = "file"
    
    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name or "document"
    elif message.audio:
        file_id = message.audio.file_id
        file_name = message.audio.file_name or "audio.mp3"
    elif message.video:
        file_id = message.video.file_id
        file_name = "video.mp4"
    elif message.photo:
        file_id = message.photo[-1].file_id
        file_name = "photo.jpg"
    elif message.voice:
        file_id = message.voice.file_id
        file_name = "voice.ogg"
    else:
        await update.message.reply_text("⚠️ نوع فایل پشتیبانی نمی‌شود.")
        return
    
    status_msg = await update.message.reply_text(f"⬇️ در حال دانلود: {file_name}...")
    try:
        file = await context.bot.get_file(file_id)
        download_path = DOWNLOAD_DIR / f"{uuid.uuid4().hex}_{file_name}"
        await file.download_to_drive(download_path)
        
        await status_msg.edit_text(f"✅ دانلود شد: {file_name}\n⏳ در حال آپلود به روبیکا...")
        
        task = {
            "task_id": uuid.uuid4().hex[:8],
            "file_name": file_name,
            "path": str(download_path),
            "user_id": user_id,
            "chat_id": update.effective_chat.id
        }
        append_task(task)
        
        await status_msg.edit_text(f"✅ فایل {file_name} به صف اضافه شد. موقعیت صف: {queue_size()}")
        
        await process_queue(context)
        
    except Exception as e:
        logger.error(f"Download error: {e}")
        await status_msg.edit_text(f"❌ خطا در دانلود: {str(e)}")

async def process_queue(context: ContextTypes.DEFAULT_TYPE):
    if load_processing():
        return
    
    task = pop_first_task()
    if not task:
        return
    
    save_processing(task)
    try:
        session_name = str(SESSION_DIR / "rubika_session.rp")
        success = await upload_to_rubika(
            task["path"],
            task["file_name"],
            session_name,
            "me"
        )
        
        if success:
            await context.bot.send_message(
                task["chat_id"],
                f"✅ آپلود {task['file_name']} به روبیکا موفق بود."
            )
        else:
            append_failed(task, "Upload failed")
            await context.bot.send_message(
                task["chat_id"],
                f"❌ آپلود {task['file_name']} ناموفق بود."
            )
    except Exception as e:
        append_failed(task, str(e))
        await context.bot.send_message(
            task["chat_id"],
            f"❌ خطا: {str(e)}"
        )
    finally:
        clear_processing()
        try:
            Path(task["path"]).unlink(missing_ok=True)
        except:
            pass
        await process_queue(context)

# ========== Flask ==========
flask_app = Flask(__name__)

@flask_app.route('/')
@flask_app.route('/health')
def health():
    return "ربات روشن است!", 200

def run_flask():
    port = int(os.environ.get('PORT', 8000))
    flask_app.run(host='0.0.0.0', port=port)

# ========== اجرا ==========
def run_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status_handler))
    app.add_handler(CommandHandler("transfers", transfers_handler))
    app.add_handler(CommandHandler("cleanup", cleanup_handler))
    app.add_handler(CommandHandler("settings", settings_handler))
    app.add_handler(MessageHandler(
        filters.Document.ALL | filters.AUDIO | filters.VIDEO | filters.PHOTO | filters.VOICE,
        handle_file
    ))
    
    async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text
        if text == "📊 Status":
            await status_handler(update, context)
        elif text == "📋 Transfers":
            await transfers_handler(update, context)
        elif text == "🧹 Cleanup":
            await cleanup_handler(update, context)
        elif text == "⚙️ Settings":
            await settings_handler(update, context)
        else:
            await update.message.reply_text("دستور نامعتبر.")
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_handler))
    
    logger.info("🤖 ربات اصلی روشن شد...")
    app.run_polling()

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("Flask در Thread جداگانه اجرا شد.")
    
    run_bot()
