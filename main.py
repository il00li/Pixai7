import os, json, asyncio, logging, pytz
from datetime import datetime

from telethon import TelegramClient, events, Button
from telethon.errors import ChatWriteForbiddenError, UserBannedInChannelError

# ---------- إعدادات ----------
API_ID   = 23656977
API_HASH = "49d3f43531a92b3f5bc403766313ca1e"
BOT_TOKEN = "7966976239:AAFEtPbUEIqMVaLN20HH49zIMVSh4jKZJA4"

SESSION_FILE = "user.session"
TASK_FILE    = "task.json"
LOG_FILE     = "bot.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"),
              logging.StreamHandler()])
log = logging.getLogger(__name__)

# ---------- client حساب المستخدم ----------
user = TelegramClient(SESSION_FILE, API_ID, API_HASH)

# ---------- مهمة النشر ----------
class Task:
    def __init__(self):
        self.data = json.load(open(TASK_FILE)) if os.path.exists(TASK_FILE) else {}
    def save(self):
        json.dump(self.data, open(TASK_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    @property
    def active(self): return self.data.get("active", False)
    @active.setter
    def active(self, v): self.data["active"] = v
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

task = Task()

# ---------- حلقة النشر ----------
async def publish_worker():
    await user.connect()   # يضمن أن الاتصال موجود
    while True:
        if task.active and task.text and task.groups:
            for gid in task.groups:
                try:
                    ent = await user.get_input_entity(gid)
                    await user.send_message(ent, task.text)
                    task.counter[str(gid)] = task.counter.get(str(gid), 0) + 1
                    log.info(f"📤 نشر إلى {gid}")
                except Exception as ex:
                    log.error(f"خطأ في {gid}: {ex}")
            task.save()
        await asyncio.sleep(task.interval * 60)

# ---------- البوت ----------
bot = TelegramClient("bot", API_ID, API_HASH)

@bot.on(events.NewMessage(pattern="/start"))
async def start(event):
    await event.respond(
        "👋 أهلاً بك في بوت النشر التلقائي (حساب واحد فقط).",
        buttons=[
            [Button.inline("📝 إعداد المهمة", b"setup")],
            [Button.inline("⏯️ التحكم بالمهمة", b"control")],
            [Button.inline("📊 السجلات", b"logs")]
        ])

# ---------- أزرار ----------
@bot.on(events.CallbackQuery)
async def cb(e):
    data = e.data.decode()

    if data == "setup":
        groups = []
        async for d in user.iter_dialogs():
            if d.is_group or d.is_channel:
                groups.append({"id": d.id, "title": d.title})
        if not groups:
            await e.edit("لا توجد مجموعات.")
            return
        btns = [[Button.inline(g["title"], f"g_{g['id']}")] for g in groups] + [[Button.inline("✅ حفظ", b"save")]]
        await e.edit("اختر المجموعات:", buttons=btns)

    elif data.startswith("g_"):
        gid = int(data[2:])
        if gid in task.groups:
            task.groups.remove(gid)
        else:
            task.groups.append(gid)
        task.save()
        await cb(type(e)(data=b"setup"))

    elif data == "save":
        async with bot.conversation(e.sender_id) as c:
            await c.send("📄 أرسل النص:")
            task.text = (await c.get_response()).text
            await c.send("⏱️ الفاصل (دقائق ≥ 2):")
            task.interval = max(int((await c.get_response()).text), 2)
            task.save()
            await c.send("✅ تم حفظ المهمة.")
        await cb(type(e)(data=b"main"))

    elif data == "control":
        status = "🟢 نشطة" if task.active else "🔴 متوقفة"
        txt = (f"الحالة: {status}\n"
               f"المجموعات: {len(task.groups)}\n"
               f"النص: {task.text[:30]}...\n"
               f"الفاصل: {task.interval} د.")
        btns = []
        if task.groups and task.text:
            btns.append([Button.inline("⏸️ إيقاف" if task.active else "▶️ تشغيل", "toggle")])
        btns.append([Button.inline("🔄 إعادة", b"restart")])
        btns.append([Button.inline("🔙", b"main")])
        await e.edit(txt, buttons=btns)

    elif data == "toggle":
        task.active = not task.active
        task.save()
        await cb(type(e)(data=b"control"))

    elif data == "restart":
        task.counter.clear()
        task.active = True
        task.save()
        await e.answer("تم الإعادة.")
        await cb(type(e)(data=b"control"))

    elif data == "logs":
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, encoding="utf-8") as f:
                last = "".join(f.readlines()[-30:])
            await e.edit(f"<pre>{last}</pre>", parse_mode="html", buttons=[[Button.inline("🔙", b"main")]])
        else:
            await e.answer("لا توجد سجلات.")

    elif data == "main":
        await e.edit("القائمة الرئيسية:", buttons=[
            [Button.inline("📝 إعداد المهمة", b"setup")],
            [Button.inline("⏯️ التحكم بالمهمة", b"control")],
            [Button.inline("📊 السجلات", b"logs")]
        ])

# ---------- التشغيل ----------
async def main():
    # تسجيل دخول حساب المستخدم (مرة واحدة)
    await user.start()
    log.info("✅ تم توصيل حساب المستخدم")
    # تشغيل مهمة النشر في الخلفية
    asyncio.create_task(publish_worker())
    # تشغيل البوت
    await bot.start(bot_token=BOT_TOKEN)
    log.info("✅ Bot started")
    await bot.run_until_disconnected()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
