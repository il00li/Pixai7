import os
import sqlite3
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
import time
import threading

TOKEN = os.getenv("TOKEN", "8299954739:AAHlkfRH4N0cDjv-IToJkXQwwIqYCtzcVCQ")
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
    conn.commit(); conn.close()

# التحقق من الاشتراك
def check_subscription(uid):
    try:
        for ch in REQUIRED_CHANNELS:
            if bot.get_chat_member(ch, uid).status not in ['member', 'administrator', 'creator']:
                return False
        return True
    except:
        return False

# إعداد المتصفح
def setup_driver():
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)

# عرض القائمة الرئيسية
def main_menu(cid):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📤 نشر الآن", callback_data="post_now"),
               InlineKeyboardButton("🔐 تسجيل الدخول", callback_data="login_account"))
    markup.add(InlineKeyboardButton("👤 إدارة الحسابات", callback_data="manage_accounts"),
               InlineKeyboardButton("➕ إضافة حساب", callback_data="add_account"))
    markup.add(InlineKeyboardButton("❓ مساعدة", callback_data="help"))
    bot.send_message(cid, "🤖 لوحة التحكم الرئيسية:", reply_markup=markup)

@bot.message_handler(commands=['start'])
def start(message):
    if not check_subscription(message.from_user.id):
        bot.reply_to(message, "⚠️ يجب الاشتراك في @crazys7 و @AWU87 أولاً.")
        return
    main_menu(message.chat.id)

# إضافة حساب
@bot.callback_query_handler(func=lambda call: call.data == "add_account")
def ask_account(call):
    msg = bot.send_message(call.message.chat.id, "➕ أرسل username:password")
    bot.register_next_step_handler(msg, save_account)

def save_account(message):
    try:
        u, p = message.text.strip().split(":", 1)
        conn = sqlite3.connect('instagram_bot.db')
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO accounts VALUES (?,?,?,1)", (message.from_user.id, u.strip(), p.strip()))
        conn.commit(); conn.close()
        bot.reply_to(message, f"✅ تم إضافة الحساب {u.strip()}")
    except:
        bot.reply_to(message, "❌ الصيغة غير صحيحة.")
    main_menu(message.chat.id)

# إدارة الحسابات
@bot.callback_query_handler(func=lambda call: call.data == "manage_accounts")
def manage(call):
    conn = sqlite3.connect('instagram_bot.db')
    accs = conn.execute("SELECT insta_username, is_active FROM accounts WHERE user_id=?", (call.from_user.id,)).fetchall()
    conn.close()
    if not accs:
        bot.answer_callback_query(call.id, "لا توجد حسابات"); return
    markup = InlineKeyboardMarkup()
    for u, a in accs:
        markup.add(InlineKeyboardButton(("✅ " if a else "❌") + u, callback_data=f"toggle_{u}"),
                   InlineKeyboardButton("🗑", callback_data=f"del_{u}"))
    markup.add(InlineKeyboardButton("🔙 رجوع", callback_data="back"))
    bot.edit_message_text("👤 إدارة الحسابات:", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("toggle_"))
def toggle(call):
    u = call.data[7:]
    conn = sqlite3.connect('instagram_bot.db')
    cur = conn.execute("SELECT is_active FROM accounts WHERE user_id=? AND insta_username=?", (call.from_user.id, u)).fetchone()[0]
    conn.execute("UPDATE accounts SET is_active=? WHERE user_id=? AND insta_username=?", (1-cur, call.from_user.id, u))
    conn.commit(); conn.close()
    bot.answer_callback_query(call.id, "تم التبديل")
    manage(call)

@bot.callback_query_handler(func=lambda call: call.data.startswith("del_"))
def delete(call):
    u = call.data[4:]
    conn = sqlite3.connect('instagram_bot.db')
    conn.execute("DELETE FROM accounts WHERE user_id=? AND insta_username=?", (call.from_user.id, u))
    conn.commit(); conn.close()
    bot.answer_callback_query(call.id, f"تم حذف {u}")
    manage(call)

# تسجيل الدخول
@bot.callback_query_handler(func=lambda call: call.data.startswith("login_"))
def login(call):
    u = call.data[6:]
    conn = sqlite3.connect('instagram_bot.db')
    p = conn.execute("SELECT insta_password FROM accounts WHERE user_id=? AND insta_username=?", (call.from_user.id, u)).fetchone()[0]
    conn.close()
    bot.edit_message_text(f"🔄 تسجيل دخول {u}...", call.message.chat.id, call.message.message_id)
    threading.Thread(target=do_login, args=(call.message.chat.id, u, p)).start()

def do_login(cid, u, p):
    d = setup_driver()
    try:
        d.get("https://www.instagram.com/accounts/login/")
        d.find_element(By.NAME, "username").send_keys(u)
        d.find_element(By.NAME, "password").send_keys(p)
        d.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        time.sleep(5)
        bot.send_message(cid, "✅ تم تسجيل الدخول بنجاح" if "accounts/login" not in d.current_url else "❌ فشل تسجيل الدخول")
    except Exception as e:
        bot.send_message(cid, f"❌ خطأ: {e}")
    finally:
        d.quit()

# النشر
@bot.callback_query_handler(func=lambda call: call.data.startswith("post_"))
def ask_img(call):
    u = call.data[5:]
    bot.edit_message_text("📤 أرسل الصورة مع تعليق اختياري:", call.message.chat.id, call.message.message_id)
    bot.register_next_step_handler(call.message, receive_img, u)

def receive_img(message, u):
    if not message.photo:
        bot.reply_to(message, "❌ من فضلك أرسل صورة"); return
    file_info = bot.get_file(message.photo[-1].file_id)
    downloaded = bot.download_file(file_info.file_path)
    with open("temp.jpg", "wb") as f:
        f.write(downloaded)
    conn = sqlite3.connect('instagram_bot.db')
    p = conn.execute("SELECT insta_password FROM accounts WHERE user_id=? AND insta_username=?", (message.from_user.id, u)).fetchone()[0]
    conn.close()
    bot.reply_to(message, "🔄 جاري النشر...")
    threading.Thread(target=do_post, args=(message.chat.id, u, p, "temp.jpg", message.caption or "")).start()

def do_post(cid, u, p, img, cap):
    d = setup_driver()
    try:
        d.get("https://www.instagram.com/accounts/login/")
        d.find_element(By.NAME, "username").send_keys(u)
        d.find_element(By.NAME, "password").send_keys(p)
        d.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        time.sleep(5)
        if "accounts/login" in d.current_url:
            bot.send_message(cid, "❌ فشل تسجيل الدخول"); return
        d.get("https://www.instagram.com/")
        d.find_element(By.CSS_SELECTOR, "[aria-label='New post']").click()
        time.sleep(2)
        d.find_element(By.CSS_SELECTOR, "input[type='file']").send_keys(os.path.abspath(img))
        time.sleep(3)
        d.find_element(By.XPATH, "//button[text()='Next']").click()
        if cap:
            d.find_element(By.CSS_SELECTOR, "textarea[aria-label='Write a caption...']").send_keys(cap)
        time.sleep(2)
        d.find_element(By.XPATH, "//button[text()='Share']").click()
        time.sleep(5)
        bot.send_message(cid, "✅ تم النشر بنجاح")
    except Exception as e:
        bot.send_message(cid, f"❌ خطأ في النشر: {e}")
    finally:
        d.quit()
        if os.path.exists(img):
            os.remove(img)

@bot.callback_query_handler(func=lambda call: call.data == "back")
def back(call):
    main_menu(call.message.chat.id)

if __name__ == '__main__':
    init_db()
    bot.polling(none_stop=True)
 
