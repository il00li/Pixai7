# bot.py
# 
# هذا الملف جاهز للعمل مباشرة. 
# عند أول تشغيل سيطلب منك:
#   • API_ID
#   • API_HASH
#   • BOT_TOKEN
# ثم يحفظها تلقائيًا في ملف config.json ولا يحتاج أي تعديل بعد ذلك.
#
# قبل التشغيل: تأكد من تثبيت الحزم التالية عبر:
# pip install telethon apscheduler

import os
import json
from datetime import datetime, timedelta

from telethon import TelegramClient, events, Button
from telethon.errors import ChatWriteForbiddenError
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --------------------------------------------------
# 1. تحميل أو إنشاء ملف الإعدادات config.json
CFG_FILE = "config.json"

def load_or_create_config():
    if os.path.exists(CFG_FILE):
        return json.load(open(CFG_FILE, "r", encoding="utf-8"))
    # عند أول تشغيل، نطلب من المطور بيانات البوت:
    cfg = {}
    cfg["api_id"]    = int(input("23656977: ").strip())
    cfg["api_hash"]  = input("49d3f43531a92b3f5bc403766313ca1e: ").strip()
    cfg["bot_token"] = input("7966976239:AAF0ypJKeGiKVBS9yowQxlUDh9kpzjsNG_Q: ").strip()
    with open(CFG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return cfg

cfg = load_or_create_config()
API_ID    = cfg["23656977"]
API_HASH  = cfg["49d3f43531a92b3f5bc403766313ca1e"]
BOT_TOKEN = cfg["7966976239:AAF0ypJKeGiKVBS9yowQxlUDh9kpzjsNG_Q"]

# --------------------------------------------------
# 2. دوال التخزين في users.json
DATA_FILE = "users.json"

def load_data():
    try:
        return json.load(open(DATA_FILE, "r", encoding="utf-8"))
    except FileNotFoundError:
        return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user(uid):
    return load_data().get(str(uid), {})

def set_user(uid, info):
    data = load_data()
    data[str(uid)] = info
    save_data(data)

def remove_user(uid):
    data = load_data()
    data.pop(str(uid), None)
    save_data(data)

# --------------------------------------------------
# 3. تهيئة عميل تلغرام وجدول المهام
client    = TelegramClient("bot_session", API_ID, API_HASH).start(bot_token=BOT_TOKEN)
scheduler = AsyncIOScheduler()
scheduler.start()

# --------------------------------------------------
# 4. قائمة الأزرار الرئيسية
def main_menu():
    return [
        [Button.inline("إضافة مجموعات", b"add_groups"),
         Button.inline("حذف مجموعة", b"remove_group")],
        [Button.inline("تغيير الرسالة", b"set_message"),
         Button.inline("تعيين الفاصل", b"set_interval")],
        [Button.inline("تفعيل النشر", b"enable"),
         Button.inline("إيقاف النشر", b"disable")],
        [Button.inline("إضافة حساب", b"add_account"),
         Button.inline("حذف حساب", b"delete_account")],
    ]

# --------------------------------------------------
# 5. فحص صلاحية الاشتراك
def check_subscription(uid, event):
    user = get_user(uid)
    end = user.get("subscription_end")
    if end:
        now = datetime.utcnow()
        sub_end = datetime.fromisoformat(end)
        if now >= sub_end:
            remove_user(uid)
            event.reply(
                "⛔ انتهت صلاحية اشتراكك وتم حذف جلستك.\n"
                "للتجديد اضغط الزر أدناه:",
                buttons=[[Button.inline("تجديد الاشتراك", b"renew")]]
            )
            return False
    return True

# --------------------------------------------------
# 6. جدولة مهمة نشر تلقائي
def schedule_job(uid, group, message, interval):
    job_id = f"{uid}:{group}"
    def job():
        try:
            client.send_message(group, message)
        except ChatWriteForbiddenError:
            # إذا فشل النشر، نحذف المجموعة من المستخدم
            user = get_user(uid)
            if group in user.get("groups", []):
                user["groups"].remove(group)
                set_user(uid, user)
            client.send_message(uid,
                f"❌ فشل النشر في {group} وتمت إزالته تلقائيًا."
            )
    scheduler.add_job(job, "interval",
                      minutes=interval,
                      id=job_id,
                      replace_existing=True)

def remove_all_jobs(uid):
    for job in scheduler.get_jobs():
        if job.id.startswith(f"{uid}:"):
            scheduler.remove_job(job.id)

# --------------------------------------------------
# 7. معالج أمر /start
@client.on(events.NewMessage(pattern="/start"))
async def on_start(event):
    uid = event.sender_id
    # ابدأ تسجيل جديد أو عرض القائمة
    if not check_subscription(uid, event):
        return

    user = get_user(uid)
    if user.get("phone"):
        # مستخدم مسجل سابقًا
        await event.reply("أهلاً من جديد! اختر من القائمة:", buttons=main_menu())
    else:
        # تسجيل جديد: نطلب رقم الهاتف
        user = {
            "state": "await_phone",
            "groups": [],
            "message": "",
            "interval": 5,
            # اشتراك 30 يوم افتراضي
            "subscription_end": (datetime.utcnow() + timedelta(days=30)).isoformat()
        }
        set_user(uid, user)
        await event.reply("مرحباً! الرجاء إدخال رقم هاتفك (مثال: +9677XXXXXXX):")

# --------------------------------------------------
# 8. معالج الرسائل النصية للحالات المختلفة
@client.on(events.NewMessage())
async def on_message(event):
    uid  = event.sender_id
    text = event.raw_text.strip()
    if not check_subscription(uid, event):
        return

    user  = get_user(uid)
    state = user.get("state")

    # استقبال رقم الهاتف
    if state == "await_phone":
        user["phone"] = text
        user["state"] = None
        set_user(uid, user)
        await event.reply("✅ تم حفظ رقم الهاتف!\nاختر من القائمة:", buttons=main_menu())
        return

    # استقبال روابط المجموعات
    if state == "await_new_groups":
        user.setdefault("groups", []).append(text)
        set_user(uid, user)
        await event.reply(f"✅ تمت إضافة المجموعة:\n{text}\n\nللمزيد أرسل رابطًا آخر أو اضغط رجوع.", buttons=[
            [Button.inline("رجوع", b"back_to_menu")]
        ])
        return

    # استقبال نص الرسالة
    if state == "await_message":
        user["message"] = text
        user["state"]   = None
        set_user(uid, user)
        await event.reply("✅ تم حفظ نص الرسالة.\nاختر من القائمة:", buttons=main_menu())
        return

    # استقبال الفاصل الزمني
    if state == "await_interval":
        try:
            mins = int(text)
            user["interval"] = mins
            user["state"]    = None
            set_user(uid, user)
            await event.reply(f"✅ تم تعيين الفاصل إلى {mins} دقيقة.\nاختر من القائمة:", buttons=main_menu())
        except ValueError:
            await event.reply("⚠️ الرجاء إدخال عدد صحيح للفاصل بالدقائق:")
        return

# --------------------------------------------------
# 9. معالج الضغط على الأزرار
@client.on(events.CallbackQuery)
async def on_button(event):
    uid  = event.sender_id
    data = event.data.decode()
    if not check_subscription(uid, event):
        return

    user = get_user(uid)

    # العودة إلى القائمة
    if data == "back_to_menu":
        await event.edit("القائمة الرئيسية:", buttons=main_menu())
        return

    # إضافة مجموعات
    if data == "add_groups":
        user["state"] = "await_new_groups"
        set_user(uid, user)
        await event.edit("أرسل روابط الدعوة للمجموعات (واحد لكل رسالة):")
        return

    # حذف مجموعة
    if data == "remove_group":
        markup = [[Button.inline(name, f"del:{i}")] 
                  for i, name in enumerate(user.get("groups", []))]
        if not markup:
            await event.edit("قائمة المجموعات فارغة.", buttons=main_menu())
        else:
            await event.edit("اختر المجموعة للحذف:", buttons=markup + [[Button.inline("رجوع", b"back_to_menu")]])
        return

    # تنفيذ حذف مجموعة حسب الفهرس
    if data.startswith("del:"):
        idx = int(data.split(":",1)[1])
        groups = user.get("groups", [])
        if 0 <= idx < len(groups):
            removed = groups.pop(idx)
            user["groups"] = groups
            set_user(uid, user)
            await event.edit(f"✅ حُذفت المجموعة:\n{removed}", buttons=main_menu())
        else:
            await event.answer("⚠️ فهرس غير صحيح.", alert=True)
        return

    # تغيير نص الرسالة
    if data == "set_message":
        user["state"] = "await_message"
        set_user(uid, user)
        await event.edit("أرسل نص الرسالة الذي تريد نشره دورياً:")
        return

    # تعيين الفاصل الزمني
    if data == "set_interval":
        user["state"] = "await_interval"
        set_user(uid, user)
        await event.edit("أرسل الفاصل الزمني بالدقائق (عدد صحيح):")
        return

    # تفعيل النشر التلقائي
    if data == "enable":
        if not user.get("groups"):
            await event.answer("⚠️ لم تضف أي مجموعة بعد.", alert=True)
            return
        remove_all_jobs(uid)
        for g in user["groups"]:
            schedule_job(uid, g, user["message"], user["interval"])
        # رسالة تأكيد
        text = (
            "✅ تم تفعيل النشر التلقائي!\n\n"
            f"• المجموعات: {len(user['groups'])}\n"
            f"• الفاصل: {user['interval']} دقيقة\n"
            f"• نص الرسالة: {user['message']!r}"
        )
        await event.edit(text, buttons=main_menu())
        return

    # إيقاف النشر
    if data == "disable":
        remove_all_jobs(uid)
        await event.edit("⏸️ تم إيقاف النشر التلقائي.", buttons=main_menu())
        return

    # إضافة حساب جديد (إعادة تسجيل)
    if data == "add_account":
        remove_all_jobs(uid)
        remove_user(uid)
        await event.edit("🔄 لنبدأ تسجيل حساب جديد. أرسل رقم هاتفك:", buttons=[])
        # نعيد تسجيل مستخدم جديد
        set_user(uid, {"state":"await_phone","groups":[], "message":"", "interval":5})
        return

    # حذف الحساب والجلسة
    if data == "delete_account":
        remove_all_jobs(uid)
        remove_user(uid)
        await event.edit("🗑️ تم حذف حسابك وجلسة البوت.")
        return

    # تجديد الاشتراك
    if data == "renew":
        end = (datetime.utcnow() + timedelta(days=30)).isoformat()
        user.update({"subscription_end": end})
        set_user(uid, user)
        await event.edit("✅ تم تجديد اشتراكك 30 يوماً إضافية!", buttons=main_menu())
        return

    # أي زر غير معروف
    await event.answer()

# --------------------------------------------------
# 10. تشغيل البوت
print("🚀 Bot is starting...")
client.run_until_disconnected() 

