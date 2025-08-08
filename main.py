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

# إعداد قاعدة البيانات
def init_db():
    conn = sqlite3.connect('instagram_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS accounts (
        user_id INTEGER,
        insta_username TEXT,
        insta_password TEXT,
        is_active INTEGER DEFAULT 0,
        PRIMARY KEY (user_id, insta_username)
    ''')
    conn.commit()
    conn.close()

init_db()

# متابعة المتصفح (محدثة لحل مشكلة Chrome Binary)
def setup_browser():
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from webdriver_manager.chrome import ChromeDriverManager

    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--headless")
    
    # حل مشكلة Chrome Binary على Render
    options.binary_location = os.getenv("CHROME_BIN", "/opt/render/.cache/chromium/chrome-linux/chrome")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver

# تسجيل الدخول إلى إنستجرام
def insta_login(driver, username, password):
    from selenium.webdriver.common.by import By
    driver.get("https://www.instagram.com/accounts/login/")
    time.sleep(3)
    driver.find_element(By.NAME, "username").send_keys(username)
    driver.find_element(By.NAME, "password").send_keys(password)
    driver.find_element(By.XPATH, "//button[@type='submit']").click()
    time.sleep(5)
    return "تم تسجيل الدخول بنجاح" if "instagram.com" in driver.current_url else "فشل تسجيل الدخول"

# نشر على إنستجرام
def insta_post(driver, image_path, caption=""):
    from selenium.webdriver.common.by import By
    driver.get("https://www.instagram.com/")
    time.sleep(3)
    
    try:
        driver.find_element(By.XPATH, "//div[contains(@aria-label, 'New post')]").click()
    except:
        try:
            driver.find_element(By.XPATH, "//span[contains(text(), 'Create')]").click()
        except:
            driver.find_element(By.XPATH, "//button[contains(@aria-label, 'New post')]").click()
    
    time.sleep(2)
    upload_input = driver.find_element(By.XPATH, "//input[@type='file']")
    upload_input.send_keys(os.path.abspath(image_path))
    time.sleep(3)
    
    next_buttons = driver.find_elements(By.XPATH, "//div[contains(text(), 'Next') or contains(text(), 'التالي')]")
    if next_buttons:
        next_buttons[0].click()
        time.sleep(2)
    
    caption_field = driver.find_element(By.XPATH, "//textarea[@aria-label='Write a caption...' or @aria-label='اكتب تعليقًا...']")
    caption_field.send_keys(caption)
    time.sleep(2)
    
    share_buttons = driver.find_elements(By.XPATH, "//div[contains(text(), 'Share') or contains(text(), 'مشاركة')]")
    if share_buttons:
        share_buttons[0].click()
        time.sleep(5)
        return True
    return False

# التحقق من الاشتراك
async def check_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    for channel in REQUIRED_CHANNELS:
        try:
            chat_member = await context.bot.get_chat_member(channel, user_id)
            if chat_member.status not in ["member", "administrator", "creator"]:
                return False
        except Exception as e:
            logger.error(f"Error checking subscription: {e}")
            return False
    return True

# لوحة التحكم مع زر "نشر الآن"
def control_keyboard():
    keyboard = [
        [InlineKeyboardButton("نشر الآن", callback_data='publish_now')],
        [InlineKeyboardButton("حساباتي", callback_data='my_accounts')],
        [InlineKeyboardButton("إضافة حساب", callback_data='add_account')]
    ]
    return InlineKeyboardMarkup(keyboard)

# بدء البوت
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_subscription(update, context):
        await update.message.reply_text("يجب الاشتراك في القنوات التالية أولاً:\n" + "\n".join(REQUIRED_CHANNELS))
        return
    
    await update.message.reply_text(
        "مرحباً! بوت التحكم بحسابات إنستجرام\nاختر أحد الخيارات:",
        reply_markup=control_keyboard()
    )

# معالجة زر "نشر الآن"
async def publish_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("أرسل الآن الصورة أو الفيديو الذي تريد نشره مع التعليق (اختياري)")
    context.user_data['awaiting_post'] = True

# معالجة المنشور
async def handle_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_post' not in context.user_data:
        return
    
    user_id = update.effective_user.id
    conn = sqlite3.connect('instagram_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT insta_username, insta_password FROM accounts WHERE user_id=? AND is_active=1", (user_id,))
    account = cursor.fetchone()
    conn.close()
    
    if not account:
        await update.message.reply_text("ليس لديك حساب مفعل!")
        return
    
    if not update.message.photo:
        await update.message.reply_text("الرجاء إرسال صورة أو فيديو")
        return
    
    # تنزيل الميديا
    media_file = await update.message.photo[-1].get_file()
    media_path = f"temp_{media_file.file_id}.jpg"
    await media_file.download_to_drive(media_path)
    
    try:
        driver = setup_browser()
        login_status = insta_login(driver, account[0], account[1])
        
        if "نجاح" in login_status:
            caption = update.message.caption if update.message.caption else ""
            if insta_post(driver, media_path, caption):
                await update.message.reply_text("✅ تم النشر بنجاح!", reply_markup=control_keyboard())
            else:
                await update.message.reply_text("❌ فشل النشر", reply_markup=control_keyboard())
        else:
            await update.message.reply_text("❌ فشل تسجيل الدخول", reply_markup=control_keyboard())
        
        driver.quit()
    except Exception as e:
        logger.error(f"Posting error: {e}")
        await update.message.reply_text(f"⚠️ خطأ: {str(e)}", reply_markup=control_keyboard())
    finally:
        if os.path.exists(media_path):
            os.remove(media_path)
        context.user_data.pop('awaiting_post', None)

# باقي الدوال (إضافة حساب، إدارة الحسابات، ...)
# ... [الكود السابق لهذه الدوال يبقى كما هو]

def main():
    application = Application.builder().token(TOKEN).build()
    
    # معالجات الأوامر
    application.add_handler(CommandHandler("start", start))
    
    # معالجات الأزرار
    application.add_handler(CallbackQueryHandler(publish_now, pattern="^publish_now$"))
    application.add_handler(CallbackQueryHandler(add_account, pattern="^add_account$"))
    application.add_handler(CallbackQueryHandler(my_accounts, pattern="^my_accounts$"))
    # ... [باقي معالجات الأزرار]
    
    # معالجات الرسائل
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_credentials))
    application.add_handler(MessageHandler(filters.PHOTO, handle_post))
    
    application.run_polling()

if __name__ == '__main__':
    main() 
