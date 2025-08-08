#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import sqlite3
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ======== إعدادات التكوين ========
TOKEN = "8299954739:AAHlkfRH4N0cDjv-IToJkXQwwIqYCtzcVCQ"
CHROME_BIN = "/usr/bin/chromium-browser"
REQUIRED_CHANNELS = ["@crazys7", "@AWU87"]
DB_NAME = "instagram_bot.db"
LOG_FILE = "bot_activity.log"

# إعداد التسجيل
logging.basicConfig(
    filename=LOG_FILE,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ======== إدارة قاعدة البيانات ========
def init_db():
    conn = sqlite3.connect(DB_NAME)
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

def add_account(user_id, username, password):
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO accounts (user_id, insta_username, insta_password)
            VALUES (?, ?, ?)
        ''', (user_id, username, password))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error adding account: {e}")
        return False
    finally:
        conn.close()

def get_user_accounts(user_id):
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT insta_username, is_active FROM accounts
            WHERE user_id = ?
        ''', (user_id,))
        return cursor.fetchall()
    except Exception as e:
        logger.error(f"Error getting accounts: {e}")
        return []
    finally:
        conn.close()

def delete_account(user_id, username):
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            DELETE FROM accounts
            WHERE user_id = ? AND insta_username = ?
        ''', (user_id, username))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Error deleting account: {e}")
        return False
    finally:
        conn.close()

# ======== عمليات إنستجرام ========
def init_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1280,720")
    chrome_options.binary_location = CHROME_BIN
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.implicitly_wait(10)
    return driver

def instagram_login(username, password):
    driver = init_driver()
    try:
        driver.get("https://www.instagram.com/accounts/login/")
        
        # ملء بيانات الدخول
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.NAME, "username"))
        ).send_keys(username)
        
        driver.find_element(By.NAME, "password").send_keys(password)
        
        # تحديد زر الدخول باستخدام XPath متعدد اللغات
        login_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((
                By.XPATH, 
                "//button[@type='submit' and (contains(., 'Log in') or contains(., 'تسجيل الدخول'))]"
            ))
        )
        login_button.click()
        
        # التحقق من نجاح الدخول
        WebDriverWait(driver, 15).until(
            EC.url_contains("instagram.com/accounts/one-tap")
            or EC.url_contains("instagram.com")
        )
        
        # كشف التحقق البشري
        if "challenge" in driver.current_url:
            return "يحتاج إلى تحقق بشري"
            
        return "تم تسجيل الدخول بنجاح ✅"
    except Exception as e:
        logger.error(f"Login error: {e}")
        return f"خطأ في تسجيل الدخول: {str(e)}"
    finally:
        driver.quit()

# ======== واجهة البوت ========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    keyboard = [
        [InlineKeyboardButton("📤 نشر الآن", callback_data='post_now')],
        [InlineKeyboardButton("🔐 تسجيل الدخول لحساب", callback_data='login_account')],
        [InlineKeyboardButton("👤 إدارة الحسابات", callback_data='manage_accounts')],
        [InlineKeyboardButton("➕ إضافة حساب", callback_data='add_account')]
    ]
    await update.message.reply_text(
        f"مرحبًا {update.effective_user.first_name}!\n"
        "اختر أحد الخيارات من لوحة التحكم:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    
    await query.answer()
    
    if data == 'add_account':
        await query.message.reply_text(
            "أرسل بيانات حساب إنستجرام كالتالي:\n"
            "<b>اسم المستخدم:كلمة المرور</b>\n"
            "مثال:\n"
            "<code>my_instagram:password123</code>",
            parse_mode='HTML'
        )
        context.user_data['awaiting_account'] = True
        
    elif data == 'post_now':
        accounts = get_user_accounts(user_id)
        if not accounts:
            await query.message.reply_text("ليس لديك أي حسابات مسجلة. أضف حساب أولاً.")
            return
            
        active_accounts = [acc[0] for acc in accounts if acc[1] == 1]
        if not active_accounts:
            await query.message.reply_text("ليس لديك حسابات مفعلة. قم بتفعيل حساب أولاً.")
            return
            
        await query.message.reply_text("أرسل الصورة الآن (مع تعليق اختياري في نفس الرسالة)")
        context.user_data['posting'] = True
        
    elif data == 'manage_accounts':
        accounts = get_user_accounts(user_id)
        if not accounts:
            await query.message.reply_text("ليس لديك حسابات مسجلة بعد.")
            return
            
        keyboard = []
        for username, is_active in accounts:
            status = "✅" if is_active else "❌"
            keyboard.append([
                InlineKeyboardButton(
                    f"{username} {status}", 
                    callback_data=f"account_{username}"
                )
            ])
            
        keyboard.append([InlineKeyboardButton("العودة", callback_data='back_to_main')])
        await query.message.reply_text(
            "حساباتك المسجلة:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif data == 'login_account':
        accounts = get_user_accounts(user_id)
        if not accounts:
            await query.message.reply_text("ليس لديك حسابات مسجلة. أضف حساب أولاً.")
            return
            
        keyboard = []
        for username, _ in accounts:
            keyboard.append([
                InlineKeyboardButton(
                    username, 
                    callback_data=f"login_{username}"
                )
            ])
            
        keyboard.append([InlineKeyboardButton("العودة", callback_data='back_to_main')])
        await query.message.reply_text(
            "اختر حساب لتسجيل الدخول:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif data == 'back_to_main':
        await start(query.message, context)
        
    elif data.startswith('account_'):
        username = data.split('_')[1]
        keyboard = [
            [
                InlineKeyboardButton("❌ حذف الحساب", callback_data=f"delete_{username}"),
                InlineKeyboardButton("🔄 تفعيل/تعطيل", callback_data=f"toggle_{username}")
            ],
            [InlineKeyboardButton("العودة", callback_data='manage_accounts')]
        ]
        await query.message.reply_text(
            f"إدارة الحساب: {username}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif data.startswith('login_'):
        username = data.split('_')[1]
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT insta_password FROM accounts
            WHERE user_id = ? AND insta_username = ?
        ''', (user_id, username))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            password = result[0]
            await query.message.reply_text(f"جاري تسجيل الدخول إلى {username}...")
            login_result = instagram_login(username, password)
            await query.message.reply_text(login_result)
        else:
            await query.message.reply_text("الحساب غير موجود!")

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message = update.message
    
    # معالجة إضافة الحساب
    if context.user_data.get('awaiting_account'):
        if ':' not in message.text:
            await message.reply_text("صيغة غير صحيحة! أرسل كـ username:password")
            return
            
        username, password = message.text.split(':', 1)
        if add_account(user_id, username.strip(), password.strip()):
            await message.reply_text(f"تمت إضافة حساب {username} بنجاح! ✅")
        else:
            await message.reply_text("فشل في إضافة الحساب. حاول مرة أخرى.")
            
        context.user_data.pop('awaiting_account', None)
    
    # معالجة النشر
    elif context.user_data.get('posting'):
        # هنا سيتم تنفيذ عملية النشر الفعلية
        # (التنفيذ الكامل يتطلب معالجة الصور)
        caption = message.caption if message.caption else ""
        await message.reply_text(
            f"تم استلام المحتوى للنشر!\n"
            f"التعليق: {caption[:50]}...\n"
            "سيتم تنفيذ النشر قريبًا."
        )
        context.user_data.pop('posting', None)

def main():
    # تهيئة قاعدة البيانات
    init_db()
    
    # إنشاء تطبيق البوت
    application = Application.builder().token(TOKEN).build()
    
    # تسجيل المعالجات
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages))
    
    # بدء البوت
    application.run_polling()
    logger.info("Bot started successfully")

if __name__ == "__main__":
    main()
