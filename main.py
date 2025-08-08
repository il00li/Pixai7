#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import sqlite3
import os
import time
import re
import requests
from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
    InputMediaPhoto
)
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
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ======== إعدادات التكوين ========
TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"  # استبدل بتابع البوت الخاص بك
CHROME_BIN = "/usr/bin/chromium"  # المسار الصحيح للمتصفح
REQUIRED_CHANNELS = ["@crazys7", "@AWU87"]  # قنوات الاشتراك الإجباري
DB_NAME = "instagram_bot.db"
LOG_FILE = "bot_activity.log"
TEMP_DIR = "temp_files"
MAX_LOGIN_ATTEMPTS = 2

# إنشاء مجلد الملفات المؤقتة
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)

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
            login_attempts INTEGER DEFAULT 0,
            last_login INTEGER DEFAULT 0,
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
            INSERT OR REPLACE INTO accounts 
            (user_id, insta_username, insta_password, is_active)
            VALUES (?, ?, ?, ?)
        ''', (user_id, username, password, 1))  # تفعيل الحساب تلقائياً
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

def get_account_credentials(user_id, username):
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT insta_password, login_attempts, last_login FROM accounts
            WHERE user_id = ? AND insta_username = ?
        ''', (user_id, username))
        return cursor.fetchone()
    except Exception as e:
        logger.error(f"Error getting credentials: {e}")
        return None
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

def toggle_account_status(user_id, username):
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE accounts
            SET is_active = NOT is_active
            WHERE user_id = ? AND insta_username = ?
        ''', (user_id, username))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error toggling account status: {e}")
        return False
    finally:
        conn.close()

def update_login_attempts(user_id, username, success):
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        if success:
            cursor.execute('''
                UPDATE accounts
                SET login_attempts = 0, last_login = ?
                WHERE user_id = ? AND insta_username = ?
            ''', (int(time.time()), user_id, username))
        else:
            cursor.execute('''
                UPDATE accounts
                SET login_attempts = login_attempts + 1, last_login = ?
                WHERE user_id = ? AND insta_username = ?
            ''', (int(time.time()), user_id, username))
            
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error updating login attempts: {e}")
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
    chrome_options.add_argument("--lang=en-US")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    
    if CHROME_BIN:
        chrome_options.binary_location = CHROME_BIN
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.implicitly_wait(15)
    return driver

def instagram_login(username, password):
    driver = init_driver()
    try:
        driver.get("https://www.instagram.com/accounts/login/")
        time.sleep(3)
        
        # محاولة التعامل مع ملفات تعريف الارتباط
        try:
            cookie_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Allow') or contains(text(), 'موافق')]"))
            )
            cookie_button.click()
            time.sleep(1)
        except:
            pass
        
        # إدخال اسم المستخدم وكلمة المرور
        username_field = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.NAME, "username"))
        )
        username_field.clear()
        username_field.send_keys(username)
        
        password_field = driver.find_element(By.NAME, "password")
        password_field.clear()
        password_field.send_keys(password)
        
        # الضغط على زر تسجيل الدخول
        try:
            login_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((
                    By.XPATH, 
                    "//button[@type='submit' and (contains(., 'Log in') or contains(., 'تسجيل الدخول'))]"
                ))
            )
            login_button.click()
        except:
            # بديل: استخدام Enter
            password_field.send_keys(Keys.RETURN)
        
        # الانتظار للتحقق من نجاح الدخول
        time.sleep(5)
        
        # التحقق من الصفحة الرئيسية
        if "instagram.com/accounts/one-tap" in driver.current_url or "instagram.com" in driver.current_url:
            # التأكد من ظهور شريط البحث
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.XPATH, "//input[@placeholder='Search']"))
            )
            return "تم تسجيل الدخول بنجاح ✅"
        
        # التحقق من الحاجة إلى تحقق بخطوتين
        if "two-factor" in driver.current_url:
            return "يحتاج إلى تحقق بخطوتين"
            
        # التحقق من وجود تحدٍ أمني
        if "challenge" in driver.current_url:
            return "يحتاج إلى تحقق بشري (Captcha)"
            
        # أخذ لقطة شاشة للتحليل
        timestamp = int(time.time())
        screenshot_path = f"{TEMP_DIR}/login_error_{username}_{timestamp}.png"
        driver.save_screenshot(screenshot_path)
        
        return "فشل في تسجيل الدخول. تم حفظ لقطة شاشة للتحليل."
        
    except Exception as e:
        logger.error(f"Login error for {username}: {e}")
        return f"خطأ في تسجيل الدخول: {str(e)}"
    finally:
        driver.quit()

def post_to_instagram(username, password, image_path, caption=""):
    driver = init_driver()
    try:
        # تسجيل الدخول
        login_result = instagram_login(username, password)
        if not login_result.startswith("تم تسجيل الدخول بنجاح"):
            return login_result
        
        # الانتقال إلى صفحة إنشاء منشور جديد
        driver.get("https://www.instagram.com/create")
        time.sleep(3)
        
        # رفع الصورة
        file_input = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, "//input[@type='file']"))
        )
        file_input.send_keys(os.path.abspath(image_path))
        
        # الانتظار حتى يتم تحميل الصورة
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, "//div[contains(@aria-label, 'Edit image')]"))
        )
        time.sleep(2)
        
        # الانتقال إلى الخطوة التالية
        next_button = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(text(), 'Next') or contains(text(), 'التالي')]"))
        )
        next_button.click()
        time.sleep(1)
        
        # الانتقال إلى الخطوة التالية مرة أخرى
        next_button = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(text(), 'Next') or contains(text(), 'التالي')]"))
        )
        next_button.click()
        time.sleep(1)
        
        # إضافة تعليق إذا كان موجوداً
        if caption:
            caption_area = WebDriverWait(driver, 15).until(
                EC.element_to_be_clickable((By.XPATH, "//div[@aria-label='Write a caption...' or @aria-label='اكتب تعليقاً...']"))
            )
            actions = ActionChains(driver)
            actions.click(caption_area)
            
            # تقسيم الكابتشن إلى أجزاء صغيرة
            for part in [caption[i:i+100] for i in range(0, len(caption), 100)]:
                actions.send_keys(part)
                actions.perform()
                time.sleep(0.1)
        
        # النشر النهائي
        share_button = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(text(), 'Share') or contains(text(), 'مشاركة')]"))
        )
        share_button.click()
        
        # التأكد من نجاح النشر
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Your post has been shared') or contains(text(), 'تمت مشاركة منشورك')]"))
        )
        time.sleep(2)
        
        # أخذ لقطة شاشة للتحقق
        timestamp = int(time.time())
        screenshot_path = f"{TEMP_DIR}/post_success_{username}_{timestamp}.png"
        driver.save_screenshot(screenshot_path)
        
        return "تم النشر بنجاح على إنستجرام! ✅"
    except Exception as e:
        logger.error(f"Posting error for {username}: {e}")
        
        # أخذ لقطة شاشة عند الخطأ
        timestamp = int(time.time())
        screenshot_path = f"{TEMP_DIR}/post_error_{username}_{timestamp}.png"
        driver.save_screenshot(screenshot_path)
        
        return f"خطأ في النشر: {str(e)}"
    finally:
        driver.quit()

# ======== نظام الأمان والتحقق ========
async def verify_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        for channel in REQUIRED_CHANNELS:
            chat_member = await context.bot.get_chat_member(chat_id=channel, user_id=user_id)
            if chat_member.status not in ['member', 'administrator', 'creator']:
                return False
        return True
    except Exception as e:
        logger.error(f"Subscription verification error: {e}")
        return False

def subscription_channels_markup():
    buttons = [[InlineKeyboardButton(channel, url=f"https://t.me/{channel[1:]}")] for channel in REQUIRED_CHANNELS]
    buttons.append([InlineKeyboardButton("✅ تأكيد الاشتراك", callback_data='check_subscription')])
    return InlineKeyboardMarkup(buttons)

# ======== واجهة البوت ========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    
    # التحقق من الاشتراك أولاً
    if not await verify_subscription(update, context):
        await update.message.reply_text(
            "⚠️ يجب عليك الاشتراك في القنوات التالية أولاً:",
            reply_markup=subscription_channels_markup()
        )
        return
    
    keyboard = [
        [InlineKeyboardButton("📤 نشر الآن", callback_data='post_now')],
        [InlineKeyboardButton("🔐 تسجيل الدخول لحساب", callback_data='login_account')],
        [InlineKeyboardButton("👤 إدارة الحسابات", callback_data='manage_accounts')],
        [InlineKeyboardButton("➕ إضافة حساب", callback_data='add_account')],
        [InlineKeyboardButton("ℹ️ المساعدة", callback_data='help')]
    ]
    
    await update.message.reply_text(
        f"مرحبًا {username} 👋\n"
        "بوت متكامل لإدارة ونشر المحتوى على إنستجرام\n"
        "اختر أحد الخيارات من لوحة التحكم:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🎯 <b>دليل استخدام البوت</b>\n\n"
        "📌 <b>إضافة حساب</b>:\n"
        "1. اختر 'إضافة حساب'\n"
        "2. أرسل بيانات الحساب كـ username:password\n"
        "3. سيقوم البوت بتفعيل الحساب تلقائياً\n\n"
        
        "📌 <b>تسجيل الدخول</b>:\n"
        "1. اختر 'تسجيل الدخول لحساب'\n"
        "2. اختر الحساب من القائمة\n"
        "3. سيقوم البوت بتسجيل الدخول ويخبرك بالنتيجة\n\n"
        
        "📌 <b>النشر على إنستجرام</b>:\n"
        "1. اختر 'نشر الآن'\n"
        "2. اختر الحساب المراد النشر عليه\n"
        "3. أرسل الصورة مع التعليق (اختياري)\n"
        "4. سيقوم البوت بالنشر على الحساب المحدد\n\n"
        
        "📌 <b>إدارة الحسابات</b>:\n"
        "1. اختر 'إدارة الحسابات'\n"
        "2. اختر الحساب الذي تريد إدارته\n"
        "3. يمكنك تفعيل/تعطيل أو حذف الحساب\n\n"
        
        "⚙️ <b>الدعم الفني</b>: @crazys7\n"
        "📣 <b>قناة التحديثات</b>: @AWU87"
    )
    
    await update.message.reply_text(help_text, parse_mode='HTML')

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    
    await query.answer()
    
    # التحقق من الاشتراك أولاً
    if not await verify_subscription(update, context):
        await query.message.reply_text(
            "⚠️ يجب عليك الاشتراك في القنوات التالية أولاً:",
            reply_markup=subscription_channels_markup()
        )
        return
    
    if data == 'add_account':
        await query.message.reply_text(
            "📝 <b>أرسل بيانات حساب إنستجرام كالتالي:</b>\n"
            "<code>اسم المستخدم:كلمة المرور</code>\n\n"
            "مثال:\n"
            "<code>my_instagram:password123</code>",
            parse_mode='HTML'
        )
        context.user_data['awaiting_account'] = True
        
    elif data == 'post_now':
        accounts = get_user_accounts(user_id)
        if not accounts:
            await query.message.reply_text("⚠️ ليس لديك أي حسابات مسجلة. أضف حساب أولاً.")
            return
            
        active_accounts = [acc[0] for acc in accounts if acc[1] == 1]
        if not active_accounts:
            await query.message.reply_text("⚠️ ليس لديك حسابات مفعلة. قم بتفعيل حساب أولاً.")
            return
            
        context.user_data['posting'] = {
            'step': 'select_account'
        }
        
        keyboard = [[InlineKeyboardButton(acc, callback_data=f"acc_{acc}")] for acc in active_accounts]
        keyboard.append([InlineKeyboardButton("إلغاء", callback_data='cancel')])
        
        await query.message.reply_text(
            "🔘 اختر الحساب للنشر:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif data == 'manage_accounts':
        accounts = get_user_accounts(user_id)
        if not accounts:
            await query.message.reply_text("⚠️ ليس لديك حسابات مسجلة بعد.")
            return
            
        keyboard = []
        for username, is_active in accounts:
            status = "✅ مفعل" if is_active else "❌ غير مفعل"
            keyboard.append([
                InlineKeyboardButton(
                    f"{username} - {status}", 
                    callback_data=f"account_{username}"
                )
            ])
            
        keyboard.append([InlineKeyboardButton("العودة", callback_data='back_to_main')])
        await query.message.reply_text(
            "📋 حساباتك المسجلة:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif data == 'login_account':
        accounts = get_user_accounts(user_id)
        if not accounts:
            await query.message.reply_text("⚠️ ليس لديك حسابات مسجلة. أضف حساب أولاً.")
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
            "🔑 اختر حساب لتسجيل الدخول:",
            reply_markup=InlineKeyboardMarkup(keyboard))
        
    elif data == 'back_to_main':
        await start(update, context)
        
    elif data == 'cancel':
        if 'posting' in context.user_data:
            del context.user_data['posting']
        await query.message.reply_text("تم الإلغاء")
        await start(update, context)
        
    elif data == 'help':
        await help_command(update, context)
        
    elif data == 'check_subscription':
        if await verify_subscription(update, context):
            await query.message.reply_text("✅ أنت مشترك في جميع القنوات المطلوبة!")
            await start(update, context)
        else:
            await query.message.reply_text(
                "❌ لم يتم التحقق من اشتراكك في جميع القنوات!",
                reply_markup=subscription_channels_markup()
            )
        
    elif data.startswith('account_'):
        username = data.split('_')[1]
        keyboard = [
            [
                InlineKeyboardButton("🗑 حذف الحساب", callback_data=f"delete_{username}"),
                InlineKeyboardButton("🔄 تفعيل/تعطيل", callback_data=f"toggle_{username}")
            ],
            [InlineKeyboardButton("العودة", callback_data='manage_accounts')]
        ]
        await query.message.reply_text(
            f"⚙️ إدارة الحساب: <b>{username}</b>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard))
        
    elif data.startswith('login_'):
        username = data.split('_')[1]
        credentials = get_account_credentials(user_id, username)
        
        if not credentials:
            await query.message.reply_text("❌ الحساب غير موجود!")
            return
            
        password, login_attempts, last_login = credentials
        
        # التحقق من عدد محاولات الدخول الفاشلة
        if login_attempts >= MAX_LOGIN_ATTEMPTS:
            await query.message.reply_text("⚠️ تم تجاوز الحد الأقصى لمحاولات الدخول. حاول لاحقاً.")
            return
            
        await query.message.reply_text(f"⏳ جاري تسجيل الدخول إلى {username}...")
        
        # تنفيذ عملية الدخول
        login_result = instagram_login(username, password)
        
        # تحديث حالة المحاولة
        success = "تم تسجيل الدخول بنجاح" in login_result
        update_login_attempts(user_id, username, success)
        
        await query.message.reply_text(login_result)
        
    elif data.startswith('delete_'):
        username = data.split('_')[1]
        if delete_account(user_id, username):
            await query.message.reply_text(f"✅ تم حذف حساب {username} بنجاح!")
        else:
            await query.message.reply_text(f"❌ فشل في حذف حساب {username}!")
            
    elif data.startswith('toggle_'):
        username = data.split('_')[1]
        if toggle_account_status(user_id, username):
            await query.message.reply_text(f"✅ تم تغيير حالة حساب {username} بنجاح!")
        else:
            await query.message.reply_text(f"❌ فشل في تغيير حالة حساب {username}!")
            
    elif data.startswith('acc_'):
        if 'posting' not in context.user_data:
            await query.message.reply_text("❌ جلسة النشر منتهية، ابدأ العملية من جديد")
            return
            
        username = data.split('_')[1]
        context.user_data['posting']['selected_account'] = username
        context.user_data['posting']['step'] = 'awaiting_image'
        
        await query.message.reply_text(
            f"📤 جاهز لنشر صورة على حساب {username}\n"
            "أرسل الصورة الآن (مع تعليق اختياري)"
        )

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message = update.message
    
    # التحقق من الاشتراك أولاً
    if not await verify_subscription(update, context):
        await message.reply_text(
            "⚠️ يجب عليك الاشتراك في القنوات التالية أولاً:",
            reply_markup=subscription_channels_markup()
        )
        return
    
    # معالجة إضافة الحساب
    if context.user_data.get('awaiting_account'):
        if ':' not in message.text:
            await message.reply_text("❌ صيغة غير صحيحة! أرسل كـ username:password")
            return
            
        parts = message.text.split(':', 1)
        if len(parts) < 2:
            await message.reply_text("❌ صيغة غير صحيحة! أرسل كـ username:password")
            return
            
        username, password = parts
        username = username.strip()
        password = password.strip()
        
        if not username or not password:
            await message.reply_text("❌ اسم المستخدم أو كلمة المرور فارغة!")
            return
            
        if add_account(user_id, username, password):
            await message.reply_text(f"✅ تمت إضافة حساب {username} بنجاح! (تم تفعيله تلقائياً)")
        else:
            await message.reply_text("❌ فشل في إضافة الحساب. حاول مرة أخرى.")
            
        context.user_data.pop('awaiting_account', None)
    
    # معالجة النشر
    elif context.user_data.get('posting') and context.user_data['posting'].get('step') == 'awaiting_image':
        if not message.photo:
            await message.reply_text("❌ يرجى إرسال صورة صالحة!")
            return
            
        # حفظ الصورة مؤقتاً
        photo_file = await message.photo[-1].get_file()
        file_path = os.path.join(TEMP_DIR, f"{user_id}_{int(time.time())}.jpg")
        await photo_file.download_to_drive(file_path)
        
        # حفظ الكابتشن
        caption = message.caption if message.caption else ""
        
        account = context.user_data['posting'].get('selected_account', '')
        
        # الحصول على بيانات الحساب
        credentials = get_account_credentials(user_id, account)
        if not credentials:
            await message.reply_text("❌ بيانات الحساب غير موجودة!")
            # تنظيف الملف المؤقت
            try:
                os.remove(file_path)
            except:
                pass
            return
            
        password = credentials[0]
        
        await message.reply_text(f"⏳ جاري النشر على حساب {account}...")
        
        # تنفيذ عملية النشر
        result = post_to_instagram(account, password, file_path, caption)
        
        # إرسال النتيجة
        await message.reply_text(result)
        
        # تنظيف الملف المؤقت
        try:
            os.remove(file_path)
        except:
            pass
        
        # تنظيف بيانات المستخدم
        del context.user_data['posting']

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"حدث خطأ: {context.error}")
    
    if update and hasattr(update, 'message'):
        await update.message.reply_text(
            "⚠️ حدث خطأ غير متوقع. الرجاء المحاولة لاحقًا أو الاتصال بالدعم @crazys7"
        )

def main():
    # تهيئة قاعدة البيانات
    init_db()
    
    # إنشاء تطبيق البوت
    application = Application.builder().token(TOKEN).build()
    
    # تسجيل المعالجات
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_messages))
    
    # تسجيل معالج الأخطاء
    application.add_error_handler(error_handler)
    
    # بدء البوت
    logger.info("جاري تشغيل البوت...")
    application.run_polling()
    logger.info("تم تشغيل البوت بنجاح")

if __name__ == "__main__":
    main() 
