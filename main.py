from telethon import TelegramClient, events, Button
import asyncio
import os

# رمز البوت وAPI
bot_token = os.environ.get('BOT_TOKEN', '7966976239:AAEy5WkQDszmVbuInTnuOyUXskhyO7ak9Nc')
api_id = int(os.environ.get('API_ID', '23656977'))
api_hash = os.environ.get('API_HASH', '49d3f43531a92b3f5bc403766313ca1e')

# تهيئة البوت
bot = TelegramClient('bot', api_id, api_hash).start(bot_token=bot_token)

# تهيئة قاموس العملاء والمجموعات
user_clients = {}
user_supergroups = {}
total_posts = 0
user_posts = {}

@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    # إنشاء أزرار القائمة الرئيسية
    buttons = [
        [Button.inline("═ LOGIN | تسجيل ═", data="login")],
        [Button.inline("بدء النشر", data="start_posting"), Button.inline("اضف سوبر", data="add_supergroups")],
        [Button.inline("مساعدة", data="help"), Button.inline("احصائيات", data="statistics")]
    ]

    # إرسال القائمة الرئيسية
    await event.respond("مرحبا! انا بوت النشر التلقائي. اختر الخيار المطلوب:", buttons=buttons)

@bot.on(events.CallbackQuery(data=b'login'))
async def login(event):
    # طلب رقم هاتف المستخدم
    await event.edit("يرجى ارسال رقم هاتفك مع رمز البلد (مثل +1234567890):", buttons=[Button.inline("رجوع", data="back")])

    # تخزين رقم هاتف المستخدم
    async with bot.conversation(event.sender_id) as conv:
        phone_number_response = await conv.get_response()
        phone_number = phone_number_response.text

        # ارسال طلب رمز التحقق
        await conv.send("يرجى ارسال رمز التحقق الذي تم ارساله لك:")

        # تخزين رمز التحقق
        verification_code_response = await conv.get_response()
        verification_code = verification_code_response.text

        # تسجيل الدخول إلى حساب المستخدم
        user_client = TelegramClient(f'user_{event.sender_id}', api_id, api_hash)
        await user_client.start(phone_number, verification_code)

        # تخزين عميل المستخدم
        user_clients[event.sender_id] = user_client

        await conv.send("تم تسجيل الدخول بنجاح!")

@bot.on(events.CallbackQuery(data=b'add_supergroups'))
async def add_supergroups(event):
    # طلب معرفات المجموعات من المستخدم
    await event.edit("يرجى ارسال اسم المستخدم أو معرف المجموعة التي تريد اضافتها (مثال: @groupusername أو -1001234567890):", buttons=[Button.inline("رجوع", data="back")])

    # تخزين معرفات المجموعات
    async with bot.conversation(event.sender_id) as conv:
        supergroup_ids = await conv.get_response()

        # تخزين معرفات المجموعات
        user_supergroups[event.sender_id] = supergroup_ids.text.split()

        await conv.send("تمت اضافة المجموعات بنجاح!")

@bot.on(events.CallbackQuery(data=b'start_posting'))
async def start_posting(event):
    # إنشاء أزرار الفاصل الزمني
    buttons = [
        [Button.inline("2 دقائق", data="2m"), Button.inline("5 دقائق", data="5m")],
        [Button.inline("10 دقائق", data="10m"), Button.inline("20 دقائق", data="20m")],
        [Button.inline("30 دقيقة", data="30m"), Button.inline("60 دقيقة", data="60m")],
        [Button.inline("120 دقيقة", data="120m"), Button.inline("رجوع", data="back")]
    ]

    # إرسال قائمة الفاصل الزمني
    await event.edit("اختر الفاصل الزمني بين كل نشر:", buttons=buttons)

@bot.on(events.CallbackQuery(data=b'help'))
async def help(event):
    # عرض معلومات المساعدة
    help_text = """
    **استخدام البوت:**
    1. اضغط على زر "═ LOGIN | تسجيل ═" لاضافة رقم هاتفك.
    2. اضغط على زر "اضف سوبر" لاضافة المجموعات التي تريد النشر فيها.
    3. اضغط على زر "بدء النشر" لاختيار الفاصل الزمني بين كل نشر.
    4. اضغط على زر "احصائيات" لعرض الاحصائيات.

    **تحذيرات:**
    - لا تستخدم البوت لارسال رسائل غير مرغوب فيها.
    - لا تستخدم البوت لارسال رسائل مزعجة أو غير قانونية.
    - المطور @Ili8_8ill غير مسؤول عن أي استخدام غير قانوني للبوت.
    """

    await event.edit(help_text, buttons=[Button.inline("رجوع", data="back")])

@bot.on(events.CallbackQuery(data=b'statistics'))
async def statistics(event):
    # عرض الاحصائيات
    stats_text = f"""
    **احصائيات البوت:**
    - عدد مرات النشر الاجمالية: {total_posts}
    - عدد مرات النشر الخاصة بك: {user_posts.get(event.sender_id, 0)}
    - عدد المستخدمين للبوت: {len(user_clients)}
    - عدد المجموعات المضافة للبوت: {len(user_supergroups)}
    """

    await event.edit(stats_text, buttons=[Button.inline("رجوع", data="back")])

@bot.on(events.CallbackQuery(data=b'2m'))
async def two_minutes(event):
    # بدء النشر كل 2 دقائق
    await start_posting_interval(event, 2)

@bot.on(events.CallbackQuery(data=b'5m'))
async def five_minutes(event):
    # بدء النشر كل 5 دقائق
    await start_posting_interval(event, 5)

@bot.on(events.CallbackQuery(data=b'10m'))
async def ten_minutes(event):
    # بدء النشر كل 10 دقائق
    await start_posting_interval(event, 10)

@bot.on(events.CallbackQuery(data=b'20m'))
async def twenty_minutes(event):
    # بدء النشر كل 20 دقيقة
    await start_posting_interval(event, 20)

@bot.on(events.CallbackQuery(data=b'30m'))
async def thirty_minutes(event):
    # بدء النشر كل 30 دقيقة
    await start_posting_interval(event, 30)

@bot.on(events.CallbackQuery(data=b'60m'))
async def sixty_minutes(event):
    # بدء النشر كل 60 دقيقة
    await start_posting_interval(event, 60)

@bot.on(events.CallbackQuery(data=b'120m'))
async def one_hundred_twenty_minutes(event):
    # بدء النشر كل 120 دقيقة
    await start_posting_interval(event, 120)

async def start_posting_interval(event, interval):
    # الحصول على عميل المستخدم ومعرفات المجموعات
    user_client = user_clients.get(event.sender_id)
    supergroup_ids = user_supergroups.get(event.sender_id, [])

    if not user_client or not supergroup_ids:
        await event.edit("يرجى تسجيل الدخول واضافة المجموعات اولا.")
        return

    # بدء النشر
    await event.edit(f"تم بدء النشر كل {interval} دقائق.")

    # جدولة مهمة النشر
    async def post_task():
        while True:
            for supergroup_id in supergroup_ids:
                await user_client.send_message(supergroup_id, "نص النشر التلقائي")
                total_posts += 1
                user_posts[event.sender_id] = user_posts.get(event.sender_id, 0) + 1
            await asyncio.sleep(interval * 60)

    asyncio.create_task(post_task())

if __name__ == '__main__':
    # تشغيل البوت
    bot.run_until_disconnected() 
