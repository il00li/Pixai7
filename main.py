import os
import sqlite3
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters, CallbackContext
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# إعدادات البوت
TOKEN = "8299954739:AAHlkfRH4N0cDjv-IToJkXQwwIqYCtzcVCQ" 
ADMIN_CHAT_ID = "8419586314" 
REQUIRED_CHANNELS = ["@crazys7", "@AWU87"]  # قنوات الاشتراك الإجباري

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
    options = webdriver.ChromeOptions()
    options.add_argument("--disable-notifications")
    options.add_argument("--headless")  # للتشغيل في الخلفية
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    return driver

# تسجيل الدخول إلى إنستجرام
def insta_login(driver, username, password):
    driver.get("https://www.instagram.com/accounts/login/")
    time.sleep(3)
    driver.find_element(By.NAME, "username").send_keys(username)
    driver.find_element(By.NAME, "password").send_keys(password)
    driver.find_element(By.XPATH, "//button[@type='submit']").click()
    time.sleep(5)
    return "تم تسجيل الدخول بنجاح" if "instagram.com" in driver.current_url else "فشل تسجيل الدخول"

# نشر على إنستجرام
def insta_post(driver, image_path, caption=""):
    driver.get("https://www.instagram.com/")
    time.sleep(3)
    driver.find_element(By.XPATH, "//div[contains(@class, 'x1i10hfl')]").click()
    time.sleep(2)
    driver.find_element(By.XPATH, "//input[@type='file']").send_keys(os.path.abspath(image_path))
    time.sleep(3)
    driver.find_element(By.XPATH, "//div[contains(text(), 'التالي')]").click()
    time.sleep(2)
    driver.find_element(By.XPATH, "//textarea[@aria-label='اكتب تعليقًا...']").send_keys(caption)
    time.sleep(2)
    driver.find_element(By.XPATH, "//div[contains(text(), 'مشاركة')]").click()
    time.sleep(5)
    return True

# التحقق من الاشتراك في القنوات
async def check_subscription(update: Update):
    user_id = update.effective_user.id
    for channel in REQUIRED_CHANNELS:
        try:
            member = await context.bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status not in ["member", "administrator", "creator"]:
                return False
        except:
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
async def start(update: Update, context: CallbackContext):
    if not await check_subscription(update):
        await update.message.reply_text("يجب الاشتراك في القنوات التالية أولاً:\n" + "\n".join(REQUIRED_CHANNELS))
        return
    
    await update.message.reply_text(
        "مرحباً! بوت التحكم بحسابات إنستجرام\nاختر أحد الخيارات:",
        reply_markup=main_keyboard(update.effective_user.id)
    )

# إضافة حساب جديد
async def add_account(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("أرسل اسم مستخدم إنستجرام وكلمة المرور بهذا الشكل:\nusername:password")
    context.user_data['awaiting_credentials'] = True

# معالجة بيانات الحساب
async def handle_credentials(update: Update, context: CallbackContext):
    if 'awaiting_credentials' not in context.user_data:
        return
    
    try:
        username, password = update.message.text.split(":")
        user_id = update.effective_user.id
        
        conn = sqlite3.connect('instagram_bot.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO accounts VALUES (?, ?, ?, 0)", (user_id, username.strip(), password.strip()))
        conn.commit()
        conn.close()
        
        await update.message.reply_text("تم حفظ الحساب بنجاح!")
        context.user_data.pop('awaiting_credentials', None)
    except Exception as e:
        await update.message.reply_text(f"خطأ: {str(e)}\nيرجى المحاولة مرة أخرى")

# إدارة الحسابات
async def my_accounts(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    
    conn = sqlite3.connect('instagram_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT insta_username, is_active FROM accounts WHERE user_id=?", (user_id,))
    accounts = cursor.fetchall()
    conn.close()
    
    if not accounts:
        await query.answer("ليس لديك أي حسابات مسجلة")
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
async def manage_account(update: Update, context: CallbackContext):
    query = update.callback_query
    username = query.data.split("_")[1]
    
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
async def toggle_account(update: Update, context: CallbackContext):
    query = update.callback_query
    username = query.data.split("_")[1]
    user_id = query.from_user.id
    
    conn = sqlite3.connect('instagram_bot.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE accounts SET is_active = NOT is_active WHERE user_id=? AND insta_username=?", (user_id, username))
    conn.commit()
    conn.close()
    
    await query.answer("تم تغيير حالة الحساب")
    await my_accounts(update, context)

# حذف الحساب
async def delete_account(update: Update, context: CallbackContext):
    query = update.callback_query
    username = query.data.split("_")[1]
    user_id = query.from_user.id
    
    conn = sqlite3.connect('instagram_bot.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM accounts WHERE user_id=? AND insta_username=?", (user_id, username))
    conn.commit()
    conn.close()
    
    await query.answer("تم حذف الحساب")
    await my_accounts(update, context)

# معالجة الصور للنشر
async def handle_photo(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    # التحقق من وجود حساب مفعل
    conn = sqlite3.connect('instagram_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT insta_username, insta_password FROM accounts WHERE user_id=? AND is_active=1", (user_id,))
    account = cursor.fetchone()
    conn.close()
    
    if not account:
        await update.message.reply_text("ليس لديك حساب مفعل!")
        return
    
    # تنزيل الصورة
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    image_path = f"{file.file_id}.jpg"
    await file.download_to_drive(image_path)
    
    # النشر
    try:
        driver = setup_browser()
        login_status = insta_login(driver, account[0], account[1])
        
        if "نجاح" in login_status:
            caption = update.message.caption if update.message.caption else ""
            if insta_post(driver, image_path, caption):
                await update.message.reply_text("تم النشر بنجاح!")
            else:
                await update.message.reply_text("فشل النشر")
        else:
            await update.message.reply_text("فشل تسجيل الدخول إلى إنستجرام")
        
        driver.quit()
    except Exception as e:
        await update.message.reply_text(f"حدث خطأ: {str(e)}")
    finally:
        if os.path.exists(image_path):
            os.remove(image_path)

def main():
    updater = Updater(TOKEN)
    dp = updater.dispatcher
    
    # الأوامر
    dp.add_handler(CommandHandler("start", start))
    
    # الأزرار التفاعلية
    dp.add_handler(CallbackQueryHandler(add_account, pattern='^add_account$'))
    dp.add_handler(CallbackQueryHandler(my_accounts, pattern='^my_accounts$'))
    dp.add_handler(CallbackQueryHandler(manage_account, pattern='^manage_'))
    dp.add_handler(CallbackQueryHandler(toggle_account, pattern='^toggle_'))
    dp.add_handler(CallbackQueryHandler(delete_account, pattern='^delete_'))
    dp.add_handler(CallbackQueryHandler(my_accounts, pattern='^back$'))
    
    # معالجة الرسائل
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_credentials))
    dp.add_handler(MessageHandler(Filters.photo, handle_photo))
    
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main() 
