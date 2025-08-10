from telethon import TelegramClient, events, Button
from telethon.tl.functions.channels import GetParticipantsRequest
from telethon.tl.types import Channel
from telethon.sessions import StringSession
import asyncio
import logging
import re

# إعداد التسجيل
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# بيانات البوت
API_ID = 23656977
API_HASH = "49d3f43531a92b3f5bc403766313ca1e"
BOT_TOKEN = "8247037355:AAH2rRm9PJCXqcVISS8g-EL1lv3tvQTXFys"

# بيانات المستخدمين
users_data = {}

class BotUser:
    def __init__(self):
        self.phone = None
        self.client = None
        self.groups = []
        self.content = ""
        self.interval = 10
        self.active = False

# بدء البوت
bot = TelegramClient('bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# /start
@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    user_id = event.sender_id
    if user_id not in users_data:
        users_data[user_id] = BotUser()

    keyboard = [
        [Button.inline("تسجيل دخول", b"login")],
        [Button.inline("إضافة مجموعة", b"add")],
        [Button.inline("بدء النشر", b"start_publish")],
        [Button.inline("إيقاف النشر", b"stop_publish")],
        [Button.inline("إحصائيات", b"stats")]
    ]
    await event.respond("👋 مرحباً! اختر أحد الخيارات:", buttons=keyboard)

# تسجيل الدخول
@bot.on(events.CallbackQuery(pattern=b"login"))
async def login(event):
    await event.edit("📱 أرسل رقمك مع +:")
    users_data[event.sender_id].phone = "waiting"

@bot.on(events.NewMessage(func=lambda e: users_data.get(e.sender_id) and users_data[e.sender_id].phone == "waiting"))
async def receive_phone(event):
    phone = event.text
    if not re.match(r"^\+\d{10,15}$", phone):
        await event.reply("❌ صيغة الرقم غير صحيحة.")
        return

    user = users_data[event.sender_id]
    user.phone = phone
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()
    await client.send_code_request(phone)
    user.client = client
    user.phone = "code"
    await event.reply("📬 أرسل الكود الذي وصلك:")

@bot.on(events.NewMessage(func=lambda e: users_data.get(e.sender_id) and users_data[e.sender_id].phone == "code"))
async def receive_code(event):
    code = event.text.strip()
    user = users_data[event.sender_id]
    try:
        await user.client.sign_in(user.phone, code)
        user.auth = True
        await event.reply("✅ تم تسجيل الدخول بنجاح!")
    except Exception as e:
        await event.reply("❌ خطأ في الكود أو كلمة المرور.")

# إضافة مجموعة
@bot.on(events.CallbackQuery(pattern=b"add"))
async def add_group(event):
    await event.edit("🔗 أرسل معرف المجموعة أو رابطها:")
    users_data[event.sender_id].phone = "add_group"

@bot.on(events.NewMessage(func=lambda e: users_data.get(e.sender_id) and users_data[e.sender_id].phone == "add_group"))
async def receive_group(event):
    link = event.text
    user = users_data[event.sender_id]
    try:
        group = await user.client.get_entity(link)
        if group.id not in user.groups:
            user.groups.append(group.id)
            await event.reply(f"✅ تمت إضافة المجموعة: {group.title}")
        else:
            await event.reply("⚠️ المجموعة مضافة بالفعل.")
        user.phone = None
    except Exception as e:
        await event.reply("❌ لم يتم العثور على المجموعة.")

# بدء النشر
@bot.on(events.CallbackQuery(pattern=b"start_publish"))
async def start_publish(event):
    user = users_data[event.sender_id]
    if not user.client or not user.groups:
        await event.edit("❌ يجب تسجيل الدخول وإضافة مجموعات أولاً.")
        return

    await event.edit("📝 أرسل النص الذي تريد نشره:")
    user.phone = "get_content"

@bot.on(events.NewMessage(func=lambda e: users_data.get(e.sender_id) and users_data[e.sender_id].phone == "get_content"))
async def receive_content(event):
    user = users_data[event.sender_id]
    user.content = event.text
    user.phone = "get_interval"
    await event.reply("⏱️ أرسل الفترة بالدقائق (2-120):")

@bot.on(events.NewMessage(func=lambda e: users_data.get(e.sender_id) and users_data[e.sender_id].phone == "get_interval"))
async def receive_interval(event):
    try:
        interval = int(event.text)
        if not (2 <= interval <= 120):
            raise ValueError
        user = users_data[event.sender_id]
        user.interval = interval
        user.active = True
        asyncio.create_task(publish_loop(event.sender_id))
        await event.reply(f"✅ بدأ النشر كل {interval} دقيقة.")
    except ValueError:
        await event.reply("❌ يجب أن يكون الرقم بين 2 و 120.")

# حلقة النشر
async def publish_loop(user_id):
    user = users_data[user_id]
    while user.active:
        for gid in user.groups:
            try:
                await user.client.send_message(gid, user.content)
                await asyncio.sleep(10)
            except Exception as e:
                logging.error(f"فشل النشر: {e}")
        await asyncio.sleep(user.interval * 60)

# إيقاف النشر
@bot.on(events.CallbackQuery(pattern=b"stop_publish"))
async def stop_publish(event):
    user = users_data[event.sender_id]
    user.active = False
    await event.edit("🛑 تم إيقاف النشر.")

# إحصائيات
@bot.on(events.CallbackQuery(pattern=b"stats"))
async def stats(event):
    user = users_data[event.sender_id]
    await event.edit(
        f"📊 **إحصائياتك**:\n"
        f"• عدد المجموعات: {len(user.groups)}\n"
        f"• النشر نشط: {'نعم' if user.active else 'لا'}"
    )

# تشغيل البوت
async def main():
    await bot.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
