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
    CallbackContext,
    filters
)

# إعدادات البوت
TOKEN = "8299954739:AAHlkfRH4N0cDjv-IToJkXQwwIqYCtzcVCQ" 
ADMIN_CHAT_ID = "8419586314" 
REQUIRED_CHANNELS = ["@crazys7", "@AWU87"]  # قنوات الاشتراك الإجباري

# إعداد التسجيل للأخطاء
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
    )
    ''')
    conn.commit()
    conn.close()

init_db()

# متابعة المتصفح
def setup_browser():
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    from selenium.webdriver.chrome.options import Options
    
    options = Options()
    options.add_argument("--disable-notifications")
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )
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
    
    # محاولة العثور على زر إنشاء منشور
    try:
        driver.find_element(By.XPATH, "//div[contains(@class, 'x1i10hfl')]").click()
    except:
        driver.find_element(By.XPATH, "//div[@role='button' and contains(., 'Create')]").click()
    
    time.sleep(2)
    
    # رفع الصورة
    upload_input = driver.find_element(By.XPATH, "//input[@type='file']")
    upload_input.send_keys(os.path.abspath(image_path))
    time.sleep(3)
    
    # التالي
    next_buttons = driver.find_elements(By.XPATH, "//div[contains(text(), 'التالي') or contains(text(), 'Next')]")
    if next_buttons:
        next_buttons[0].click()
        time.sleep(2)
    
    # إضافة وصف
    caption_field = driver.find_element(By.XPATH, "//textarea[@aria-label='اكتب تعليقًا...' or @aria-label='Write a caption...']")
    caption_field.send_keys(caption)
    time.sleep(2)
    
    # النشر
    share_buttons = driver.find_elements(By.XPATH, "//div[contains(text(), 'مشاركة') or contains(text(), 'Share')]")
    if share_buttons:
        share_buttons[0].click()
        time.sleep(5)
        return True
    return False

# التحقق من الاشتراك في القنوات
async def check_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    for channel in REQUIRED_CHANNELS:
        try:
            chat_member = await context.bot.get_chat_member(chat_id=channel, user_id=user_id)
            if chat_member.status not in ["member", "administrator", "creator"]:
                return False
        except Exception as e:
            logger.error(f"Error checking subscription: {e}")
            return False
    return True

# لوحة التحكم الرئيسية
def main_keyboard(user_id):
    keyboard = [
        [InlineKeyboardButton("إضافة حساب", callback_data='add_account')],
        [InlineKeyboardButton("حساباتي", callback_data='my_accounts')],
        [InlineKeyboardButton("تعليمات", callback_data='help')]
    ]
    return InlineKeyboardMarkup(keyboard)

# بدء البوت
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_subscription(update, context):
        await update.message.reply_text("يجب الاشتراك في القنوات التالية أولاً:\n" + "\n".join(REQUIRED_CHANNELS))
        return
    
    await update.message.reply_text(
        "مرحباً! بوت التحكم بحسابات إنستجرام\nاختر أحد الخيارات:",
        reply_markup=main_keyboard(update.effective_user.id)
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
            await update.message.reply_text("الرجاء استخدام الصيغة الصحيحة: username:password")
            return
            
        username, password = text.split(":", 1)
        user_id = update.effective_user.id
        
        conn = sqlite3.connect('instagram_bot.db')
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO accounts VALUES (?, ?, ?, 0)", 
                      (user_id, username.strip(), password.strip()))
        conn.commit()
        conn.close()
        
        await update.message.reply_text("تم حفظ الحساب بنجاح!")
        context.user_data.pop('awaiting_credentials', None)
    except Exception as e:
        logger.error(f"Error saving credentials: {e}")
        await update.message.reply_text(f"خطأ: {str(e)}\nيرجى المحاولة مرة أخرى")

# إدارة الحسابات
async def my_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    conn = sqlite3.connect('instagram_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT insta_username, is_active FROM accounts WHERE user_id=?", (user_id,))
    accounts = cursor.fetchall()
    conn.close()
    
    if not accounts:
        await query.edit_message_text("ليس لديك أي حسابات مسجلة")
        return
    
    keyboard = []
    for username, is_active in accounts:
        status = "✅ مفعل" if is_active else "❌ معطل"
        keyboard.append([InlineKeyboardButton(f"{username} - {status}", callback_data=f"manage_{username}")])
    
    keyboard.append([InlineKeyboardButton("العودة", callback_data='back')])
    
    await query.edit_message_text(
        "حساباتك المسجلة:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# إدارة حساب معين
async def manage_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    username = query.data.split("_", 1)[1]
    
    keyboard = [
        [InlineKeyboardButton("تفعيل/تعطيل", callback_data=f"toggle_{username}")],
        [InlineKeyboardButton("حذف الحساب", callback_data=f"delete_{username}")],
        [InlineKeyboardButton("العودة", callback_data='my_accounts')]
    ]
    
    await query.edit_message_text(
        f"إدارة حساب: {username}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# تفعيل/تعطيل الحساب
async def toggle_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    username = query.data.split("_", 1)[1]
    user_id = query.from_user.id
    
    conn = sqlite3.connect('instagram_bot.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE accounts SET is_active = NOT is_active WHERE user_id=? AND insta_username=?", 
                  (user_id, username))
    conn.commit()
    conn.close()
    
    await my_accounts(update, context)

# حذف الحساب
async def delete_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    username = query.data.split("_", 1)[1]
    user_id = query.from_user.id
    
    conn = sqlite3.connect('instagram_bot.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM accounts WHERE user_id=? AND insta_username=?", 
                  (user_id, username))
    conn.commit()
    conn.close()
    
    await query.edit_message_text(f"تم حذف حساب {username} بنجاح!")
    await my_accounts(update, context)

# العودة للقائمة الرئيسية
async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "مرحباً! بوت التحكم بحسابات إنستجرام\nاختر أحد الخيارات:",
        reply_markup=main_keyboard(update.effective_user.id)
    )

# معالجة الصور للنشر
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # التحقق من وجود حساب مفعل
    conn = sqlite3.connect('instagram_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT insta_username, insta_password FROM accounts WHERE user_id=? AND is_active=1", (user_id,))
    account = cursor.fetchone()
    conn.close()
    
    if not account:
        await update.message.reply_text("ليس لديك حساب مفعل! الرجاء تفعيل حساب أولاً.")
        return
    
    # تنزيل الصورة
    photo_file = await update.message.photo[-1].get_file()
    image_path = f"{photo_file.file_id}.jpg"
    await photo_file.download_to_drive(image_path)
    
    # النشر
    try:
        driver = setup_browser()
        login_status = insta_login(driver, account[0], account[1])
        
        if "نجاح" in login_status:
            caption = update.message.caption if update.message.caption else ""
            if insta_post(driver, image_path, caption):
                await update.message.reply_text("✅ تم النشر بنجاح على إنستجرام!")
            else:
                await update.message.reply_text("❌ فشل في عملية النشر")
        else:
            await update.message.reply_text("❌ فشل تسجيل الدخول إلى إنستجرام")
        
        driver.quit()
    except Exception as e:
        logger.error(f"Error posting to Instagram: {e}")
        await update.message.reply_text(f"⚠️ حدث خطأ: {str(e)}")
    finally:
        if os.path.exists(image_path):
            os.remove(image_path)

# تعليمات الاستخدام
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    help_text = """
    📝 دليل استخدام البوت:
    
    1. أضف حساب إنستجرام باستخدام /start ثم "إضافة حساب"
    2. أرسل اسم المستخدم وكلمة المرور بالصيغة: username:password
    3. تفعيل الحساب من قائمة "حساباتي"
    4. أرسل صورة مع تعليق (اختياري) ليتم نشرها تلقائياً
    
    ⚠️ ملاحظات:
    - البوت يستخدم حساب تجريبي فقط
    - تجنب استخدام الحسابات الرئيسية
    - قد يؤدي الاستخدام المكثف إلى حظر الحساب
    """
    await query.edit_message_text(help_text, reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("العودة", callback_data='back')]
    ]))

# إعداد وتشغيل البوت
def main():
    application = Application.builder().token(TOKEN).build()
    
    # تسجيل المعالجات
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(add_account, pattern="^add_account$"))
    application.add_handler(CallbackQueryHandler(my_accounts, pattern="^my_accounts$"))
    application.add_handler(CallbackQueryHandler(manage_account, pattern="^manage_"))
    application.add_handler(CallbackQueryHandler(toggle_account, pattern="^toggle_"))
    application.add_handler(CallbackQueryHandler(delete_account, pattern="^delete_"))
    application.add_handler(CallbackQueryHandler(back_to_main, pattern="^back$"))
    application.add_handler(CallbackQueryHandler(help_command, pattern="^help$"))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_credentials))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    # تشغيل البوت
    application.run_polling()

if __name__ == '__main__':
    main() 
