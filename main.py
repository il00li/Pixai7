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

# إدارة قاعدة البيانات
class Database:
    def __init__(self):
        self.conn = sqlite3.connect('instagram_bot.db', check_same_thread=False)
        self.create_tables()
    
    def create_tables(self):
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
    
    def add_account(self, user_id, username, password):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO accounts (user_id, insta_username, insta_password, is_active)
            VALUES (?, ?, ?, ?)
        ''', (user_id, username, password, 0))
        self.conn.commit()
        return True
    
    def get_accounts(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute("SELECT insta_username, is_active FROM accounts WHERE user_id=?", (user_id,))
        return cursor.fetchall()
    
    def get_active_account(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute("SELECT insta_username, insta_password FROM accounts WHERE user_id=? AND is_active=1", (user_id,))
        return cursor.fetchone()
    
    def toggle_account(self, user_id, username):
        cursor = self.conn.cursor()
        cursor.execute("UPDATE accounts SET is_active = NOT is_active WHERE user_id=? AND insta_username=?", 
                      (user_id, username))
        self.conn.commit()
    
    def delete_account(self, user_id, username):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM accounts WHERE user_id=? AND insta_username=?", 
                      (user_id, username))
        self.conn.commit()

db = Database()

# متابعة المتصفح
def setup_browser():
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from webdriver_manager.chrome import ChromeDriverManager

    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    
    # حل مشكلة Chrome على Render
    options.binary_location = os.getenv("CHROME_BIN", "/usr/bin/chromium-browser")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver

# تسجيل الدخول إلى إنستجرام
def insta_login(driver, username, password):
    from selenium.webdriver.common.by import By
    driver.get("https://www.instagram.com/accounts/login/")
    time.sleep(5)
    driver.find_element(By.NAME, "username").send_keys(username)
    driver.find_element(By.NAME, "password").send_keys(password)
    driver.find_element(By.XPATH, "//button[@type='submit']").click()
    time.sleep(7)
    return "تم تسجيل الدخول بنجاح" if "instagram.com" in driver.current_url else "فشل تسجيل الدخول"

# نشر على إنستجرام
def insta_post(driver, image_path, caption=""):
    from selenium.webdriver.common.by import By
    driver.get("https://www.instagram.com/")
    time.sleep(5)
    
    # العثور على زر النشر
    try:
        create_button = driver.find_element(By.XPATH, "//div[@role='button'][.//*[local-name()='svg' and @aria-label='New post']]")
        create_button.click()
    except:
        try:
            create_button = driver.find_element(By.XPATH, "//span[text()='Create']")
            create_button.click()
        except:
            return False
    
    time.sleep(3)
    
    # رفع الصورة
    upload_input = driver.find_element(By.XPATH, "//input[@type='file']")
    upload_input.send_keys(os.path.abspath(image_path))
    time.sleep(5)
    
    # التالي
    next_buttons = driver.find_elements(By.XPATH, "//div[contains(text(), 'Next') or contains(text(), 'التالي')]")
    if next_buttons:
        next_buttons[0].click()
        time.sleep(3)
    
    # إضافة وصف
    caption_field = driver.find_element(By.XPATH, "//textarea[@aria-label='Write a caption...' or @aria-label='اكتب تعليقًا...']")
    caption_field.send_keys(caption)
    time.sleep(2)
    
    # النشر
    share_buttons = driver.find_elements(By.XPATH, "//div[contains(text(), 'Share') or contains(text(), 'مشاركة')]")
    if share_buttons:
        share_buttons[0].click()
        time.sleep(10)
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
            logger.error(f"خطأ في التحقق من الاشتراك: {e}")
            return False
    return True

# لوحة التحكم
def control_keyboard():
    keyboard = [
        [InlineKeyboardButton("نشر الآن", callback_data='publish_now')],
        [InlineKeyboardButton("إدارة الحسابات", callback_data='manage_accounts')],
        [InlineKeyboardButton("مساعدة", callback_data='help')]
    ]
    return InlineKeyboardMarkup(keyboard)

# بدء البوت
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_subscription(update, context):
        await update.message.reply_text("يجب الاشتراك في القنوات التالية أولاً:\n" + "\n".join(REQUIRED_CHANNELS))
        return
    
    await update.message.reply_text(
        "🏆 بوت النشر الآمن لإنستجرام\nاختر أحد الخيارات:",
        reply_markup=control_keyboard()
    )

# معالجة زر "نشر الآن"
async def publish_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📤 أرسل الآن الصورة التي تريد نشرها مع التعليق (اختياري)")
    context.user_data['awaiting_post'] = True

# معالجة المنشور
async def handle_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_post' not in context.user_data:
        return
    
    user_id = update.effective_user.id
    account = db.get_active_account(user_id)
    
    if not account:
        await update.message.reply_text("⚠️ ليس لديك حساب مفعل! الرجاء تفعيل حساب أولاً.")
        context.user_data.pop('awaiting_post', None)
        return
    
    if not update.message.photo:
        await update.message.reply_text("⚠️ الرجاء إرسال صورة")
        return
    
    # تنزيل الصورة
    photo_file = await update.message.photo[-1].get_file()
    image_path = f"temp_{photo_file.file_id}.jpg"
    await photo_file.download_to_drive(image_path)
    caption = update.message.caption if update.message.caption else ""
    
    # إرسال رسالة انتظار
    wait_msg = await update.message.reply_text("⏳ جاري النشر على إنستجرام...")
    
    try:
        driver = setup_browser()
        login_status = insta_login(driver, account[0], account[1])
        
        if "نجاح" in login_status:
            if insta_post(driver, image_path, caption):
                await wait_msg.edit_text("✅ تم النشر بنجاح على إنستجرام!", reply_markup=control_keyboard())
            else:
                await wait_msg.edit_text("❌ فشل في عملية النشر", reply_markup=control_keyboard())
        else:
            await wait_msg.edit_text("❌ فشل تسجيل الدخول إلى إنستجرام", reply_markup=control_keyboard())
        
        driver.quit()
    except Exception as e:
        logger.error(f"خطأ في النشر: {e}")
        await wait_msg.edit_text(f"⚠️ حدث خطأ غير متوقع: {str(e)}", reply_markup=control_keyboard())
    finally:
        if os.path.exists(image_path):
            os.remove(image_path)
        context.user_data.pop('awaiting_post', None)

# معالجة زر "إدارة الحسابات"
async def manage_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    accounts = db.get_accounts(user_id)
    
    if not accounts:
        await query.edit_message_text("ليس لديك أي حسابات مسجلة")
        return
    
    keyboard = []
    for username, is_active in accounts:
        status = "✅ مفعل" if is_active else "❌ معطل"
        keyboard.append([InlineKeyboardButton(f"{username} - {status}", callback_data=f"manage_{username}")])
    
    keyboard.append([InlineKeyboardButton("إضافة حساب جديد", callback_data='add_account')])
    keyboard.append([InlineKeyboardButton("العودة", callback_data='back')])
    
    await query.edit_message_text(
        "📝 حساباتك المسجلة:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# إضافة حساب جديد
async def add_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("أرسل اسم مستخدم إنستجرام وكلمة المرور بهذا الشكل:\nusername:password")
    context.user_data['awaiting_credentials'] = True

# معالجة بيانات الحساب
async def handle_credentials(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_credentials' not in context.user_data:
        return
    
    try:
        text = update.message.text
        if ':' not in text:
            await update.message.reply_text("⚠️ الرجاء استخدام الصيغة الصحيحة: username:password")
            return
            
        username, password = text.split(":", 1)
        user_id = update.effective_user.id
        
        if db.add_account(user_id, username.strip(), password.strip()):
            await update.message.reply_text("✅ تم حفظ الحساب بنجاح!", reply_markup=control_keyboard())
        else:
            await update.message.reply_text("❌ فشل في حفظ الحساب", reply_markup=control_keyboard())
        
        context.user_data.pop('awaiting_credentials', None)
    except Exception as e:
        logger.error(f"خطأ في حفظ بيانات الحساب: {e}")
        await update.message.reply_text(f"⚠️ حدث خطأ: {str(e)}", reply_markup=control_keyboard())

# معالجة الأخطاء
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"حدث خطأ غير متوقع: {context.error}")
    
    if isinstance(update, Update):
        if update.callback_query:
            await update.callback_query.message.reply_text("⚠️ حدث خطأ غير متوقع. الرجاء المحاولة لاحقًا")
        elif update.message:
            await update.message.reply_text("⚠️ حدث خطأ غير متوقع. الرجاء المحاولة لاحقًا")

def main():
    application = Application.builder().token(TOKEN).build()
    
    # معالجات الأوامر
    application.add_handler(CommandHandler("start", start))
    
    # معالجات الأزرار
    application.add_handler(CallbackQueryHandler(publish_now, pattern="^publish_now$"))
    application.add_handler(CallbackQueryHandler(manage_accounts, pattern="^manage_accounts$"))
    application.add_handler(CallbackQueryHandler(add_account, pattern="^add_account$"))
    
    # معالجات الرسائل
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_credentials))
    application.add_handler(MessageHandler(filters.PHOTO, handle_post))
    
    # معالجة الأخطاء
    application.add_error_handler(error_handler)
    
    # تشغيل البوت
    application.run_polling()

if __name__ == '__main__':
    main()
