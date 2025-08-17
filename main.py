# bot.py
# ملف واحد مُحدَّث للتعامل مع server-less (Render) ومنع خطأ event loop
# pip install telethon python-socks[asyncio] pytz

import os, json, logging, asyncio, pytz
from datetime import datetime
from typing import Dict, List

from telethon import TelegramClient, events, Button
from telethon.errors import ChatWriteForbiddenError, UserBannedInChannelError

# ---------- إعدادات ----------
API_ID   = 23656977
API_HASH = "49d3f43531a92b3f5bc403766313ca1e"
BOT_TOKEN = "7966976239:AAFEtPbUEIqMVaLN20HH49zIMVSh4jKZJA4"

SESSION_DIR = "sessions"
DATA_DIR    = "data"
os.makedirs(SESSION_DIR, exist_ok=True)
os.makedirs(DATA_DIR,   exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.FileHandler(os.path.join(DATA_DIR, "bot.log"), encoding="utf-8"),
              logging.StreamHandler()]
)
log = logging.getLogger(__name__)

# ---------- أدوات JSON ----------
def load_json(path: str, default=dict):
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else default()

def save_json(path: str, data):
    json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

# ---------- إدارة الحسابات ----------
accounts: Dict[str, TelegramClient] = {}

async def reload_accounts():
    phones = load_json(os.path.join(DATA_DIR, "accounts.json"), list)
    for p in phones:
        if p in accounts:
            continue
        session = os.path.join(SESSION_DIR, f"{p}.session")
        client = TelegramClient(session, API_ID, API_HASH)
        try:
            await client.start(phone=p)
            accounts[p] = client
            log.info(f"✅ تم توصيل {p}")
        except Exception as e:
            log.error(f"❌ فشل توصيل {p} : {e}")

async def get_groups(phone: str):
    if phone not in accounts:
        return []
    client = accounts[phone]
    res = []
    async for d in client.iter_dialogs():
        if d.is_group or d.is_channel:
            res.append({"id": d.id, "title": d.title})
    return res

# ---------- مهمة النشر ----------
class Task:
    def __init__(self):
        self.file = os.path.join(DATA_DIR, "task.json")
        self.data = load_json(self.file)
    def save(self):
        save_json(self.file, self.data)
    @property
    def active(self): return self.data.get("active", False)
    @active.setter
    def active(self, v): self.data["active"] = v
    @property
    def account(self): return self.data.get("account")
    @account.setter
    def account(self, v): self.data["account"] = v
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
    while True:
        if task.active and task.account and task.text and task.groups:
            client = accounts.get(task.account)
            if not client:
                task.active = False
                task.save()
                log.warning("الحساب غير متصل، تم إيقاف المهمة")
            else:
                for gid in task.groups:
                    try:
                        ent = await client.get_input_entity(gid)
                        await client.send_message(ent, task.text)
                        task.counter[str(gid)] = task.counter.get(str(gid), 0) + 1
                        log.info(f"📤 نشر إلى {gid}")
                    except Exception as e:
                        log.error(f"خطأ في {gid}: {e}")
                task.save()
        await asyncio.sleep(task.interval * 60)

# ---------- البوت ----------
bot = TelegramClient("bot", API_ID, API_HASH)

@bot.on(events.NewMessage(pattern="/start"))
async def start(event):
    await event.respond(
        "👋 أهلاً بك في بوت النشر التلقائي.",
        buttons=[
            [Button.inline("📱 إدارة الحسابات", b"accounts")],
            [Button.inline("📝 إعداد المهمة", b"setup")],
            [Button.inline("⏯️ التحكم", b"control")],
            [Button.inline("📊 السجلات", b"logs")]
        ])

# ---------- أزرار ----------
@bot.on(events.CallbackQuery)
async def callback(e):
    data = e.data.decode()
    if data == "accounts":
        accs = load_json(os.path.join(DATA_DIR, "accounts.json"), list)
        btns = [[Button.inline(f"➕ إضافة", b"add")]] + [[Button.inline(p, f"del_{p}") for p in accs]] + [[Button.inline("🔙", b"main")]]
        await e.edit("📱 إدارة الحسابات", buttons=btns)

    elif data == "add":
        async with bot.conversation(e.sender_id) as c:
            await c.send("📞 أرسل رقم الهاتف مع رمز الدولة:")
            phone = (await c.get_response()).text.strip()
            await reload_accounts()
            if phone in accounts:
                await c.send("✅ الحساب متصل بالفعل.")
            else:
                await c.send("🔄 جارٍ توصيل الحساب...")
                session = os.path.join(SESSION_DIR, f"{phone}.session")
                client = TelegramClient(session, API_ID, API_HASH)
                try:
                    await client.start(phone=phone)
                    accounts[phone] = client
                    accs = load_json(os.path.join(DATA_DIR, "accounts.json"), list)
                    if phone not in accs:
                        accs.append(phone)
                        save_json(os.path.join(DATA_DIR, "accounts.json"), accs)
                    await c.send("✅ تمت إضافة الحساب.")
                except Exception as ex:
                    await c.send(f"❌ فشل: {ex}")
        await callback(e)  # refresh

    elif data.startswith("del_"):
        phone = data[4:]
        accs = load_json(os.path.join(DATA_DIR, "accounts.json"), list)
        if phone in accs:
            accs.remove(phone)
            save_json(os.path.join(DATA_DIR, "accounts.json"), accs)
            if phone in accounts:
                await accounts[phone].disconnect()
                del accounts[phone]
        await callback(type(e)(data=b"accounts"))

    elif data == "setup":
        if task.active:
            await e.answer("⚠️ أوقف المهمة أولاً.")
            return
        accs = load_json(os.path.join(DATA_DIR, "accounts.json"), list)
        if not accs:
            await e.answer("❌ لا توجد حسابات.")
            return
        await e.edit("اختر الحساب:", buttons=[[Button.inline(acc, f"acc_{acc}")] for acc in accs] + [[Button.inline("🔙", b"main")]])

    elif data.startswith("acc_"):
        phone = data[4:]
        task.account = phone
        task.save()
        groups = await get_groups(phone)
        if not groups:
            await e.edit("لا توجد مجموعات.")
            return
        btns = [[Button.inline(g["title"], f"grp_{g['id']}")] for g in groups] + [[Button.inline("✅ حفظ", b"save_task")]]
        await e.edit("اختر المجموعات:", buttons=btns)

    elif data.startswith("grp_"):
        gid = int(data[4:])
        if gid in task.groups:
            task.groups.remove(gid)
        else:
            task.groups.append(gid)
        task.save()
        await callback(type(e)(data=f"acc_{task.account}"))

    elif data == "save_task":
        async with bot.conversation(e.sender_id) as c:
            await c.send("📄 أرسل النص:")
            task.text = (await c.get_response()).text
            await c.send("⏱️ الفاصل (دقائق ≥ 2):")
            task.interval = max(int((await c.get_response()).text), 2)
            task.save()
            await c.send("✅ تم حفظ المهمة.")
        await callback(type(e)(data=b"main"))

    elif data == "control":
        status = "🟢 نشطة" if task.active else "🔴 متوقفة"
        txt = f"الحالة: {status}\nالحساب: {task.account}\nالمجموعات: {len(task.groups)}\nالنص: {task.text[:30]}...\nالفاصل: {task.interval} د."
        btns = []
        if task.account and task.groups and task.text:
            btns.append([Button.inline("⏸️ إيقاف" if task.active else "▶️ تشغيل", "toggle_task")])
        btns.append([Button.inline("🔄 إعادة", b"restart")])
        btns.append([Button.inline("🔙", b"main")])
        await e.edit(txt, buttons=btns)

    elif data == "toggle_task":
        task.active = not task.active
        task.save()
        await callback(type(e)(data=b"control"))

    elif data == "restart":
        task.counter.clear()
        task.active = True
        task.save()
        await e.answer("تم الإعادة.")
        await callback(type(e)(data=b"control"))

    elif data == "logs":
        if os.path.exists(os.path.join(DATA_DIR, "bot.log")):
            with open(os.path.join(DATA_DIR, "bot.log"), encoding="utf-8") as f:
                last = "".join(f.readlines()[-30:])
            await e.edit(f"<pre>{last}</pre>", parse_mode="html", buttons=[[Button.inline("🔙", b"main")]])
        else:
            await e.answer("لا توجد سجلات.")

    elif data == "main":
        await e.edit("القائمة الرئيسية", buttons=[
            [Button.inline("📱 إدارة الحسابات", b"accounts")],
            [Button.inline("📝 إعداد المهمة", b"setup")],
            [Button.inline("⏯️ التحكم", b"control")],
            [Button.inline("📊 السجلات", b"logs")]
        ])

# ---------- التشغيل ----------
async def on_start():
    await reload_accounts()
    asyncio.create_task(publish_worker())
    log.info("Bot started")

if __name__ == "__main__":
    import nest_asyncio, asyncio
    nest_asyncio.apply()  # يسمح بتشغيل loop داخل loop (server-less)
    with bot:
        bot.loop.run_until_complete(on_start())
        bot.run_until_disconnected()
 
