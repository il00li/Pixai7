import os
import sqlite3
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
import time
import asyncio
from PIL import Image
import io

# إعدادات التسجيل
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# إعدادات البوت
TOKEN = "8299954739:AAHlkfRH4N0cDjv-IToJkXQwwIqYCtzcVCQ"
REQUIRED_CHANNELS = ["@crazys7", "@AWU87"]
CHROME_BIN = "/usr/bin/chromium-browser"

# تهيئة قاعدة البيانات
def init_db():
    conn = sqlite3.connect('instagram_bot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS accounts
                 (user_id INTEGER,
                  insta_username TEXT,
                  insta_password TEXT,
                  is_active INTEGER DEFAULT 0,
                  PRIMARY KEY (user_id, insta_username))''')
    conn.commit()
    conn.close()

# التحقق من اشتراك المستخدم
async def check_subscription(user_id, context):
    try:
        for channel in REQUIRED_CHANNELS:
            member = await context.bot.get_chat_member(channel, user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                return False
        return True
    except:
        return False

# إعداد المتصفح
def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    
    if CHROME_BIN and os.path.exists(CHROME_BIN):
        chrome_options.binary_location = CHROME_BIN
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

# البدء
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not await check_subscription(user_id, context):
        channels_text = "\n".join([f"• {ch}" for ch in REQUIRED_CHANNELS])
        await update.message.reply_text(
            f"⚠️ يجب الاشتراك في القنوات التالية أولاً:\n{channels_text}\n\n"
            f"بعد الاشتراك، أعد إرسال /start"
        )
        return
    
    keyboard = [
        [InlineKeyboardButton("📤 نشر الآن", callback_data='post_now')],
        [InlineKeyboardButton("🔐 تسجيل الدخول", callback_data='login_account')],
        [InlineKeyboardButton("👤 إدارة الحسابات", callback_data='manage_accounts')],
        [InlineKeyboardButton("➕ إضافة حساب", callback_data='add_account')],
        [InlineKeyboardButton("❓ مساعدة", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🤖 مرحباً بك في بوت إدارة إنستجرام!\n"
        "اختر أحد الخيارات أدناه:",
        reply_markup=reply_markup
    )

# معالجة الاستعلامات
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if data == 'add_account':
        await query.edit_message_text(
            "➕ إضافة حساب إنستجرام جديد\n"
            "أرسل اسم المستخدم وكلمة المرور بالصيغة:\n"
            "`username:password`",
            parse_mode='Markdown'
        )
        context.user_data['action'] = 'add_account'
    
    elif data == 'manage_accounts':
        conn = sqlite3.connect('instagram_bot.db')
        c = conn.cursor()
        accounts = c.execute("SELECT insta_username, is_active FROM accounts WHERE user_id=?", (user_id,)).fetchall()
        conn.close()
        
        if not accounts:
            await query.edit_message_text("لا توجد حسابات مضافة بعد.")
            return
        
        keyboard = []
        for username, active in accounts:
            status = "✅" if active else "❌"
            keyboard.append([
                InlineKeyboardButton(f"{status} {username}", callback_data=f'toggle_{username}'),
                InlineKeyboardButton("🗑 حذف", callback_data=f'delete_{username}')
            ])
        
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data='back')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "👤 إدارة الحسابات:\n"
            "اضغط على الحساب لتفعيل/تعطيل\n"
            "اضغط على 🗑 لحذف الحساب",
            reply_markup=reply_markup
        )
    
    elif data.startswith('toggle_'):
        username = data.split('_')[1]
        conn = sqlite3.connect('instagram_bot.db')
        c = conn.cursor()
        current = c.execute("SELECT is_active FROM accounts WHERE user_id=? AND insta_username=?", 
                          (user_id, username)).fetchone()[0]
        new_status = 0 if current else 1
        c.execute("UPDATE accounts SET is_active=? WHERE user_id=? AND insta_username=?", 
                 (new_status, user_id, username))
        conn.commit()
        conn.close()
        
        await query.answer(f"تم {'تفعيل' if new_status else 'تعطيل'} الحساب {username}")
        await button_handler(update, context)  # إعادة تحميل القائمة
    
    elif data.startswith('delete_'):
        username = data.split('_')[1]
        conn = sqlite3.connect('instagram_bot.db')
        c = conn.cursor()
        c.execute("DELETE FROM accounts WHERE user_id=? AND insta_username=?", (user_id, username))
        conn.commit()
        conn.close()
        
        await query.answer(f"تم حذف الحساب {username}")
        await button_handler(update, context)  # إعادة تحميل القائمة
    
    elif data == 'login_account':
        conn = sqlite3.connect('instagram_bot.db')
        c = conn.cursor()
        accounts = c.execute("SELECT insta_username FROM accounts WHERE user_id=? AND is_active=1", (user_id,)).fetchall()
        conn.close()
        
        if not accounts:
            await query.edit_message_text("لا توجد حسابات مفعلة للتسجيل.")
            return
        
        keyboard = []
        for account in accounts:
            keyboard.append([InlineKeyboardButton(account[0], callback_data=f'login_{account[0]}')])
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data='back')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text("اختر حساباً لتسجيل الدخول:", reply_markup=reply_markup)
    
    elif data.startswith('login_'):
        username = data.split('_')[1]
        await query.edit_message_text(f"جاري تسجيل الدخول للحساب {username}...")
        
        conn = sqlite3.connect('instagram_bot.db')
        c = conn.cursor()
        password = c.execute("SELECT insta_password FROM accounts WHERE user_id=? AND insta_username=?", 
                           (user_id, username)).fetchone()[0]
        conn.close()
        
        # تشغيل تسجيل الدخول في خيط منفصل
        asyncio.create_task(login_instagram(update, context, username, password))
    
    elif data == 'post_now':
        conn = sqlite3.connect('instagram_bot.db')
        c = conn.cursor()
        accounts = c.execute("SELECT insta_username FROM accounts WHERE user_id=? AND is_active=1", (user_id,)).fetchall()
        conn.close()
        
        if not accounts:
            await query.edit_message_text("لا توجد حسابات مفعلة للنشر.")
            return
        
        keyboard = []
        for account in accounts:
            keyboard.append([InlineKeyboardButton(account[0], callback_data=f'post_{account[0]}')])
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data='back')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text("اختر حساباً للنشر:", reply_markup=reply_markup)
        context.user_data['action'] = 'select_account_for_post'
    
    elif data.startswith('post_'):
        username = data.split('_')[1]
        context.user_data['selected_account'] = username
        await query.edit_message_text(
            "📤 إرسال صورة للنشر:\n"
            "أرسل الصورة الآن (مع تعليق اختياري)"
        )
        context.user_data['action'] = 'send_image_for_post'
    
    elif data == 'help':
        await query.edit_message_text(
            "❓ دليل استخدام البوت:\n\n"
            "📤 **نشر الآن**: نشر صورة على إنستجرام\n"
            "🔐 **تسجيل الدخول**: التحقق من صحة الحساب\n"
            "👤 **إدارة الحسابات**: تفعيل/تعطيل/حذف الحسابات\n"
            "➕ **إضافة حساب**: إضافة حساب إنستجرام جديد\n\n"
            "للنشر: أرسل الصورة مع التعليق (اختياري)"
        )
    
    elif data == 'back':
        keyboard = [
            [InlineKeyboardButton("📤 نشر الآن", callback_data='post_now')],
            [InlineKeyboardButton("🔐 تسجيل الدخول", callback_data='login_account')],
            [InlineKeyboardButton("👤 إدارة الحسابات", callback_data='manage_accounts')],
            [InlineKeyboardButton("➕ إضافة حساب", callback_data='add_account')],
            [InlineKeyboardButton("❓ مساعدة", callback_data='help')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "🤖 لوحة التحكم الرئيسية:",
            reply_markup=reply_markup
        )

# معالجة الرسائل النصية
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    action = context.user_data.get('action')
    
    if not await check_subscription(user_id, context):
        await update.message.reply_text("يجب الاشتراك في القنوات المطلوبة أولاً.")
        return
    
    if action == 'add_account':
        text = update.message.text
        if ':' not in text:
            await update.message.reply_text("❌ الصيغة غير صحيحة. استخدم: username:password")
            return
        
        username, password = text.split(':', 1)
        
        conn = sqlite3.connect('instagram_bot.db')
        c = conn.cursor()
        try:
            c.execute("INSERT INTO accounts (user_id, insta_username, insta_password) VALUES (?, ?, ?)",
                     (user_id, username.strip(), password.strip()))
            conn.commit()
            await update.message.reply_text(f"✅ تم إضافة الحساب {username.strip()}")
        except sqlite3.IntegrityError:
            await update.message.reply_text("❌ هذا الحساب موجود بالفعل")
        finally:
            conn.close()
        
        context.user_data['action'] = None

# تسجيل الدخول إلى إنستجرام
async def login_instagram(update, context, username, password):
    driver = None
    try:
        driver = setup_driver()
        driver.get("https://www.instagram.com/accounts/login/")
        
        # انتظار تحميل الصفحة
        time.sleep(3)
        
        # إدخال اسم المستخدم وكلمة المرور
        username_input = driver.find_element(By.NAME, "username")
        password_input = driver.find_element(By.NAME, "password")
        
        username_input.send_keys(username)
        password_input.send_keys(password)
        
        # النقر على زر تسجيل الدخول
        login_button = driver.find_element(By.XPATH, "//button[@type='submit']")
        login_button.click()
        
        time.sleep(5)
        
        # التحقق من نجاح تسجيل الدخول
        if "accounts/login" not in driver.current_url:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"✅ تم تسجيل الدخول بنجاح للحساب {username}"
            )
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"❌ فشل تسجيل الدخول للحساب {username}"
            )
            
    except Exception as e:
        logger.error(f"خطأ في تسجيل الدخول: {e}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"❌ خطأ في تسجيل الدخول: {str(e)}"
        )
    finally:
        if driver:
            driver.quit()

# معالجة الصور
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not await check_subscription(user_id, context):
        await update.message.reply_text("يجب الاشتراك في القنوات المطلوبة أولاً.")
        return
    
    if context.user_data.get('action') == 'send_image_for_post':
        username = context.user_data.get('selected_account')
        if not username:
            await update.message.reply_text("❌ لم يتم اختيار حساب.")
            return
        
        # الحصول على كلمة المرور
        conn = sqlite3.connect('instagram_bot.db')
        c = conn.cursor()
        password = c.execute("SELECT insta_password FROM accounts WHERE user_id=? AND insta_username=?", 
                           (user_id, username)).fetchone()[0]
        conn.close()
        
        caption = update.message.caption if update.message.caption else ""
        
        # تشغيل النشر في خيط منفصل
        asyncio.create_task(post_to_instagram(update, context, username, password, update.message.photo[-1], caption))
        
        await update.message.reply_text("🔄 جاري نشر الصورة...")
        context.user_data['action'] = None

# النشر على إنستجرام
async def post_to_instagram(update, context, username, password, photo, caption):
    driver = None
    try:
        driver = setup_driver()
        
        # تسجيل الدخول
        driver.get("https://www.instagram.com/accounts/login/")
        time.sleep(3)
        
        username_input = driver.find_element(By.NAME, "username")
        password_input = driver.find_element(By.NAME, "password")
        
        username_input.send_keys(username)
        password_input.send_keys(password)
        
        login_button = driver.find_element(By.XPATH, "//button[@type='submit']")
        login_button.click()
        
        time.sleep(5)
        
        if "accounts/login" in driver.current_url:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ فشل تسجيل الدخول. تحقق من بيانات الحساب."
            )
            return
        
        # الانتقال إلى صفحة النشر
        driver.get("https://www.instagram.com/")
        time.sleep(3)
        
        # النقر على زر إنشاء منشور
        create_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//*[contains(@aria-label, 'New post')]"))
        )
        create_button.click()
        
        time.sleep(2)
        
        # تحميل الصورة
        photo_file = await context.bot.get_file(photo.file_id)
        photo_bytes = await photo_file.download_as_bytearray()
        
        # حفظ الصورة مؤقتاً
        with open("temp_post.jpg", "wb") as f:
            f.write(photo_bytes)
        
        upload_input = driver.find_element(By.XPATH, "//input[@type='file']")
        upload_input.send_keys(os.path.abspath("temp_post.jpg"))
        
        time.sleep(3)
        
        # الانتقال للخطوة التالية
        next_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//button[text()='Next']"))
        )
        next_button.click()
        
        time.sleep(2)
        
        # إضافة التعليق
        if caption:
            caption_textarea = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//textarea[@aria-label='Write a caption...']"))
            )
            caption_textarea.send_keys(caption)
        
        time.sleep(2)
        
        # النشر
        share_button = driver.find_element(By.XPATH, "//button[text()='Share']")
        share_button.click()
        
        time.sleep(5)
        
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="✅ تم نشر الصورة بنجاح!"
        )
        
    except Exception as e:
        logger.error(f"خطأ في النشر: {e}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"❌ خطأ في النشر: {str(e)}"
        )
    finally:
        if driver:
            driver.quit()
        # حذف الملف المؤقت
        if os.path.exists("temp_post.jpg"):
            os.remove("temp_post.jpg")

# تشغيل البوت
def main():
    init_db()
    
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    application.run_polling()

if __name__ == '__main__':
    main()
