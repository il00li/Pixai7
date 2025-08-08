import os
import sqlite3
import time
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# إعدادات البوت
TOKEN = "8299954739:AAHlkfRH4N0cDjv-IToJkXQwwIqYCtzcVCQ"
ADMIN_CHAT_ID = "8419586314"
REQUIRED_CHANNELS = ["@crazys7", "@AWU87"]

# إعداد التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# إدارة قاعدة البيانات (محدثة)
class Database:
    def __init__(self):
        self.conn = sqlite3.connect('instagram_bot.db', check_same_thread=False)
        self.create_tables()
    
    def create_tables(self):
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS accounts (
                    user_id INTEGER,
                    insta_username TEXT,
                    insta_password TEXT,
                    is_active INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, insta_username)
                )
            ''')
            self.conn.commit()
        except Exception as e:
            logger.error(f"Error creating tables: {e}")
    
    def add_account(self, user_id, username, password):
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO accounts (user_id, insta_username, insta_password, is_active)
                VALUES (?, ?, ?, ?)
            ''', (user_id, username, password, 0))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error adding account: {e}")
            return False
    
    # باقي دوال قاعدة البيانات...

db = Database()

# متابعة المتصفح (محدثة)
def setup_browser():
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from webdriver_manager.chrome import ChromeDriverManager

    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--headless")
    
    # حل مشكلة Chrome على Render
    options.binary_location = os.getenv("CHROME_BIN", "/usr/bin/chromium-browser")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver

# باقي الدوال (تسجيل الدخول، النشر، التحقق من الاشتراك)...

# معالجة الأوامر (محدثة)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_subscription(update, context):
        await update.message.reply_text("يجب الاشتراك في القنوات التالية أولاً:\n" + "\n".join(REQUIRED_CHANNELS))
        return
    
    keyboard = [
        [InlineKeyboardButton("نشر الآن", callback_data='publish_now')],
        [InlineKeyboardButton("إدارة الحسابات", callback_data='manage_accounts')],
        [InlineKeyboardButton("مساعدة", callback_data='help')]
    ]
    await update.message.reply_text(
        "🏆 بوت النشر الآمن لإنستجرام\nاختر أحد الخيارات:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# معالجة الأخطاء (محدثة)
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"حدث خطأ: {context.error}")
    if update.callback_query:
        await update.callback_query.message.reply_text("⚠️ حدث خطأ غير متوقع. الرجاء المحاولة لاحقًا")
    elif update.message:
        await update.message.reply_text("⚠️ حدث خطأ غير متوقع. الرجاء المحاولة لاحقًا")

def main():
    application = Application.builder().token(TOKEN).build()
    
    # المعالجات الأساسية
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(publish_now, pattern="^publish_now$"))
    
    # معالجة الأخطاء
    application.add_error_handler(error_handler)
    
    # تشغيل البوت
    application.run_polling()

if __name__ == '__main__':
    main()
