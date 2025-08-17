# bot.py
# بوت نشر تلقائي لعدة مستخدمين – جاهز للاستضافة على Render (Web أو Background)
# pip install telethon pytz python-dotenv

import os
import json
import asyncio
import logging
from datetime import datetime

from telethon import TelegramClient, events, Button
from telethon.errors import ChatWriteForbiddenError, UserBannedInChannelError

# ---------- إعدادات ----------
API_ID   = int(os.getenv("API_ID", "23656977"))
API_HASH = os.getenv("API_HASH", "49d3f43531a92b3f5bc403766313ca1e")
BOT_TOKEN = os.getenv("BOT_TOKEN", "7966976239:AAFSHHAYUDwvLf1LzI8QCeRICBxATmtIB9Q")

# تستطيع إضافة هذه المتغيرات في Render لتجنّب الإدخال اليدوي
PHONE       = os.getenv("PHONE", None)        # اختياري
SESSION_STR = os.getenv("SESSION_STR", None)  # اختياري (كود التحقق)

# مجلدات البيانات
SESSIONS_DIR = "sessions"
TASKS_DIR    = "tasks"
os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(TASKS_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.FileHandler("bot.log", encoding="utf-8"), logging.StreamHandler()])
log = logging.getLogger(__name__)

# ---------- أدوات ----------
def user_session(uid: int) -> str:
    return os.path.join(SESSIONS_DIR, f"{uid}.session")

def user_task(uid: int) -> str:
    return os.path.join(TASKS_DIR, f"{uid}.json")

class Task:
    def __init__(self, uid: int):
        self.uid = uid
        self.file = user_task(uid)
        self.data = json.load(open(self.file)) if os.path.exists(self.file) else {}
    def save(self):
        json.dump(self.data, open(self.file, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    @property
    def active(self): return self.data.get("active", False)
    @active.setter
    def active(self, v): self.data["active"] = v
    @property
    def phone(self): return self.data.get("phone")
    @phone.setter
    def phone(self, v): self.data["phone"] = v
    @property
    def groups(self): return self.data.setdefault("groups", [])
    @property
    def text(self): return self.data.setdefault("text", "")
    @text.setter
    def text(self, v): self.data["text"] = v
    @property
    def interval(self): return max(self.data.get("interval", 2), 2)
    @interval.setter
    def interval(self, v): self.data["interval"] = max(v, 2)
    @property
    def counter(self): return self.data.setdefault("counter", {})

# ---------- تخزين العملاء ----------
clients: dict[int, TelegramClient] = {}
loops:    dict[int, asyncio.Task]  = {}

async def get_client(uid: int) -> TelegramClient:
    if uid in clients:
        return clients[uid]
    session = user_session(uid)
    client = TelegramClient(session, API_ID, API_HASH)
    # نستخدم phone أو session_str من البيئة
    if SESSION_STR:
        await client.start(session_string=SESSION_STR)
    else:
        await client.start(phone=PHONE or "+201234567890")
    clients[uid] = client
    return client

async def publish_worker(uid: int):
    while True:
        t = Task(uid)
        if t.active and t.phone and t.text and t.groups:
            client = clients.get(uid)
            if not client:
                break
            for gid in t.groups:
                try:
                    ent = await client.get_input_entity(gid)
                    await client.send_message(ent, t.text)
                    t.counter[str(gid)] = t.counter.get(str(gid), 0) + 1
                    t.save()
                    log.info(f"📤 user {uid} -> {gid}")
                except Exception as ex:
                    log.error(f"❌ user {uid} error {gid}: {ex}")
        await asyncio.sleep(t.interval * 60)

def start_loop(uid: int):
    if uid in loops and not loops[uid].done():
        return
    loop = asyncio.get_event_loop()
    loops[uid] = loop.create_task(publish_worker(uid))

def stop_loop(uid: int):
    if uid in loops and not loops[uid].done():
        loops[uid].cancel()
        del loops[uid]

# ---------- البوت ----------
bot = TelegramClient("bot", API_ID, API_HASH)

@bot.on(events.NewMessage(pattern="/start"))
async def start(event):
    uid = event.sender_id
    await event.respond(
        "👋 مرحباً! يمكنك الآن إضافة حسابك وإنشاء مهمة نشر.",
        buttons=[
            [Button.inline("📱 إضافة حسابي", b"add_acc")],
            [Button.inline("📝 إعداد مهمة", b"setup")],
            [Button.inline("⏯️ التحكم بالمهمة", b"control")],
            [Button.inline("📊 السجلات", b"logs")]
        ])

@bot.on(events.CallbackQuery)
async def cb(e):
    uid = e.sender_id
    data = e.data.decode()

    async def refresh_main():
        await e.edit("القائمة الرئيسية:", buttons=[
            [Button.inline("📱 إضافة حسابي", b"add_acc")],
            [Button.inline("📝 إعداد مهمة", b"setup")],
            [Button.inline("⏯️ التحكم بالمهمة", b"control")],
            [Button.inline("📊 السجلات", b"logs")]
        ])

    if data == "add_acc":
        async with bot.conversation(uid) as c:
            await c.send_message("📞 أرسل رقم الهاتف مع رمز الدولة:")
            phone = (await c.get_response()).text.strip()
            await c.send_message("⏳ جارٍ توصيل الحساب...")
            t = Task(uid)
            t.phone = phone
            t.save()
            try:
                client = await get_client(uid)
                await client.send_message("me", "✅ تم توصيل الحساب بنجاح.")
                await c.send_message("✅ تم توصيل الحساب.")
            except Exception as ex:
                await c.send_message(f"❌ فشل: {ex}")
        await refresh_main()

    elif data == "setup":
        t = Task(uid)
        if not t.phone:
            await e.answer("أضف حسابك أولاً.")
            return
        client = await get_client(uid)
        groups = []
        async for d in client.iter_dialogs():
            if d.is_group or d.is_channel:
                groups.append({"id": d.id, "title": d.title})
        if not groups:
            await e.edit("لا توجد مجموعات.")
            return
        btns = [[Button.inline(g["title"], f"g_{g['id']}")] for g in groups] + [[Button.inline("✅ حفظ", b"save_task")]]
        await e.edit("اختر المجموعات:", buttons=btns)

    elif data.startswith("g_"):
        gid = int(data[2:])
        t = Task(uid)
        if gid in t.groups:
            t.groups.remove(gid)
        else:
            t.groups.append(gid)
        t.save()
        await cb(type(e)(data=b"setup"))

    elif data == "save_task":
        async with bot.conversation(uid) as c:
            await c.send_message("📄 أرسل النص:")
            t = Task(uid)
            t.text = (await c.get_response()).text
            await c.send_message("⏱️ الفاصل (دقائق ≥ 2):")
            t.interval = max(int((await c.get_response()).text), 2)
            t.save()
            await c.send_message("✅ تم حفظ المهمة.")
        await refresh_main()

    elif data == "control":
        t = Task(uid)
        status = "🟢 نشطة" if t.active else "🔴 متوقفة"
        txt = (f"الحالة: {status}\n"
               f"المجموعات: {len(t.groups)}\n"
               f"النص: {t.text[:30]}...\n"
               f"الفاصل: {t.interval} د.")
        btns = []
        if t.groups and t.text:
            btns.append([Button.inline("⏸️ إيقاف" if t.active else "▶️ تشغيل", b"toggle_task")])
        btns.append([Button.inline("🔄 إعادة", b"restart")])
        btns.append([Button.inline("🔙", b"main")])
        await e.edit(txt, buttons=btns)

    elif data == "toggle_task":
        t = Task(uid)
        t.active = not t.active
        t.save()
        if t.active:
            start_loop(uid)
        else:
            stop_loop(uid)
        await cb(type(e)(data=b"control"))

    elif data == "restart":
        t = Task(uid)
        t.counter.clear()
        t.active = True
        t.save()
        start_loop(uid)
        await e.answer("تم الإعادة.")
        await cb(type(e)(data=b"control"))

    elif data == "logs":
        if os.path.exists("bot.log"):
            with open("bot.log", encoding="utf-8") as f:
                last = "".join(f.readlines()[-30:])
            await e.edit(f"<pre>{last}</pre>", parse_mode="html", buttons=[[Button.inline("🔙", b"main")]])
        else:
            await e.answer("لا توجد سجلات.")

    elif data == "main":
        await refresh_main()

# ---------- تشغيل ----------
async def main():
    await bot.start(bot_token=BOT_TOKEN)
    log.info("Bot started")
    await bot.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
