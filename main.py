import os
import sqlite3
import logging
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
import time
import threading
from PIL import Image

# إعدادات التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# إعدادات البوت
TOKEN = "8299954739:AAHlkfRH4N0cDjv-IToJkXQwwIqYCtzcVCQ"
REQUIRED_CHANNELS = ["@crazys7", "@AWU87"]
bot = telebot.TeleBot(TOKEN)

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
def check_subscription(user_id):
    try:
        for channel in REQUIRED_CHANNELS:
            member = bot.get_chat_member(channel, user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                return False
        return True
    except Exception:
        return False

# إعداد المتصفح
def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.binary_location = "/usr/bin/chromium-browser"
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)

# عرض لوحة التحكم
def show_main_menu(chat_id):
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("📤 نشر الآن", callback_data="post_now"),
        InlineKeyboardButton("🔐 تسجيل الدخول", callback_data="login_account")
    )
    markup.add(
        InlineKeyboardButton("👤 إدارة الحسابات", callback_data="manage_accounts"),
        InlineKeyboardButton("➕ إضافة حساب", callback_data="add_account")
    )
    markup.add(InlineKeyboardButton("❓ مساعدة", callback_data="help"))
    bot.send_message(chat_id, "🤖 لوحة التحكم الرئيسية:", reply_markup=markup)

# /start
@bot.message_handler(commands=['start'])
def start(message):
    if not check_subscription(message.from_user.id):
        channels = "\n".join([f"• {ch}" for ch in REQUIRED_CHANNELS])
        bot.send_message(
            message.chat.id,
            f"⚠️ يجب الاشتراك في القنوات التالية أولاً:\n{channels}\n\nبعد الاشتراك، أعد إرسال /start"
        )
        return
    show_main_menu(message.chat.id)

# معالجة الاستعلامات
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    user_id = call.from_user.id
    data = call.data

    if data == "add_account":
        msg = bot.send_message(call.message.chat.id, "➕ أرسل بيانات الحساب بالصيغة:\nusername:password")
        bot.register_next_step_handler(msg, process_add_account)

    elif data == "manage_accounts":
        conn = sqlite3.connect('instagram_bot.db')
        c = conn.cursor()
        accounts = c.execute("SELECT insta_username, is_active FROM accounts WHERE user_id=?", (user_id,)).fetchall()
        conn.close()
        if not accounts:
            bot.send_message(call.message.chat.id, "لا توجد حسابات مضافة.")
            return

        markup = InlineKeyboardMarkup()
        for username, active in accounts:
            status = "✅" if active else "❌"
            markup.add(
                InlineKeyboardButton(f"{status} {username}", callback_data=f"toggle_{username}"),
                InlineKeyboardButton("🗑 حذف", callback_data=f"delete_{username}")
            )
        markup.add(InlineKeyboardButton("🔙 رجوع", callback_data="back"))
        bot.edit_message_text("👤 إدارة الحسابات:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif data.startswith("toggle_"):
        username = data.split("_")[1]
        conn = sqlite3.connect('instagram_bot.db')
        c = conn.cursor()
        current = c.execute("SELECT is_active FROM accounts WHERE user_id=? AND insta_username=?", (user_id, username)).fetchone()[0]
        new_status = 0 if current else 1
        c.execute("UPDATE accounts SET is_active=? WHERE user_id=? AND insta_username=?", (new_status, user_id, username))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, f"تم {'تفعيل' if new_status else 'تعطيل'} الحساب {username}")
        callback_query(call)  # إعادة تحميل القائمة

    elif data.startswith("delete_"):
        username = data.split("_")[1]
        conn = sqlite3.connect('instagram_bot.db')
        c = conn.cursor()
        c.execute("DELETE FROM accounts WHERE user_id=? AND insta_username=?", (user_id, username))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, f"تم حذف الحساب {username}")
        callback_query(call)

    elif data == "login_account":
        conn = sqlite3.connect('instagram_bot.db')
        c = conn.cursor()
        accounts = c.execute("SELECT insta_username FROM accounts WHERE user_id=? AND is_active=1", (user_id,)).fetchall()
        conn.close()
        if not accounts:
            bot.send_message(call.message.chat.id, "لا توجد حسابات مفعلة.")
            return

        markup = InlineKeyboardMarkup()
        for acc in accounts:
            markup.add(InlineKeyboardButton(acc[0], callback_data=f"login_{acc[0]}"))
        markup.add(InlineKeyboardButton("🔙 رجوع", callback_data="back"))
        bot.edit_message_text("اختر حساباً لتسجيل الدخول:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif data.startswith("login_"):
        username = data.split("_")[1]
        conn = sqlite3.connect('instagram_bot.db')
        password = c.execute("SELECT insta_password FROM accounts WHERE user_id=? AND insta_username=?", (user_id, username)).fetchone()[0]
        conn.close()
        bot.edit_message_text(f"🔄 جاري تسجيل الدخول للحساب {username}...", call.message.chat.id, call.message.message_id)
        threading.Thread(target=login_instagram, args=(call.message.chat.id, username, password)).start()

    elif data == "post_now":
        conn = sqlite3.connect('instagram_bot.db')
        c = conn.cursor()
        accounts = c.execute("SELECT insta_username FROM accounts WHERE user_id=? AND is_active=1", (user_id,)).fetchall()
        conn.close()
        if not accounts:
            bot.send_message(call.message.chat.id, "لا توجد حسابات مفعلة.")
            return

        markup = InlineKeyboardMarkup()
        for acc in accounts:
            markup.add(InlineKeyboardButton(acc[0], callback_data=f"post_{acc[0]}"))
        markup.add(InlineKeyboardButton("🔙 رجوع", callback_data="back"))
        bot.edit_message_text("اختر حساباً للنشر:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif data.startswith("post_"):
        username = data.split("_")[1]
        bot.edit_message_text("📤 أرسل الصورة الآن (مع تعليق اختياري):", call.message.chat.id, call.message.message_id)
        bot.register_next_step_handler(call.message, process_post_image, username)

    elif data == "help":
        bot.send_message(call.message.chat.id, "❓ دليل الاستخدام:\n📤 نشر الآن\n🔐 تسجيل الدخول\n👤 إدارة الحسابات\n➕ إضافة حساب")

    elif data == "back":
        show_main_menu(call.message.chat.id)

# إضافة حساب
def process_add_account(message):
    try:
        username, password = message.text.strip().split(":", 1)
        conn = sqlite3.connect('instagram_bot.db')
        c = conn.cursor()
        c.execute("INSERT INTO accounts (user_id, insta_username, insta_password) VALUES (?, ?, ?)", (message.from_user.id, username.strip(), password.strip()))
        conn.commit()
        conn.close()
        bot.send_message(message.chat.id, f"✅ تم إضافة الحساب {username.strip()}")
    except Exception:
        bot.send_message(message.chat.id, "❌ الصيغة غير صحيحة. استخدم: username:password")
    show_main_menu(message.chat.id)

# نشر صورة
def process_post_image(message, username):
    if not message.photo:
        bot.send_message(message.chat.id, "❌ من فضلك أرسل صورة.")
        return

    caption = message.caption or ""
    file_info = bot.get_file(message.photo[-1].file_id)
    downloaded_file = bot.download_file(file_info.file_path)

    with open("temp_post.jpg", "wb") as f:
        f.write(downloaded_file)

    conn = sqlite3.connect('instagram_bot.db')
    c = cursor = conn.cursor()
    password = c.execute("SELECT insta_password FROM accounts WHERE user_id=? AND insta_username=?", (message.from_user.id, username)).fetchone()[0]
    conn.close()

    bot.send_message(message.chat.id, "🔄 جاري النشر...")
    threading.Thread(target=post_to_instagram, args=(message.chat.id, username, password, "temp_post.jpg", caption)).start()

# تسجيل الدخول
def login_instagram(chat_id, username, password):
    driver = setup_driver()
    try:
        driver.get("https://www.instagram.com/accounts/login/")
        time.sleep(3)

        driver.find_element(By.NAME, "username").send_keys(username)
        driver.find_element(By.NAME, "password").send_keys(password)
        driver.find_element(By.XPATH, "//button[@type='submit']").click()
        time.sleep(5)

        if "accounts/login" not in driver.current_url:
            bot.send_message(chat_id, f"✅ تم تسجيل الدخول للحساب {username}")
        else:
            bot.send_message(chat_id, f"❌ فشل تسجيل الدخول للحساب {username}")
    except Exception as e:
        bot.send_message(chat_id, f"❌ خطأ: {str(e)}")
    finally:
        driver.quit()

# النشر على إنستجرام
def post_to_instagram(chat_id, username, password, image_path, caption):
    driver = setup_driver()
    try:
        driver.get("https://www.instagram.com/accounts/login/")
        time.sleep(3)
        driver.find_element(By.NAME, "username").send_keys(username)
        driver.find_element(By.NAME, "password").send_keys(password)
        driver.find_element(By.XPATH, "//button[@type='submit']").click()
        time.sleep(5)

        if "accounts/login" in driver.current_url:
            bot.send_message(chat_id, "❌ فشل تسجيل الدخول.")
            return

        driver.get("https://www.instagram.com/")
        time.sleep(3)

        driver.find_element(By.XPATH, "//*[contains(@aria-label, 'New post')]").click()
        time.sleep(2)

        upload_input = driver.find_element(By.XPATH, "//input[@type='file']")
        upload_input.send_keys(os.path.abspath(image_path))
        time.sleep(3)

        driver.find_element(By.XPATH, "//button[text()='Next']").click()
        time.sleep(2)

        if caption:
            driver.find_element(By.XPATH, "//textarea[@aria-label='Write a caption...']").send_keys(caption)
        time.sleep(2)

        driver.find_element(By.XPATH, "//button[text()='Share']").click()
        time.sleep(5)
        bot.send_message(chat_id, "✅ تم نشر الصورة بنجاح!")
    except Exception as e:
        bot.send_message(chat_id, f"❌ خطأ في النشر: {str(e)}")
    finally:
        driver.quit()
        if os.path.exists(image_path):
            os.remove(image_path)

# تشغيل البوت
if __name__ == '__main__':
    init_db()
    print("🤖 البوت يعمل الآن...")
    bot.polling(none_stop=True)
 
