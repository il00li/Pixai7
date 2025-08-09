import asyncio
import re
import os
import time
import sqlite3
from datetime import datetime
from telethon import TelegramClient, events, Button
from telethon.errors import (
    SessionPasswordNeededError, 
    PhoneCodeInvalidError, 
    PhoneCodeExpiredError,
    PhoneNumberInvalidError,
    FloodWaitError
)

# إعدادات البوت
API_ID = 23656977
API_HASH = '49d3f43531a92b3f5bc403766313ca1e'
BOT_TOKEN = '7966976239:AAEy5WkQDszmVbuInTnuOyUXskhyO7ak9Nc'
ADMIN_ID = 7251748706
DEVELOPER = "@Ili8_8ill"

# حالات المحادثة
LOGIN, ADD_SUPER, PUBLISH_INTERVAL = range(3)

# فترات النشر
PUBLISH_INTERVALS = {
    2: "2 دقائق",
    5: "5 دقائق",
    10: "10 دقائق",
    20: "20 دقيقة",
    30: "30 دقيقة",
    60: "60 دقيقة",
    120: "120 دقيقة"
}

# إنشاء قاعدة البيانات
def init_db():
    conn = sqlite3.connect('publishing_bot.db')
    cursor = conn.cursor()
    
    # جدول المستخدمين
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        phone TEXT,
        session_file TEXT,
        created_at TEXT
    )
    ''')
    
    # جدول المجموعات
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS groups (
        group_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        group_link TEXT,
        group_name TEXT,
        added_at TEXT
    )
    ''')
    
    # جدول النشر
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS publishing (
        publish_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        group_id INTEGER,
        interval INTEGER,
        last_published TEXT,
        is_active INTEGER DEFAULT 1
    )
    ''')
    
    # جدول الإحصائيات
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS statistics (
        stat_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        publish_count INTEGER DEFAULT 0,
        last_activity TEXT
    )
    ''')
    
    conn.commit()
    conn.close()

# إنشاء عميل البوت
bot = TelegramClient('publishing_bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# القائمة الرئيسية
async def main_menu(event, message=None):
    buttons = [
        [Button.inline("═════ LOGIN | تسجيل ═════", data="login")],
        [
            Button.inline("بدء النشر", data="start_publishing"),
            Button.inline("اضف سوبر", data="add_super")
        ],
        [
            Button.inline("مساعدة", data="help"),
            Button.inline("احصائيات", data="stats")
        ]
    ]
    
    text = "⚡️ **مرحباً بك في بوت النشر التلقائي** ⚡️\n\n" \
           "اختر أحد الخيارات من القائمة:"
    
    if message:
        await event.edit(text, buttons=buttons)
    else:
        await event.respond(text, buttons=buttons)

# بدء المحادثة
@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    await main_menu(event)

# معالجة الضغط على الأزرار
@bot.on(events.CallbackQuery)
async def handle_buttons(event):
    user_id = event.sender_id
    data = event.data.decode('utf-8')
    
    if data == "login":
        await handle_login(event)
    elif data == "add_super":
        await handle_add_super(event)
    elif data == "start_publishing":
        await start_publishing_menu(event)
    elif data == "help":
        await show_help(event)
    elif data == "stats":
        await show_stats(event)
    elif data == "back":
        await main_menu(event, message=True)
    elif data.startswith("interval_"):
        interval = int(data.split("_")[1])
        await start_publishing(event, interval)
    elif data == "cancel":
        await event.edit("❌ تم الإلغاء")
        await main_menu(event, message=True)

# تسجيل الدخول
async def handle_login(event):
    await event.edit(
        "📱 **تسجيل الدخول**\n\n"
        "الرجاء إرسال رقم هاتفك مع رمز الدولة:\n"
        "مثال: +201234567890",
        buttons=[[Button.inline("رجوع", data="back")]]
    )
    # تحديث حالة المستخدم
    set_user_state(event.sender_id, LOGIN)

# معالجة إضافة المجموعات
async def handle_add_super(event):
    await event.edit(
        "📢 **إضافة مجموعات للنشر**\n\n"
        "الرجاء إرسال روابط المجموعات (سوبر جروب) التي تريد النشر فيها:\n"
        "مثال: https://t.me/group_name\n\n"
        "يمكنك إرسال أكثر من رابط في نفس الرسالة",
        buttons=[[Button.inline("رجوع", data="back")]]
    )
    # تحديث حالة المستخدم
    set_user_state(event.sender_id, ADD_SUPER)

# قائمة فترات النشر
async def start_publishing_menu(event):
    buttons = [
        [Button.inline(text, data=f"interval_{interval}")]
        for interval, text in PUBLISH_INTERVALS.items()
    ]
    buttons.append([Button.inline("رجوع", data="back")])
    
    await event.edit(
        "⏱ **اختر الفترة الزمنية للنشر**\n\n"
        "سيتم النشر في جميع المجموعات المضافة كل الفترة المحددة:",
        buttons=buttons
    )

# عرض المساعدة
async def show_help(event):
    help_text = (
        "🆘 **دليل استخدام البوت**\n\n"
        "1. **تسجيل الدخول**: أضف حسابك عبر رقم الهاتف\n"
        "2. **إضافة سوبر**: أضف المجموعات التي تريد النشر فيها\n"
        "3. **بدء النشر**: اختر الفترة الزمنية لبدء النشر التلقائي\n\n"
        "⚠️ **تحذيرات مهمة**:\n"
        "- لا تستخدم البوت في إرسال سبام\n"
        "- تأكد من أن لديك إذن النشر في المجموعات\n"
        "- البوت ليس مسؤولاً عن حظر حسابك\n\n"
        f"المطور: {DEVELOPER}"
    )
    
    await event.edit(
        help_text,
        buttons=[[Button.inline("رجوع", data="back")]]
    )

# عرض الإحصائيات
async def show_stats(event):
    user_id = event.sender_id
    conn = sqlite3.connect('publishing_bot.db')
    cursor = conn.cursor()
    
    # إحصائيات المستخدم
    cursor.execute("SELECT COUNT(*) FROM publishing WHERE user_id = ?", (user_id,))
    user_publish_count = cursor.fetchone()[0]
    
    # الإحصائيات العامة
    cursor.execute("SELECT COUNT(DISTINCT user_id) FROM users")
    total_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM groups")
    total_groups = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(publish_count) FROM statistics")
    total_publishes = cursor.fetchone()[0] or 0
    
    stats_text = (
        "📊 **إحصائيات البوت**\n\n"
        f"• عدد مرات النشر الخاصة بك: `{user_publish_count}`\n"
        f"• إجمالي مرات النشر: `{total_publishes}`\n"
        f"• عدد المستخدمين: `{total_users}`\n"
        f"• عدد المجموعات المضافة: `{total_groups}`"
    )
    
    conn.close()
    
    await event.edit(
        stats_text,
        buttons=[[Button.inline("رجوع", data="back")]]
    )

# بدء النشر
async def start_publishing(event, interval):
    user_id = event.sender_id
    
    # التحقق من وجود جلسة مستخدم
    conn = sqlite3.connect('publishing_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT session_file FROM users WHERE user_id = ?", (user_id,))
    session_data = cursor.fetchone()
    
    if not session_data:
        await event.edit(
            "❌ يجب تسجيل الدخول أولاً",
            buttons=[[Button.inline("تسجيل الدخول", data="login")]]
        )
        return
    
    # التحقق من وجود مجموعات
    cursor.execute("SELECT COUNT(*) FROM groups WHERE user_id = ?", (user_id,))
    group_count = cursor.fetchone()[0]
    
    if group_count == 0:
        await event.edit(
            "❌ يجب إضافة مجموعات أولاً",
            buttons=[[Button.inline("إضافة مجموعات", data="add_super")]]
        )
        return
    
    # بدء عملية النشر
    await event.edit(
        f"⏳ جاري بدء النشر كل `{PUBLISH_INTERVALS[interval]}`...\n\n"
        "سيتم إرسال رسالة تأكيد بعد كل نشر ناجح",
        buttons=[[Button.inline("إلغاء النشر", data="cancel")]]
    )
    
    # حفظ إعدادات النشر
    cursor.execute("INSERT INTO publishing (user_id, interval) VALUES (?, ?)", 
                  (user_id, interval))
    conn.commit()
    conn.close()
    
    # بدء النشر التلقائي
    asyncio.create_task(auto_publish(user_id, interval))

# النشر التلقائي
async def auto_publish(user_id, interval):
    while True:
        try:
            # جلب بيانات المستخدم
            conn = sqlite3.connect('publishing_bot.db')
            cursor = conn.cursor()
            cursor.execute("SELECT session_file FROM users WHERE user_id = ?", (user_id,))
            session_file = cursor.fetchone()[0]
            
            # جلب المجموعات
            cursor.execute("SELECT group_link FROM groups WHERE user_id = ?", (user_id,))
            groups = cursor.fetchall()
            
            # الاتصال بحساب المستخدم
            async with TelegramClient(session_file, API_ID, API_HASH) as client:
                for group in groups:
                    try:
                        entity = await client.get_entity(group[0])
                        await client.send_message(
                            entity, 
                            "📢 هذا منشور تلقائي من البوت\n"
                            "نتمنى لكم يوماً سعيداً! 🌟"
                        )
                        
                        # تحديث الإحصائيات
                        cursor.execute("""
                            INSERT OR IGNORE INTO statistics (user_id) 
                            VALUES (?)
                        """, (user_id,))
                        
                        cursor.execute("""
                            UPDATE statistics 
                            SET publish_count = publish_count + 1,
                                last_activity = ?
                            WHERE user_id = ?
                        """, (datetime.now().isoformat(), user_id))
                        
                        conn.commit()
                        
                        # إرسال تأكيد للمستخدم
                        await bot.send_message(
                            user_id,
                            f"✅ تم النشر في {entity.title} بنجاح!"
                        )
                    except Exception as e:
                        await bot.send_message(
                            user_id,
                            f"❌ فشل النشر في {group[0]}: {str(e)}"
                        )
            
            # الانتظار للفترة المحددة
            await asyncio.sleep(interval * 60)
            
        except Exception as e:
            await bot.send_message(
                user_id,
                f"❌ خطأ في النشر التلقائي: {str(e)}\n"
                "جاري إعادة المحاولة بعد 5 دقائق..."
            )
            await asyncio.sleep(300)

# معالجة رسائل المستخدم
@bot.on(events.NewMessage)
async def handle_messages(event):
    user_id = event.sender_id
    state = get_user_state(user_id)
    
    if state == LOGIN:
        await process_login(event)
    elif state == ADD_SUPER:
        await process_add_groups(event)

# معالجة تسجيل الدخول
async def process_login(event):
    user_id = event.sender_id
    phone = event.raw_text.strip()
    
    # التحقق من صحة الرقم
    if not re.match(r"^\+\d{10,15}$", phone):
        await event.respond(
            "❌ رقم غير صحيح! الرجاء إرسال رقم صحيح مثل:\n"
            "+201234567890",
            buttons=[[Button.inline("رجوع", data="back")]]
        )
        return
    
    # إنشاء جلسة جديدة
    session_file = f"sessions/{user_id}.session"
    client = TelegramClient(session_file, API_ID, API_HASH)
    await client.connect()
    
    try:
        # إرسال كود التحقق
        sent_code = await client.send_code_request(phone)
        set_session_data(user_id, {
            'client': client,
            'phone': phone,
            'phone_code_hash': sent_code.phone_code_hash
        })
        
        await event.respond(
            f"🔑 تم إرسال كود التحقق إلى {phone}\n"
            "الرجاء إدخال الكود المكون من 5 أرقام:",
            buttons=[[Button.inline("رجوع", data="back")]]
        )
        # تحديث حالة المستخدم
        set_user_state(user_id, "CODE")
        
    except Exception as e:
        await event.respond(
            f"❌ حدث خطأ: {str(e)}\n"
            "الرجاء المحاولة مرة أخرى",
            buttons=[[Button.inline("رجوع", data="back")]]
        )

# معالجة إضافة المجموعات
async def process_add_groups(event):
    user_id = event.sender_id
    text = event.raw_text
    
    # استخراج الروابط
    links = re.findall(r'https?://t\.me/\w+', text) + re.findall(r'@\w+', text)
    
    if not links:
        await event.respond(
            "❌ لم يتم العثور على روابط صحيحة\n"
            "الرجاء إرسال روابط المجموعات:",
            buttons=[[Button.inline("رجوع", data="back")]]
        )
        return
    
    # حفظ المجموعات
    conn = sqlite3.connect('publishing_bot.db')
    cursor = conn.cursor()
    
    for link in links:
        # تنظيف الرابط
        if link.startswith("@"):
            link = "https://t.me/" + link[1:]
        
        cursor.execute("""
            INSERT INTO groups (user_id, group_link, added_at) 
            VALUES (?, ?, ?)
        """, (user_id, link, datetime.now().isoformat()))
    
    conn.commit()
    conn.close()
    
    await event.respond(
        f"✅ تم إضافة {len(links)} مجموعة بنجاح!",
        buttons=[[Button.inlight("رجوع", data="back")]]
    )
    await main_menu(event)

# وظائف مساعدة لإدارة الحالة والبيانات
def set_user_state(user_id, state):
    # في الإصدار الحقيقي، يجب حفظ الحالة في قاعدة البيانات
    # هنا سنستخدم متغير بسيط للتبسيط
    global user_states
    user_states[user_id] = state

def get_user_state(user_id):
    return user_states.get(user_id, None)

def set_session_data(user_id, data):
    global sessions
    sessions[user_id] = data

def get_session_data(user_id):
    return sessions.get(user_id, None)

# تهيئة البيانات
init_db()
user_states = {}
sessions = {}

# تشغيل البوت
if __name__ == '__main__':
    # إنشاء مجلد الجلسات
    os.makedirs('sessions', exist_ok=True)
    
    print("جارٍ تشغيل بوت النشر التلقائي...")
    bot.run_until_disconnected()
