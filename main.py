# file: bot.py
import os
import json
import asyncio
import math
import time
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime

from telethon import TelegramClient, events, Button, types
from telethon.errors import SessionPasswordNeededError, FloodWaitError, ChatWriteForbiddenError
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.messages import GetFullChatRequest
from telethon.tl.types import Channel, Chat, ChatBannedRights

# ---------------------------
# مسارات التخزين
# ---------------------------
DATA_DIR = "data"
SESSIONS_DIR = os.path.join(DATA_DIR, "sessions")
ACCOUNTS_FILE = os.path.join(DATA_DIR, "accounts.json")
TASK_FILE = os.path.join(DATA_DIR, "task.json")
LOGS_FILE = os.path.join(DATA_DIR, "logs.json")
CONFIG_FILE = "config.json"

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(SESSIONS_DIR, exist_ok=True)

# ---------------------------
# تحميل الإعدادات
# ---------------------------
if not os.path.exists(CONFIG_FILE):
    raise RuntimeError("لم يتم العثور على config.json. رجاءً أنشِئه كما في التعليمات.")

with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

API_ID = CONFIG["23656977"]
API_HASH = CONFIG["49d3f43531a92b3f5bc403766313ca1e"]
BOT_TOKEN = CONFIG["7966976239:AAHQAAu13b-8jot_BDUE_BniviWKlD5Bclc"]

# ---------------------------
# أدوات مساعدة للملفات
# ---------------------------
file_lock = asyncio.Lock()

async def load_json(path: str, default: Any):
    async with file_lock:
        if not os.path.exists(path):
            return default
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

async def save_json(path: str, data: Any):
    async with file_lock:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

# ---------------------------
# هيكلية البيانات
# ---------------------------
# accounts.json:
# {
#   "accounts": {
#       "<user_id>": {
#           "session": "<string_session>",
#           "display": "<name_or_phone>"
#       }
#   }
# }
#
# task.json:
# {
#   "status": "جاهزة/نشطة/متوقفة/مكتملة",
#   "account_id": "<user_id>",
#   "group_ids": [int, ...],
#   "group_states": {
#       "<chat_id>": {"enabled": true, "sent_count": 0, "title": "<title>"}
#   },
#   "content": "<text>",
#   "interval_min": 2,
#   "last_cycle_at": 0
# }
#
# logs.json: قائمة مرتبة زمنياً
# [
#   {"ts": 1690000000.0, "account_id": "...", "chat_id": ..., "chat_title": "...", "status": "نجاح/فشل", "message": "نُشر/وصف الخطأ", "snippet": "أول 50 حرفاً"}
# ]

# ---------------------------
# عملاء Telethon
# ---------------------------
bot = TelegramClient("bot_session", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# عملاء حسابات المستخدمين (ينشؤون عند الطلب ويُحتفظ بهم في الذاكرة)
account_clients: Dict[str, TelegramClient] = {}
account_client_locks: Dict[str, asyncio.Lock] = {}

def _ensure_account_lock(acc_id: str):
    if acc_id not in account_client_locks:
        account_client_locks[acc_id] = asyncio.Lock()
    return account_client_locks[acc_id]

async def get_account_client(account_id: str) -> TelegramClient:
    # يعيد أو ينشئ عميل الحساب من StringSession
    if account_id in account_clients:
        return account_clients[account_id]
    accounts = await load_json(ACCOUNTS_FILE, {"accounts": {}})
    if account_id not in accounts.get("accounts", {}):
        raise RuntimeError("الحساب غير موجود.")
    session_str = accounts["accounts"][account_id]["session"]
    client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        raise RuntimeError("جلسة الحساب غير صالحة. يرجى إعادة تسجيل الدخول.")
    account_clients[account_id] = client
    return client

async def close_account_client(account_id: str):
    if account_id in account_clients:
        try:
            await account_clients[account_id].disconnect()
        except Exception:
            pass
        del account_clients[account_id]

# ---------------------------
# حالة المهمة والجدولة
# ---------------------------
task_lock = asyncio.Lock()
runner_task: Optional[asyncio.Task] = None

async def get_task() -> Optional[Dict[str, Any]]:
    return await load_json(TASK_FILE, None)

async def set_task(data: Optional[Dict[str, Any]]):
    if data is None:
        if os.path.exists(TASK_FILE):
            async with file_lock:
                os.remove(TASK_FILE)
        return
    await save_json(TASK_FILE, data)

def now_ts() -> float:
    return time.time()

def dt_str(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")

# ---------------------------
# السجل
# ---------------------------
async def append_log(entry: Dict[str, Any]):
    logs = await load_json(LOGS_FILE, [])
    logs.append(entry)
    # لا حدود صارمة، لكن يمكن تقليل الحجم إن لزم
    await save_json(LOGS_FILE, logs)

async def get_recent_logs(limit: int = 30) -> List[Dict[str, Any]]:
    logs = await load_json(LOGS_FILE, [])
    return logs[-limit:]

# ---------------------------
# أدوات المجموعات والصلاحيات
# ---------------------------
async def list_groups(client: TelegramClient) -> List[Tuple[int, str]]:
    groups = []
    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        title = dialog.name or "بدون اسم"
        if isinstance(entity, (Channel, Chat)):
            # نعتبر المجموعات والقنوات الفائقة (megagroups) فقط
            if isinstance(entity, Channel) and not entity.megagroup:
                # قناة بث غالباً، نتجنبها كوجهة للنشر بحساب مستخدم
                continue
            groups.append((entity.id, title))
    return groups

def has_send_restriction(entity) -> bool:
    # فحص أولي لحقوق الإرسال
    try:
        rights: Optional[ChatBannedRights] = getattr(entity, "default_banned_rights", None)
        if rights and getattr(rights, "send_messages", False):
            return True
    except Exception:
        pass
    return False

async def can_send_messages(client: TelegramClient, chat_id: int) -> bool:
    try:
        entity = await client.get_entity(chat_id)
        if has_send_restriction(entity):
            return False
        return True
    except ChatWriteForbiddenError:
        return False
    except Exception:
        # إذا فشل الفحص، سنحاول أثناء النشر مع التعامل مع الخطأ
        return True

# ---------------------------
# إشعارات متأخرة (10 ثوانٍ)
# ---------------------------
async def notify_with_delay(chat_id: int, text: str, delay: int = 10):
    await asyncio.sleep(delay)
    await bot.send_message(chat_id, text)

# ---------------------------
# واجهة المستخدم: القوائم
# ---------------------------
def main_menu():
    return [
        [Button.inline("➕ إضافة حساب", b"acc_add"), Button.inline("🗑 حذف حساب", b"acc_del")],
        [Button.inline("📜 حساباتي ومجموعاتي", b"acc_list")],
        [Button.inline("🗂 إعداد مهمة النشر", b"task_setup")],
        [Button.inline("▶️ بدء المهمة", b"task_start"), Button.inline("⏸ إيقاف مؤقت", b"task_pause"), Button.inline("▶️ استئناف", b"task_resume")],
        [Button.inline("⏹ إيقاف المهمة", b"task_stop"), Button.inline("🔁 إعادة تشغيل", b"task_restart")],
        [Button.inline("✏️ تعديل المحتوى", b"task_edit_content"), Button.inline("⏱ تعديل الفاصل", b"task_edit_interval")],
        [Button.inline("🚫 إيقاف مجموعة", b"group_disable"), Button.inline("✅ تفعيل مجموعة", b"group_enable")],
        [Button.inline("📊 حالة المهمة", b"task_status"), Button.inline("🧾 السجل", b"show_logs")]
    ]

async def send_home(event):
    await event.respond("مرحبًا بك في بوت النشر التلقائي 📢\nاختر من القائمة:", buttons=main_menu())

@bot.on(events.NewMessage(pattern=r"/start"))
async def start_cmd(event):
    if event.sender_id != OWNER_ID:
        return
    await send_home(event)

# ---------------------------
# إدارة حاليات الإدخال (Conversation State)
# ---------------------------
# نخزن حالة المحادثة لكل مالك (واحد)
conversation_state: Dict[str, Any] = {}

def set_state(key: str, value: Any):
    conversation_state[key] = value

def get_state(key: str, default=None):
    return conversation_state.get(key, default)

def clear_state(keys: List[str]):
    for k in keys:
        conversation_state.pop(k, None)

# ---------------------------
# إضافة حساب: تفاعلي (هاتف -> كود -> كلمة مرور إن وجدت)
# ---------------------------
@bot.on(events.CallbackQuery(data=b"acc_add"))
async def acc_add_cb(event):
    if event.sender_id != OWNER_ID:
        return await event.answer("غير مصرح.", alert=True)
    set_state("add_acc_step", "await_phone")
    await event.edit("أرسل رقم الهاتف للحساب الجديد بصيغة دولية (مثال: +2012XXXXXXX):")

@bot.on(events.NewMessage)
async def handle_text_inputs(event):
    if event.sender_id != OWNER_ID:
        return
    text = (event.raw_text or "").strip()

    # إضافة حساب: الخطوات
    add_step = get_state("add_acc_step")
    if add_step == "await_phone":
        phone = text
        set_state("add_acc_phone", phone)
        # إنشاء عميل مؤقت لإرسال الكود
        temp_client = TelegramClient(StringSession(), API_ID, API_HASH)
        await temp_client.connect()
        set_state("add_acc_client", temp_client)
        try:
            await temp_client.send_code_request(phone)
            set_state("add_acc_step", "await_code")
            await event.respond("تم إرسال كود التحقق. أرسل الكود الآن (بدون مسافات):")
        except Exception as e:
            await event.respond(f"فشل إرسال الكود: {e}")
            await temp_client.disconnect()
            clear_state(["add_acc_step", "add_acc_phone", "add_acc_client"])
        return

    if add_step == "await_code":
        code = text.replace(" ", "")
        temp_client: TelegramClient = get_state("add_acc_client")
        phone = get_state("add_acc_phone")
        try:
            await temp_client.sign_in(phone=phone, code=code)
        except SessionPasswordNeededError:
            set_state("add_acc_step", "await_2fa")
            return await event.respond("الحساب مفعّل بحماية كلمة المرور. أرسل كلمة المرور الآن:")
        except Exception as e:
            await event.respond(f"فشل تسجيل الدخول بالكود: {e}")
            await temp_client.disconnect()
            clear_state(["add_acc_step", "add_acc_phone", "add_acc_client"])
            return
        # النجاح بدون 2FA
        me = await temp_client.get_me()
        session_str = temp_client.session.save()
        await save_account(me, session_str, display=phone or me.username or str(me.id))
        await temp_client.disconnect()
        clear_state(["add_acc_step", "add_acc_phone", "add_acc_client"])
        await event.respond(f"✅ تم إضافة الحساب: {me.first_name} ({me.id})", buttons=main_menu())
        return

    if add_step == "await_2fa":
        password = text
        temp_client: TelegramClient = get_state("add_acc_client")
        phone = get_state("add_acc_phone")
        try:
            await temp_client.sign_in(password=password)
            me = await temp_client.get_me()
            session_str = temp_client.session.save()
            await save_account(me, session_str, display=phone or me.username or str(me.id))
            await temp_client.disconnect()
            clear_state(["add_acc_step", "add_acc_phone", "add_acc_client"])
            await event.respond(f"✅ تم إضافة الحساب: {me.first_name} ({me.id})", buttons=main_menu())
        except Exception as e:
            await event.respond(f"فشل التحقق بكلمة المرور: {e}")
            try:
                await temp_client.disconnect()
            except Exception:
                pass
            clear_state(["add_acc_step", "add_acc_phone", "add_acc_client"])
        return

    # إعداد المهمة: المحتوى/الفاصل
    ts_step = get_state("task_setup_step")
    if ts_step == "await_content":
        set_state("task_setup_content", text)
        set_state("task_setup_step", "await_interval")
        return await event.respond("أرسل الفاصل الزمني بالدقائق (الحد الأدنى 2):")
    if ts_step == "await_interval":
        try:
            minutes = max(2, int(text))
        except ValueError:
            return await event.respond("❌ الرجاء إدخال رقم صحيح (بالدقائق، 2 فأكثر).")
        # حفظ الإعدادات
        account_id = get_state("task_setup_account_id")
        selected_groups = get_state("task_setup_groups", [])
        content = get_state("task_setup_content")
        group_states = {str(cid): {"enabled": True, "sent_count": 0, "title": title} for cid, title in selected_groups}
        new_task = {
            "status": "جاهزة",
            "account_id": account_id,
            "group_ids": [cid for cid, _ in selected_groups],
            "group_states": group_states,
            "content": content,
            "interval_min": minutes,
            "last_cycle_at": 0
        }
        async with task_lock:
            await set_task(new_task)
        clear_state(["task_setup_step", "task_setup_account_id", "task_setup_groups", "task_setup_content"])
        return await event.respond(f"✅ تم إعداد المهمة. الفاصل: {minutes} دقيقة. استخدم ▶️ بدء المهمة.", buttons=main_menu())

    # تعديل المحتوى
    edit_step = get_state("edit_content_step")
    if edit_step == "await_new_content":
        async with task_lock:
            task = await get_task()
            if not task:
                clear_state(["edit_content_step"])
                return await event.respond("⚠ لا توجد مهمة.")
            task["content"] = text
            await set_task(task)
        clear_state(["edit_content_step"])
        return await event.respond("✅ تم تعديل المحتوى. سيُطبّق قبل النشر القادم.", buttons=main_menu())

    # تعديل الفاصل
    edit_int_step = get_state("edit_interval_step")
    if edit_int_step == "await_new_interval":
        try:
            minutes = max(2, int(text))
        except ValueError:
            return await event.respond("❌ الرجاء إدخال رقم صحيح (بالدقائق، 2 فأكثر).")
        async with task_lock:
            task = await get_task()
            if not task:
                clear_state(["edit_interval_step"])
                return await event.respond("⚠ لا توجد مهمة.")
            task["interval_min"] = minutes
            await set_task(task)
        clear_state(["edit_interval_step"])
        return await event.respond(f"✅ تم تعديل الفاصل إلى {minutes} دقيقة. سيُطبّق قبل النشر القادم.", buttons=main_menu())

# ---------------------------
# حفظ الحساب
# ---------------------------
async def save_account(me, session_str: str, display: str):
    accounts = await load_json(ACCOUNTS_FILE, {"accounts": {}})
    accounts["accounts"][str(me.id)] = {
        "session": session_str,
        "display": display
    }
    await save_json(ACCOUNTS_FILE, accounts)

# ---------------------------
# حذف حساب
# ---------------------------
@bot.on(events.CallbackQuery(data=b"acc_del"))
async def acc_del_cb(event):
    if event.sender_id != OWNER_ID:
        return await event.answer("غير مصرح.", alert=True)
    accounts = await load_json(ACCOUNTS_FILE, {"accounts": {}})
    accs = accounts.get("accounts", {})
    if not accs:
        return await event.edit("لا توجد حسابات.", buttons=main_menu())
    buttons = []
    for uid, info in accs.items():
        label = f"🗑 حذف: {info.get('display', uid)}"
        buttons.append([Button.inline(label, f"del::{uid}".encode("utf-8"))])
    buttons.append([Button.inline("⬅️ رجوع", b"back_home")])
    await event.edit("اختر حسابًا لحذفه:", buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"del::"))
async def acc_del_pick(event):
    if event.sender_id != OWNER_ID:
        return
    _, uid = event.data.decode("utf-8").split("::", 1)
    accounts = await load_json(ACCOUNTS_FILE, {"accounts": {}})
    if uid in accounts.get("accounts", {}):
        del accounts["accounts"][uid]
        await save_json(ACCOUNTS_FILE, accounts)
        await close_account_client(uid)
        await event.edit(f"✅ تم حذف الحساب: {uid}", buttons=main_menu())
    else:
        await event.answer("الحساب غير موجود.", alert=True)

# ---------------------------
# عرض الحسابات والمجموعات
# ---------------------------
@bot.on(events.CallbackQuery(data=b"acc_list"))
async def acc_list_cb(event):
    if event.sender_id != OWNER_ID:
        return
    accounts = await load_json(ACCOUNTS_FILE, {"accounts": {}})
    accs = accounts.get("accounts", {})
    if not accs:
        return await event.edit("لا توجد حسابات مضافة بعد.", buttons=main_menu())
    buttons = []
    for uid, info in accs.items():
        buttons.append([Button.inline(f"📜 مجموعات: {info.get('display', uid)}", f"lg::{uid}".encode("utf-8"))])
    buttons.append([Button.inline("⬅️ رجوع", b"back_home")])
    await event.edit("اختر حسابًا لعرض مجموعاته:", buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"lg::"))
async def list_groups_cb(event):
    if event.sender_id != OWNER_ID:
        return
    _, uid = event.data.decode("utf-8").split("::", 1)
    lock = _ensure_account_lock(uid)
    async with lock:
        try:
            client = await get_account_client(uid)
        except Exception as e:
            return await event.edit(f"تعذر فتح الحساب: {e}", buttons=main_menu())
        groups = await list_groups(client)
    total = len(groups)
    preview = "\n".join([f"- {title} ({cid})" for cid, title in groups[:30]])
    more = f"\n... والمزيد ({total-30})" if total > 30 else ""
    await event.edit(f"عدد المجموعات: {total}\n{preview}{more}", buttons=main_menu())

# ---------------------------
# إعداد المهمة: اختيار الحساب -> اختيار المجموعات -> المحتوى -> الفاصل
# ---------------------------
@bot.on(events.CallbackQuery(data=b"task_setup"))
async def task_setup_cb(event):
    if event.sender_id != OWNER_ID:
        return
    accounts = await load_json(ACCOUNTS_FILE, {"accounts": {}})
    accs = accounts.get("accounts", {})
    if not accs:
        return await event.edit("أضف حسابًا أولاً من خلال ➕ إضافة حساب.", buttons=main_menu())
    # اختيار الحساب
    buttons = []
    for uid, info in accs.items():
        buttons.append([Button.inline(f"اختر الحساب: {info.get('display', uid)}", f"ts_acc::{uid}".encode("utf-8"))])
    buttons.append([Button.inline("⬅️ رجوع", b"back_home")])
    await event.edit("اختر الحساب الذي سيتم استخدامه للنشر:", buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"ts_acc::"))
async def ts_choose_account(event):
    if event.sender_id != OWNER_ID:
        return
    _, uid = event.data.decode("utf-8").split("::", 1)
    set_state("task_setup_account_id", uid)
    # جلب المجموعات
    lock = _ensure_account_lock(uid)
    async with lock:
        try:
            client = await get_account_client(uid)
        except Exception as e:
            return await event.edit(f"تعذر فتح الحساب: {e}", buttons=main_menu())
        groups = await list_groups(client)
    if not groups:
        return await event.edit("لا توجد مجموعات متاحة لهذا الحساب.", buttons=main_menu())
    # حفظ قائمة المجموعات مؤقتًا
    set_state("ts_all_groups", groups)
    set_state("ts_selected_ids", set())
    await show_groups_selection(event, page=0)

async def show_groups_selection(event, page: int = 0, page_size: int = 10):
    groups: List[Tuple[int, str]] = get_state("ts_all_groups", [])
    selected: set = get_state("ts_selected_ids", set())
    total_pages = max(1, math.ceil(len(groups) / page_size))
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    chunk = groups[start:start + page_size]
    buttons = []
    for cid, title in chunk:
        mark = "✅" if cid in selected else "⚪"
        buttons.append([Button.inline(f"{mark} {title[:40]} ({cid})", f"ts_toggle::{cid}::{page}".encode("utf-8"))])
    nav = []
    if page > 0:
        nav.append(Button.inline("⬅️ السابق", f"ts_page::{page-1}".encode("utf-8")))
    if page < total_pages - 1:
        nav.append(Button.inline("التالي ➡️", f"ts_page::{page+1}".encode("utf-8")))
    if nav:
        buttons.append(nav)
    buttons.append([Button.inline("تم الاختيار ✅", f"ts_done::{page}".encode("utf-8"))])
    buttons.append([Button.inline("⬅️ إلغاء", b"back_home")])
    await event.edit(f"اختر المجموعات المستهدفة (صفحة {page+1}/{total_pages}):", buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"ts_toggle::"))
async def ts_toggle_group(event):
    if event.sender_id != OWNER_ID:
        return
    _, cid, page = event.data.decode("utf-8").split("::", 2)
    cid = int(cid); page = int(page)
    selected: set = get_state("ts_selected_ids", set())
    if cid in selected:
        selected.remove(cid)
    else:
        selected.add(cid)
    set_state("ts_selected_ids", selected)
    await show_groups_selection(event, page=page)

@bot.on(events.CallbackQuery(pattern=b"ts_page::"))
async def ts_page_nav(event):
    if event.sender_id != OWNER_ID:
        return
    _, page = event.data.decode("utf-8").split("::", 1)
    await show_groups_selection(event, page=int(page))

@bot.on(events.CallbackQuery(pattern=b"ts_done::"))
async def ts_done_groups(event):
    if event.sender_id != OWNER_ID:
        return
    groups: List[Tuple[int, str]] = get_state("ts_all_groups", [])
    selected_ids: set = get_state("ts_selected_ids", set())
    if not selected_ids:
        return await event.answer("اختر مجموعة واحدة على الأقل.", alert=True)
    # تقاطع الاختيار مع القائمة (للعناوين)
    selected_with_titles = [(cid, title) for cid, title in groups if cid in selected_ids]
    set_state("task_setup_groups", selected_with_titles)
    set_state("task_setup_step", "await_content")
    await event.edit(f"عدد المجموعات المختارة: {len(selected_with_titles)}\nأرسل المحتوى النصي المراد نشره:")

# ---------------------------
# بدء/إيقاف/استئناف/تعديل
# ---------------------------
@bot.on(events.CallbackQuery(data=b"task_start"))
async def task_start_cb(event):
    if event.sender_id != OWNER_ID:
        return
    async with task_lock:
        task = await get_task()
        if not task:
            return await event.edit("⚠ لا توجد مهمة مُعدة. استخدم 🗂 إعداد مهمة النشر أولاً.", buttons=main_menu())
        if task["status"] == "نشطة":
            return await event.answer("المهمة تعمل بالفعل.", alert=True)
        if task["status"] == "متوقفة" or task["status"] == "جاهزة" or task["status"] == "مكتملة":
            # تحقق الصلاحيات قبل البدء
            acc_id = task["account_id"]
            lock = _ensure_account_lock(acc_id)
            async with lock:
                try:
                    client = await get_account_client(acc_id)
                except Exception as e:
                    return await event.edit(f"تعذر فتح الحساب: {e}", buttons=main_menu())
                # تحقق لكل مجموعة
                ok, bad = [], []
                for cid in task["group_ids"]:
                    allowed = await can_send_messages(client, cid)
                    (ok if allowed else bad).append(cid)
                if bad:
                    # عطّل المجموعات غير المسموح بها
                    for cid in bad:
                        if str(cid) in task["group_states"]:
                            task["group_states"][str(cid)]["enabled"] = False
                await set_task(task)
            task["status"] = "نشطة"
            await set_task(task)
            global runner_task
            if runner_task and not runner_task.done():
                runner_task.cancel()
            runner_task = asyncio.create_task(task_runner(OWNER_ID))
            await event.edit("✅ تم بدء المهمة.", buttons=main_menu())

@bot.on(events.CallbackQuery(data=b"task_pause"))
async def task_pause_cb(event):
    if event.sender_id != OWNER_ID:
        return
    async with task_lock:
        task = await get_task()
        if not task or task["status"] != "نشطة":
            return await event.answer("لا توجد مهمة نشطة.", alert=True)
        task["status"] = "متوقفة"
        await set_task(task)
    await event.edit("⏸ تم إيقاف المهمة مؤقتًا.", buttons=main_menu())

@bot.on(events.CallbackQuery(data=b"task_resume"))
async def task_resume_cb(event):
    if event.sender_id != OWNER_ID:
        return
    async with task_lock:
        task = await get_task()
        if not task or task["status"] != "متوقفة":
            return await event.answer("المهمة ليست متوقفة مؤقتًا.", alert=True)
        task["status"] = "نشطة"
        await set_task(task)
    # تأكد من وجود العداء
    global runner_task
    if not runner_task or runner_task.done():
        runner_task = asyncio.create_task(task_runner(OWNER_ID))
    await event.edit("▶️ تم استئناف المهمة.", buttons=main_menu())

@bot.on(events.CallbackQuery(data=b"task_stop"))
async def task_stop_cb(event):
    if event.sender_id != OWNER_ID:
        return
    async with task_lock:
        task = await get_task()
        if not task or task["status"] not in ("نشطة", "متوقفة"):
            return await event.answer("لا توجد مهمة قيد التشغيل.", alert=True)
        task["status"] = "مكتملة"
        await set_task(task)
    await event.edit("جارٍ إنهاء المهمة... سيتم الإشعار بعد 10 ثوانٍ.", buttons=main_menu())
    asyncio.create_task(notify_with_delay(event.chat_id, "⏹ تم إنهاء المهمة نهائيًا.", delay=10))

@bot.on(events.CallbackQuery(data=b"task_restart"))
async def task_restart_cb(event):
    if event.sender_id != OWNER_ID:
        return
    async with task_lock:
        task = await get_task()
        if not task or task["status"] != "مكتملة":
            return await event.answer("لا توجد مهمة مكتملة لإعادة تشغيلها.", alert=True)
        # إعادة تعيين العدادات والإعداد للحالة نشطة
        for st in task["group_states"].values():
            st["sent_count"] = 0
        task["status"] = "نشطة"
        task["last_cycle_at"] = 0
        await set_task(task)
    global runner_task
    if runner_task and not runner_task.done():
        runner_task.cancel()
    runner_task = asyncio.create_task(task_runner(OWNER_ID))
    await event.edit("🔁 تم إعادة تشغيل المهمة.", buttons=main_menu())

@bot.on(events.CallbackQuery(data=b"task_edit_content"))
async def task_edit_content_cb(event):
    if event.sender_id != OWNER_ID:
        return
    set_state("edit_content_step", "await_new_content")
    await event.edit("أرسل المحتوى النصي الجديد:")

@bot.on(events.CallbackQuery(data=b"task_edit_interval"))
async def task_edit_interval_cb(event):
    if event.sender_id != OWNER_ID:
        return
    set_state("edit_interval_step", "await_new_interval")
    await event.edit("أرسل الفاصل الزمني الجديد بالدقائق (الحد الأدنى 2):")

# ---------------------------
# تمكين/تعطيل مجموعة ضمن المهمة
# ---------------------------
@bot.on(events.CallbackQuery(data=b"group_disable"))
async def group_disable_cb(event):
    if event.sender_id != OWNER_ID:
        return
    async with task_lock:
        task = await get_task()
        if not task:
            return await event.edit("⚠ لا توجد مهمة.", buttons=main_menu())
        buttons = []
        for cid in task["group_ids"]:
            st = task["group_states"].get(str(cid), {})
            if st.get("enabled", True):
                title = st.get("title", str(cid))
                buttons.append([Button.inline(f"🚫 تعطيل: {title}", f"gd::{cid}".encode("utf-8"))])
        if not buttons:
            buttons.append([Button.inline("لا توجد مجموعات مفعّلة.", b"noop")])
        buttons.append([Button.inline("⬅️ رجوع", b"back_home")])
        await event.edit("اختر مجموعة لتعطيلها:", buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"gd::"))
async def group_disable_pick(event):
    if event.sender_id != OWNER_ID:
        return
    _, cid = event.data.decode("utf-8").split("::", 1)
    cid = int(cid)
    async with task_lock:
        task = await get_task()
        if not task:
            return await event.answer("لا توجد مهمة.", alert=True)
        if str(cid) in task["group_states"]:
            task["group_states"][str(cid)]["enabled"] = False
            await set_task(task)
    await event.edit("✅ تم تعطيل المجموعة.", buttons=main_menu())

@bot.on(events.CallbackQuery(data=b"group_enable"))
async def group_enable_cb(event):
    if event.sender_id != OWNER_ID:
        return
    async with task_lock:
        task = await get_task()
        if not task:
            return await event.edit("⚠ لا توجد مهمة.", buttons=main_menu())
        buttons = []
        for cid in task["group_ids"]:
            st = task["group_states"].get(str(cid), {})
            if not st.get("enabled", True):
                title = st.get("title", str(cid))
                buttons.append([Button.inline(f"✅ تفعيل: {title}", f"ge::{cid}".encode("utf-8"))])
        if not buttons:
            buttons.append([Button.inline("لا توجد مجموعات معطّلة.", b"noop")])
        buttons.append([Button.inline("⬅️ رجوع", b"back_home")])
        await event.edit("اختر مجموعة لتفعيلها:", buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"ge::"))
async def group_enable_pick(event):
    if event.sender_id != OWNER_ID:
        return
    _, cid = event.data.decode("utf-8").split("::", 1)
    cid = int(cid)
    async with task_lock:
        task = await get_task()
        if not task:
            return await event.answer("لا توجد مهمة.", alert=True)
        if str(cid) in task["group_states"]:
            task["group_states"][str(cid)]["enabled"] = True
            await set_task(task)
    await event.edit("✅ تم تفعيل المجموعة.", buttons=main_menu())

# ---------------------------
# حالة المهمة والسجل
# ---------------------------
@bot.on(events.CallbackQuery(data=b"task_status"))
async def task_status_cb(event):
    if event.sender_id != OWNER_ID:
        return
    task = await get_task()
    if not task:
        return await event.edit("لا توجد مهمة حالياً.", buttons=main_menu())
    lines = [
        f"الحالة: {task['status']}",
        f"المحتوى: {task['content'][:60]}{'...' if len(task['content'])>60 else ''}",
        f"الفاصل: {task['interval_min']} دقيقة",
        f"آخر دورة: {dt_str(task['last_cycle_at']) if task['last_cycle_at'] else '—'}",
        f"المجموعات:"
    ]
    for cid in task["group_ids"]:
        st = task["group_states"].get(str(cid), {})
        title = st.get("title", str(cid))
        enabled = "مفعّلة" if st.get("enabled", True) else "معطّلة"
        cnt = st.get("sent_count", 0)
        lines.append(f"- {title} ({cid}) — {enabled} — أُرسلت: {cnt}")
    await event.edit("\n".join(lines), buttons=main_menu())

@bot.on(events.CallbackQuery(data=b"show_logs"))
async def show_logs_cb(event):
    if event.sender_id != OWNER_ID:
        return
    logs = await get_recent_logs(30)
    if not logs:
        return await event.edit("لا توجد سجلات بعد.", buttons=main_menu())
    lines = []
    for e in logs[-30:]:
        t = dt_str(ACCOUNTS_FILE, {"accounts": {}})
    accounts["accounts"][str(me.id)] = {
        "session": session_str,
        "display": display
    }
    await save_json(ACCOUNTS_FILE, accounts)

# ---------------------------
# حذف حساب
# ---------------------------
@bot.on(events.CallbackQuery(data=b"acc_del"))
async def acc_del_cb(event):
    if event.sender_id != OWNER_ID:
        return await event.answer("غير مصرح.", alert=True)
    accounts = await load_json(ACCOUNTS_FILE, {"accounts": {}})
    accs = accounts.get("accounts", {})
    if not accs:
        return await event.edit("لا توجد حسابات.", buttons=main_menu())
    buttons = []
    for uid, info in accs.items():
        label = f"🗑 حذف: {info.get('display', uid)}"
        buttons.append([Button.inline(label, f"del::{uid}".encode("utf-8"))])
    buttons.append([Button.inline("⬅️ رجوع", b"back_home")])
    await event.edit("اختر حسابًا لحذفه:", buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"del::"))
async def acc_del_pick(event):
    if event.sender_id != OWNER_ID:
        return
    _, uid = event.data.decode("utf-8").split("::", 1)
    accounts = await load_json(ACCOUNTS_FILE, {"accounts": {}})
    if uid in accounts.get("accounts", {}):
        del accounts["accounts"][uid]
        await save_json(ACCOUNTS_FILE, accounts)
        await close_account_client(uid)
        await event.edit(f"✅ تم حذف الحساب: {uid}", buttons=main_menu())
    else:
        await event.answer("الحساب غير موجود.", alert=True)

# ---------------------------
# عرض الحسابات والمجموعات
# ---------------------------
@bot.on(events.CallbackQuery(data=b"acc_list"))
async def acc_list_cb(event):
    if event.sender_id != OWNER_ID:
        return
    accounts = await load_json(ACCOUNTS_FILE, {"accounts": {}})
    accs = accounts.get("accounts", {})
    if not accs:
        return await event.edit("لا توجد حسابات مضافة بعد.", buttons=main_menu())
    buttons = []
    for uid, info in accs.items():
        buttons.append([Button.inline(f"📜 مجموعات: {info.get('display', uid)}", f"lg::{uid}".encode("utf-8"))])
    buttons.append([Button.inline("⬅️ رجوع", b"back_home")])
    await event.edit("اختر حسابًا لعرض مجموعاته:", buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"lg::"))
async def list_groups_cb(event):
    if event.sender_id != OWNER_ID:
        return
    _, uid = event.data.decode("utf-8").split("::", 1)
    lock = _ensure_account_lock(uid)
    async with lock:
        try:
            client = await get_account_client(uid)
        except Exception as e:
            return await event.edit(f"تعذر فتح الحساب: {e}", buttons=main_menu())
        groups = await list_groups(client)
    total = len(groups)
    preview = "\n".join([f"- {title} ({cid})" for cid, title in groups[:30]])
    more = f"\n... والمزيد ({total-30})" if total > 30 else ""
    await event.edit(f"عدد المجموعات: {total}\n{preview}{more}", buttons=main_menu())

# ---------------------------
# إعداد المهمة: اختيار الحساب -> اختيار المجموعات -> المحتوى -> الفاصل
# ---------------------------
@bot.on(events.CallbackQuery(data=b"task_setup"))
async def task_setup_cb(event):
    if event.sender_id != OWNER_ID:
        return
    accounts = await load_json(ACCOUNTS_FILE, {"accounts": {}})
    accs = accounts.get("accounts", {})
    if not accs:
        return await event.edit("أضف حسابًا أولاً من خلال ➕ إضافة حساب.", buttons=main_menu())
    # اختيار الحساب
    buttons = []
    for uid, info in accs.items():
        buttons.append([Button.inline(f"اختر الحساب: {info.get('display', uid)}", f"ts_acc::{uid}".encode("utf-8"))])
    buttons.append([Button.inline("⬅️ رجوع", b"back_home")])
    await event.edit("اختر الحساب الذي سيتم استخدامه للنشر:", buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"ts_acc::"))
async def ts_choose_account(event):
    if event.sender_id != OWNER_ID:
        return
    _, uid = event.data.decode("utf-8").split("::", 1)
    set_state("task_setup_account_id", uid)
    # جلب المجموعات
    lock = _ensure_account_lock(uid)
    async with lock:
        try:
            client = await get_account_client(uid)
        except Exception as e:
            return await event.edit(f"تعذر فتح الحساب: {e}", buttons=main_menu())
        groups = await list_groups(client)
    if not groups:
        return await event.edit("لا توجد مجموعات متاحة لهذا الحساب.", buttons=main_menu())
    # حفظ قائمة المجموعات مؤقتًا
    set_state("ts_all_groups", groups)
    set_state("ts_selected_ids", set())
    await show_groups_selection(event, page=0)

async def show_groups_selection(event, page: int = 0, page_size: int = 10):
    groups: List[Tuple[int, str]] = get_state("ts_all_groups", [])
    selected: set = get_state("ts_selected_ids", set())
    total_pages = max(1, math.ceil(len(groups) / page_size))
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    chunk = groups[start:start + page_size]
    buttons = []
    for cid, title in chunk:
        mark = "✅" if cid in selected else "⚪"
        buttons.append([Button.inline(f"{mark} {title[:40]} ({cid})", f"ts_toggle::{cid}::{page}".encode("utf-8"))])
    nav = []
    if page > 0:
        nav.append(Button.inline("⬅️ السابق", f"ts_page::{page-1}".encode("utf-8")))
    if page < total_pages - 1:
        nav.append(Button.inline("التالي ➡️", f"ts_page::{page+1}".encode("utf-8")))
    if nav:
        buttons.append(nav)
    buttons.append([Button.inline("تم الاختيار ✅", f"ts_done::{page}".encode("utf-8"))])
    buttons.append([Button.inline("⬅️ إلغاء", b"back_home")])
    await event.edit(f"اختر المجموعات المستهدفة (صفحة {page+1}/{total_pages}):", buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"ts_toggle::"))
async def ts_toggle_group(event):
    if event.sender_id != OWNER_ID:
        return
    _, cid, page = event.data.decode("utf-8").split("::", 2)
    cid = int(cid); page = int(page)
    selected: set = get_state("ts_selected_ids", set())
    if cid in selected:
        selected.remove(cid)
    else:
        selected.add(cid)
    set_state("ts_selected_ids", selected)
    await show_groups_selection(event, page=page)

@bot.on(events.CallbackQuery(pattern=b"ts_page::"))
async def ts_page_nav(event):
    if event.sender_id != OWNER_ID:
        return
    _, page = event.data.decode("utf-8").split("::", 1)
    await show_groups_selection(event, page=int(page))

@bot.on(events.CallbackQuery(pattern=b"ts_done::"))
async def ts_done_groups(event):
    if event.sender_id != OWNER_ID:
        return
    groups: List[Tuple[int, str]] = get_state("ts_all_groups", [])
    selected_ids: set = get_state("ts_selected_ids", set())
    if not selected_ids:
        return await event.answer("اختر مجموعة واحدة على الأقل.", alert=True)
    # تقاطع الاختيار مع القائمة (للعناوين)
    selected_with_titles = [(cid, title) for cid, title in groups if cid in selected_ids]
    set_state("task_setup_groups", selected_with_titles)
    set_state("task_setup_step", "await_content")
    await event.edit(f"عدد المجموعات المختارة: {len(selected_with_titles)}\nأرسل المحتوى النصي المراد نشره:")

# ---------------------------
# بدء/إيقاف/استئناف/تعديل
# ---------------------------
@bot.on(events.CallbackQuery(data=b"task_start"))
async def task_start_cb(event):
    if event.sender_id != OWNER_ID:
        return
    async with task_lock:
        task = await get_task()
        if not task:
            return await event.edit("⚠ لا توجد مهمة مُعدة. استخدم 🗂 إعداد مهمة النشر أولاً.", buttons=main_menu())
        if task["status"] == "نشطة":
            return await event.answer("المهمة تعمل بالفعل.", alert=True)
        if task["status"] == "متوقفة" or task["status"] == "جاهزة" or task["status"] == "مكتملة":
            # تحقق الصلاحيات قبل البدء
            acc_id = task["account_id"]
            lock = _ensure_account_lock(acc_id)
            async with lock:
                try:
                    client = await get_account_client(acc_id)
                except Exception as e:
                    return await event.edit(f"تعذر فتح الحساب: {e}", buttons=main_menu())
                # تحقق لكل مجموعة
                ok, bad = [], []
                for cid in task["group_ids"]:
                    allowed = await can_send_messages(client, cid)
                    (ok if allowed else bad).append(cid)
                if bad:
                    # عطّل المجموعات غير المسموح بها
                    for cid in bad:
                        if str(cid) in task["group_states"]:
                            task["group_states"][str(cid)]["enabled"] = False
                await set_task(task)
            task["status"] = "نشطة"
            await set_task(task)
            global runner_task
            if runner_task and not runner_task.done():
                runner_task.cancel()
            runner_task = asyncio.create_task(task_runner(OWNER_ID))
            await event.edit("✅ تم بدء المهمة.", buttons=main_menu())

@bot.on(events.CallbackQuery(data=b"task_pause"))
async def task_pause_cb(event):
    if event.sender_id != OWNER_ID:
        return
    async with task_lock:
        task = await get_task()
        if not task or task["status"] != "نشطة":
            return await event.answer("لا توجد مهمة نشطة.", alert=True)
        task["status"] = "متوقفة"
        await set_task(task)
    await event.edit("⏸ تم إيقاف المهمة مؤقتًا.", buttons=main_menu())

@bot.on(events.CallbackQuery(data=b"task_resume"))
async def task_resume_cb(event):
    if event.sender_id != OWNER_ID:
        return
    async with task_lock:
        task = await get_task()
        if not task or task["status"] != "متوقفة":
            return await event.answer("المهمة ليست متوقفة مؤقتًا.", alert=True)
        task["status"] = "نشطة"
        await set_task(task)
    # تأكد من وجود العداء
    global runner_task
    if not runner_task or runner_task.done():
        runner_task = asyncio.create_task(task_runner(OWNER_ID))
    await event.edit("▶️ تم استئناف المهمة.", buttons=main_menu())

@bot.on(events.CallbackQuery(data=b"task_stop"))
async def task_stop_cb(event):
    if event.sender_id != OWNER_ID:
        return
    async with task_lock:
        task = await get_task()
        if not task or task["status"] not in ("نشطة", "متوقفة"):
            return await event.answer("لا توجد مهمة قيد التشغيل.", alert=True)
        task["status"] = "مكتملة"
        await set_task(task)
    await event.edit("جارٍ إنهاء المهمة... سيتم الإشعار بعد 10 ثوانٍ.", buttons=main_menu())
    asyncio.create_task(notify_with_delay(event.chat_id, "⏹ تم إنهاء المهمة نهائيًا.", delay=10))

@bot.on(events.CallbackQuery(data=b"task_restart"))
async def task_restart_cb(event):
    if event.sender_id != OWNER_ID:
        return
    async with task_lock:
        task = await get_task()
        if not task or task["status"] != "مكتملة":
            return await event.answer("لا توجد مهمة مكتملة لإعادة تشغيلها.", alert=True)
        # إعادة تعيين العدادات والإعداد للحالة نشطة
        for st in task["group_states"].values():
            st["sent_count"] = 0
        task["status"] = "نشطة"
        task["last_cycle_at"] = 0
        await set_task(task)
    global runner_task
    if runner_task and not runner_task.done():
        runner_task.cancel()
    runner_task = asyncio.create_task(task_runner(OWNER_ID))
    await event.edit("🔁 تم إعادة تشغيل المهمة.", buttons=main_menu())

@bot.on(events.CallbackQuery(data=b"task_edit_content"))
async def task_edit_content_cb(event):
    if event.sender_id != OWNER_ID:
        return
    set_state("edit_content_step", "await_new_content")
    await event.edit("أرسل المحتوى النصي الجديد:")

@bot.on(events.CallbackQuery(data=b"task_edit_interval"))
async def task_edit_interval_cb(event):
    if event.sender_id != OWNER_ID:
        return
    set_state("edit_interval_step", "await_new_interval")
    await event.edit("أرسل الفاصل الزمني الجديد بالدقائق (الحد الأدنى 2):")

# ---------------------------
# تمكين/تعطيل مجموعة ضمن المهمة
# ---------------------------
@bot.on(events.CallbackQuery(data=b"group_disable"))
async def group_disable_cb(event):
    if event.sender_id != OWNER_ID:
        return
    async with task_lock:
        task = await get_task()
        if not task:
            return await event.edit("⚠ لا توجد مهمة.", buttons=main_menu())
        buttons = []
        for cid in task["group_ids"]:
            st = task["group_states"].get(str(cid), {})
            if st.get("enabled", True):
                title = st.get("title", str(cid))
                buttons.append([Button.inline(f"🚫 تعطيل: {title}", f"gd::{cid}".encode("utf-8"))])
        if not buttons:
            buttons.append([Button.inline("لا توجد مجموعات مفعّلة.", b"noop")])
        buttons.append([Button.inline("⬅️ رجوع", b"back_home")])
        await event.edit("اختر مجموعة لتعطيلها:", buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"gd::"))
async def group_disable_pick(event):
    if event.sender_id != OWNER_ID:
        return
    _, cid = event.data.decode("utf-8").split("::", 1)
    cid = int(cid)
    async with task_lock:
        task = await get_task()
        if not task:
            return await event.answer("لا توجد مهمة.", alert=True)
        if str(cid) in task["group_states"]:
            task["group_states"][str(cid)]["enabled"] = False
            await set_task(task)
    await event.edit("✅ تم تعطيل المجموعة.", buttons=main_menu())

@bot.on(events.CallbackQuery(data=b"group_enable"))
async def group_enable_cb(event):
    if event.sender_id != OWNER_ID:
        return
    async with task_lock:
        task = await get_task()
        if not task:
            return await event.edit("⚠ لا توجد مهمة.", buttons=main_menu())
        buttons = []
        for cid in task["group_ids"]:
            st = task["group_states"].get(str(cid), {})
            if not st.get("enabled", True):
                title = st.get("title", str(cid))
                buttons.append([Button.inline(f"✅ تفعيل: {title}", f"ge::{cid}".encode("utf-8"))])
        if not buttons:
            buttons.append([Button.inline("لا توجد مجموعات معطّلة.", b"noop")])
        buttons.append([Button.inline("⬅️ رجوع", b"back_home")])
        await event.edit("اختر مجموعة لتفعيلها:", buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"ge::"))
async def group_enable_pick(event):
    if event.sender_id != OWNER_ID:
        return
    _, cid = event.data.decode("utf-8").split("::", 1)
    cid = int(cid)
    async with task_lock:
        task = await get_task()
        if not task:
            return await event.answer("لا توجد مهمة.", alert=True)
        if str(cid) in task["group_states"]:
            task["group_states"][str(cid)]["enabled"] = True
            await set_task(task)
    await event.edit("✅ تم تفعيل المجموعة.", buttons=main_menu())

# ---------------------------
# حالة المهمة والسجل
# ---------------------------
@bot.on(events.CallbackQuery(data=b"task_status"))
async def task_status_cb(event):
    if event.sender_id != OWNER_ID:
        return
    task = await get_task()
    if not task:
        return await event.edit("لا توجد مهمة حالياً.", buttons=main_menu())
    lines = [
        f"الحالة: {task['status']}",
        f"المحتوى: {task['content'][:60]}{'...' if len(task['content'])>60 else ''}",
        f"الفاصل: {task['interval_min']} دقيقة",
        f"آخر دورة: {dt_str(task['last_cycle_at']) if task['last_cycle_at'] else '—'}",
        f"المجموعات:"
    ]
    for cid in task["group_ids"]:
        st = task["group_states"].get(str(cid), {})
        title = st.get("title", str(cid))
        enabled = "مفعّلة" if st.get("enabled", True) else "معطّلة"
        cnt = st.get("sent_count", 0)
        lines.append(f"- {title} ({cid}) — {enabled} — أُرسلت: {cnt}")
    await event.edit("\n".join(lines), buttons=main_menu())

@bot.on(events.CallbackQuery(data=b"show_logs"))
async def show_logs_cb(event):
    if event.sender_id != OWNER_ID:
        return
    logs = await get_recent_logs(30)
    if not logs:
        return await event.edit("لا توجد سجلات بعد.", buttons=main_menu())
    lines = []
    for e in logs[-30:]:
        t = dt_str(e["ts"])
        status = e["status"]
        title = e.get("chat_title", str(e.get("chat_id", "")))
        snippet = e.get("snippet", "")
        lines.append(f"[{t}] {status} | {title}: {snippet}")
    await event.edit("\n".join(lines[-30:]), buttons=main_menu())

@bot.on(events.CallbackQuery(data=b"back_home"))
async def back_home_cb(event):
    if event.sender_id != OWNER_ID:
        return
    await event.edit("القائمة الرئيسية:", buttons=main_menu())

@bot.on(events.CallbackQuery(data=b"noop"))
async def noop_cb(event):
    if event.sender_id != OWNER_ID:
        return
    await event.answer("—")

# ---------------------------
# العداء الأساسي للمهمة
# ---------------------------
async def task_runner(notify_chat_id: int):
    await bot.send_message(notify_chat_id, "⏳ تم تشغيل عدّاد المهمة.")
    while True:
        async with task_lock:
            task = await get_task()
        if not task:
            await bot.send_message(notify_chat_id, "⚠ لا توجد مهمة. إيقاف العداء.")
            return
        if task["status"] != "نشطة":
            # انتظر لحين الاستئناف أو الإنهاء
            await asyncio.sleep(2)
            # تحقق إن أصبحت مكتملة
            async with task_lock:
                task = await get_task()
                if task and task["status"] == "مكتملة":
                    await notify_with_delay(notify_chat_id, "✅ تم إنهاء المهمة (إشعار بعد 10 ثوانٍ).", delay=10)
                    return
            continue

        acc_id = task["account_id"]
        try:
            client = await get_account_client(acc_id)
        except Exception as e:
            await bot.send_message(notify_chat_id, f"❌ فشل فتح حساب المهمة: {e}")
            # إيقاف المهمة كمكتملة مع إشعار متأخر
            async with task_lock:
                task = await get_task()
                if task:
                    task["status"] = "مكتملة"
                    await set_task(task)
            asyncio.create_task(notify_with_delay(notify_chat_id, "⛔ تم إنهاء المهمة بسبب خطأ بالحساب.", delay=10))
            return

        interval_sec = max(2, task["interval_min"]) * 60
        any_sent = False

        for cid in task["group_ids"]:
            # تحقق من آخر حالة المهمة قبل كل إرسال
            async with task_lock:
                task_now = await get_task()
                if not task_now or task_now["status"] != "نشطة":
                    break
            st = task["group_states"].get(str(cid), {"enabled": True, "sent_count": 0, "title": str(cid)})
            if not st.get("enabled", True):
                continue

            content = task["content"]
            title = st.get("title", str(cid))

            try:
                await client.send_message(cid, content)
                st["sent_count"] = st.get("sent_count", 0) + 1
                any_sent = True
                await append_log({
                    "ts": now_ts(),
                    "account_id": acc_id,
                    "chat_id": cid,
                    "chat_title": title,
                    "status": "نجاح",
                    "message": "تم الإرسال",
                    "snippet": content[:50]
                })
                await bot.send_message(notify_chat_id, f"✅ نجاح | {title}: +1 (المجموع {st['sent_count']})")
            except FloodWaitError as e:
                await append_log({
                    "ts": now_ts(),
                    "account_id": acc_id,
                    "chat_id": cid,
                    "chat_title": title,
                    "status": "فشل",
                    "message": f"FloodWait {e.seconds}s",
                    "snippet": content[:50]
                })
                await bot.send_message(notify_chat_id, f"⏱ انتظار إجباري ({e.seconds}s) في {title}. سيتم التعطيل مؤقتًا.")
                # تعطيل المجموعة مؤقتًا
                st["enabled"] = False
            except ChatWriteForbiddenError:
                await append_log({
                    "ts": now_ts(),
                    "account_id": acc_id,
                    "chat_id": cid,
                    "chat_title": title,
                    "status": "فشل",
                    "message": "لا صلاحية للكتابة",
                    "snippet": content[:50]
                })
                await bot.send_message(notify_chat_id, f"🚫 لا صلاحية للكتابة في {title}. تعطيل المجموعة.")
                st["enabled"] = False
            except Exception as e:
                await append_log({
                    "ts": now_ts(),
                    "account_id": acc_id,
                    "chat_id": cid,
                    "chat_title": title,
