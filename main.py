import asyncio
import os
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict

from telethon import TelegramClient, events, Button
from telethon.tl.types import PeerChat, PeerChannel
from telethon.errors import ChatWriteForbiddenError, UserBannedInChannelError
import pytz

# ========== إعدادات أساسية ==========
API_ID = 23656977
API_HASH = "49d3f43531a92b3f5bc403766313ca1e"
BOT_TOKEN = "7966976239:AAFEtPbUEIqMVaLN20HH49zIMVSh4jKZJA4"

SESSION_DIR = "sessions"
DATA_DIR = "data"
ACCOUNTS_FILE = os.path.join(DATA_DIR, "accounts.json")
TASK_FILE = os.path.join(DATA_DIR, "task.json")
LOG_FILE = os.path.join(DATA_DIR, "bot.log")

os.makedirs(SESSION_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

tz = pytz.timezone("Africa/Cairo")

# ========== أدوات JSON ==========
def load_json(path: str, default=dict):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default()

def save_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ========== كائنات حالة المهمة ==========
class Task:
    def __init__(self):
        self.raw: Dict = load_json(TASK_FILE)
        self.active = self.raw.get("active", False)
        self.account = self.raw.get("account")          # str: phone
        self.groups = self.raw.get("groups", [])        # List[int]
        self.text = self.raw.get("text", "")
        self.interval = max(self.raw.get("interval", 2), 2)  # دقائق
        self.sent_counter = self.raw.get("sent_counter", {})

    def save(self):
        self.raw.update({
            "active": self.active,
            "account": self.account,
            "groups": self.groups,
            "text": self.text,
            "interval": self.interval,
            "sent_counter": self.sent_counter,
        })
        save_json(TASK_FILE, self.raw)

task = Task()

# ========== إدارة الحسابات ==========
accounts: Dict[str, TelegramClient] = {}   # phone -> client

async def reload_accounts():
    """تحميل/إعادة تحميل جميع الحسابات من accounts.json"""
    data = load_json(ACCOUNTS_FILE, list)
    phones_in_file = set(data)
    current_phones = set(accounts.keys())

    # إضافة جديد
    for phone in phones_in_file - current_phones:
        session_path = os.path.join(SESSION_DIR, f"{phone}.session")
        client = TelegramClient(session_path, API_ID, API_HASH)
        try:
            await client.start(phone)
            accounts[phone] = client
            log.info(f"تم توصيل الحساب {phone}")
        except Exception as e:
            log.error(f"فشل توصيل الحساب {phone}: {e}")

    # حذف قديم
    for phone in current_phones - phones_in_file:
        client = accounts.pop(phone)
        await client.disconnect()
        log.info(f"تم قطع الحساب {phone}")

async def get_groups(phone: str) -> List[Dict]:
    """إرجاع قائمة المجموعات التي يمكن للحساب الكتابة فيها"""
    client = accounts.get(phone)
    if not client:
        return []
    groups = []
    async for dialog in client.iter_dialogs():
        if dialog.is_group or dialog.is_channel:
            groups.append({
                "id": dialog.id,
                "title": dialog.title,
                "username": getattr(dialog.entity, "username", None)
            })
    return groups

# ========== مهمة النشر ==========
publish_lock = asyncio.Lock()

async def publish_worker():
    """الحلقة اللانهائية للنشر"""
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
                        entity = await client.get_input_entity(gid)
                        await client.send_message(entity, task.text)
                        task.sent_counter[str(gid)] = task.sent_counter.get(str(gid), 0) + 1
                        log.info(f"نشر إلى {gid}")
                    except ChatWriteForbiddenError:
                        log.warning(f"لا يمكن الكتابة في {gid}")
                    except UserBannedInChannelError:
                        log.warning(f"محظور في {gid}")
                    except Exception as e:
                        log.error(f"خطأ عند النشر إلى {gid}: {e}")
                task.save()
        await asyncio.sleep(task.interval * 60)

# ========== البوت ==========
bot = TelegramClient("bot", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# ---------- أوامر /start ----------
@bot.on(events.NewMessage(pattern="/start"))
async def cmd_start(event):
    await event.respond(
        "👋 أهلاً بك في بوت النشر التلقائي.\n"
        "استخدم الأزرار أدناه لإدارة الحسابات والمهام.",
        buttons=main_menu()
    )

def main_menu():
    return [
        [Button.inline("📱 إدارة الحسابات", b"accounts")],
        [Button.inline("📝 إعداد مهمة النشر", b"setup")],
        [Button.inline("⏯️ التحكم في المهمة", b"control")],
        [Button.inline("📊 السجلات", b"logs")]
    ]

# ---------- إدارة الحسابات ----------
@bot.on(events.CallbackQuery(data=b"accounts"))
async def manage_accounts(event):
    data = load_json(ACCOUNTS_FILE, list)
    text = "📱 الحسابات الحالية:\n" + "\n".join([f"• `{p}`" for p in data])
    buttons = [
        [Button.inline("➕ إضافة حساب", b"add_acc")],
        [Button.inline("➖ حذف حساب", b"del_acc")],
        [Button.inline("🔙 رجوع", b"main")]
    ]
    await event.edit(text, buttons=buttons)

@bot.on(events.CallbackQuery(data=b"add_acc"))
async def add_account_prompt(event):
    async with bot.conversation(event.sender_id) as conv:
        await conv.send_message("📞 أرسل رقم الهاتف مع رمز الدولة مثلاً `+201xxxxxxxxx`")
        phone = (await conv.get_response()).text.strip()
        session_path = os.path.join(SESSION_DIR, f"{phone}.session")
        client = TelegramClient(session_path, API_ID, API_HASH)
        try:
            await client.start(phone)
            accounts[phone] = client
            data = load_json(ACCOUNTS_FILE, list)
            if phone not in data:
                data.append(phone)
                save_json(ACCOUNTS_FILE, data)
            await conv.send_message("✅ تمت إضافة الحساب بنجاح!")
        except Exception as e:
            await conv.send_message(f"❌ فشلت الإضافة: {e}")
    await manage_accounts(event)

@bot.on(events.CallbackQuery(data=b"del_acc"))
async def delete_account_prompt(event):
    data = load_json(ACCOUNTS_FILE, list)
    if not data:
        await event.answer("لا توجد حسابات لحذفها.")
        return
    buttons = [[Button.inline(p, f"del_{p}")] for p in data] + [[Button.inline("🔙 رجوع", b"accounts")]]
    await event.edit("اختر الحساب لحذفه:", buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"del_(.+)"))
async def delete_account_confirm(event):
    phone = event.pattern_match.group(1).decode()
    data = load_json(ACCOUNTS_FILE, list)
    if phone in data:
        data.remove(phone)
        save_json(ACCOUNTS_FILE, data)
        client = accounts.pop(phone, None)
        if client:
            await client.disconnect()
    await manage_accounts(event)

# ---------- إعداد المهمة ----------
@bot.on(events.CallbackQuery(data=b"setup"))
async def setup_task(event):
    if task.active:
        await event.answer("⚠️ توجد مهمة نشطة بالفعل، أوقفها أولاً.")
        return
    accounts_data = load_json(ACCOUNTS_FILE, list)
    if not accounts_data:
        await event.answer("❌ لا توجد حسابات لاستخدامها.")
        return
    buttons = [[Button.inline(acc, f"pickacc_{acc}")] for acc in accounts_data]
    buttons.append([Button.inline("🔙 رجوع", b"main")])
    await event.edit("اختر الحساب للنشر:", buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"pickacc_(.+)"))
async def pick_account(event):
    phone = event.pattern_match.group(1).decode()
    task.account = phone
    task.save()
    groups = await get_groups(phone)
    if not groups:
        await event.edit("لا توجد مجموعات في هذا الحساب.")
        return
    buttons = [[Button.inline(g["title"], f"toggle_{g['id']}")] for g in groups]
    buttons.append([Button.inline("✅ حفظ المجموعات", b"save_groups")])
    text = "📝 اختر المجموعات للنشر (الزر يُغيّر الحالة):\n"
    selected = set(task.groups)
    for g in groups:
        mark = "✅" if g["id"] in selected else "❌"
        text += f"{mark} {g['title']}\n"
    await event.edit(text, buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"toggle_(-?\\d+)"))
async def toggle_group(event):
    gid = int(event.pattern_match.group(1))
    if gid in task.groups:
        task.groups.remove(gid)
    else:
        task.groups.append(gid)
    task.save()
    # إعادة عرض القائمة
    await pick_account(event)

@bot.on(events.CallbackQuery(data=b"save_groups"))
async def save_groups_step(event):
    async with bot.conversation(event.sender_id) as conv:
        await conv.send_message("📄 أرسل النص المطلوب نشره:")
        text = (await conv.get_response()).text
        await conv.send_message("⏱️ أرسل الفاصل الزمني (بالدقائق، الحد الأدنى 2):")
        interval = int((await conv.get_response()).text)
        interval = max(interval, 2)
        task.text = text
        task.interval = interval
        task.save()
        await conv.send_message("✅ تم حفظ إعدادات المهمة.")
    await event.edit("العودة للقائمة الرئيسية.", buttons=main_menu())

# ---------- التحكم في المهمة ----------
@bot.on(events.CallbackQuery(data=b"control"))
async def control_task(event):
    status = "🟢 نشطة" if task.active else "🔴 متوقفة"
    text = f"حالة المهمة: {status}\n"
    if task.account:
        text += f"الحساب: `{task.account}`\n"
        text += f"المجموعات: {len(task.groups)}\n"
        text += f"النص: {task.text[:30]}...\n"
        text += f"الفاصل: {task.interval} دقيقة\n"
    buttons = []
    if task.account and task.groups and task.text:
        if task.active:
            buttons.append([Button.inline("⏸️ إيقاف مؤقت", b"pause")])
        else:
            buttons.append([Button.inline("▶️ تشغيل", b"resume")])
    buttons.extend([
        [Button.inline("🔄 إعادة تشغيل", b"restart")],
        [Button.inline("🔙 رجوع", b"main")]
    ])
    await event.edit(text, buttons=buttons)

@bot.on(events.CallbackQuery(data=b"pause"))
async def pause_task(event):
    task.active = False
    task.save()
    await control_task(event)

@bot.on(events.CallbackQuery(data=b"resume"))
async def resume_task(event):
    task.active = True
    task.save()
    await control_task(event)

@bot.on(events.CallbackQuery(data=b"restart"))
async def restart_task(event):
    task.sent_counter.clear()
    task.active = True
    task.save()
    await event.answer("تم إعادة تشغيل المهمة.")
    await control_task(event)

# ---------- السجلات ----------
@bot.on(events.CallbackQuery(data=b"logs"))
async def show_logs(event):
    if not os.path.exists(LOG_FILE):
        await event.answer("لا توجد سجلات.")
        return
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
    last = "".join(lines[-30:])
    await event.edit(f"آخر 30 سطر من السجلات:\n<pre>{last}</pre>", parse_mode="html", buttons=[Button.inline("🔙 رجوع", b"main")])

# ---------- رجوع ----------
@bot.on(events.CallbackQuery(data=b"main"))
async def back_main(event):
    await event.edit("القائمة الرئيسية:", buttons=main_menu())

# ========== تشغيل البوت ==========
async def main():
    await reload_accounts()
    asyncio.create_task(publish_worker())
    log.info("Bot started")
    await bot.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
