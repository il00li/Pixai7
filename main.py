import os
import json
import time
import asyncio
import threading
from collections import defaultdict
import telebot
from telethon import TelegramClient, errors
from telebot import types
import logging


# تفعيل نظام التسجيل للمساعدة في التشخيص
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ⚙️ استخراج الإعدادات من المتغيرات البيئية (مهم لـ Render)
API_ID = int(os.getenv('API_ID', '23656977'))
API_HASH = os.getenv('API_HASH', '49d3f43531a92b3f5bc403766313ca1e')
BOT_TOKEN = os.getenv('BOT_TOKEN', '7966976239:AAGMg2RBAJEB_nDWGJEhsaOialSDJhWbAEE')

# 📁 إنشاء المجلدات المطلوبة
SESSIONS_DIR = "telegram_sessions"
TASK_FILE = "current_task.json"
os.makedirs(SESSIONS_DIR, exist_ok=True)

# 🧩 حالات المحادثة
ACCOUNT_PHONE, ACCOUNT_CODE, SETUP_ACCOUNT, SETUP_GROUPS, SETUP_CONTENT, SETUP_INTERVAL = range(6)

# 📦 مدير المهام
class TaskManager:
    def __init__(self):
        self.task = None
        self.stop_event = asyncio.Event()
        self.pause_event = asyncio.Event()
        self.group_status = {}
        self.message_count = defaultdict(int)
        self.current_settings = None
        self.bot = None
        self.user_id = None

    def set_bot(self, bot, user_id):
        self.bot = bot
        self.user_id = user_id

    async def start_task(self, account_session, groups, content, interval):
        self.stop_event.clear()
        self.pause_event.clear()
        self.message_count.clear()
        self.current_settings = {
            "account": account_session,
            "groups": groups,
            "content": content,
            "interval": interval
        }
        
        # حفظ الإعدادات في ملف
        with open(TASK_FILE, "w", encoding="utf-8") as f:
            json.dump(self.current_settings, f, ensure_ascii=False)
        
        # تشغيل حلقة النشر
        self.task = asyncio.create_task(
            self._posting_loop(account_session, groups, content, interval)
        )

    async def _posting_loop(self, account_session, groups, content, interval):
        client = TelegramClient(os.path.join(SESSIONS_DIR, account_session), API_ID, API_HASH)
        await client.connect()
        
        try:
            while not self.stop_event.is_set():
                if self.pause_event.is_set():
                    await asyncio.sleep(1)
                    continue
                    
                for group in groups:
                    if self.stop_event.is_set():
                        break
                    if not self.group_status.get(group, True):
                        continue
                        
                    try:
                        await client.send_message(group, content)
                        self.message_count[group] += 1
                        logger.info(f"تم نشر رسالة في المجموعة {group}")
                        
                        # إرسال إشعار إلى المستخدم
                        if self.bot and self.user_id:
                            self.bot.send_message(
                                self.user_id,
                                f"✅ تم نشر رسالة في المجموعة {group}"
                            )
                    except Exception as e:
                        logger.error(f"خطأ في نشر الرسالة في {group}: {str(e)}")
                        if self.bot and self.user_id:
                            self.bot.send_message(
                                self.user_id,
                                f"❌ خطأ في نشر الرسالة في {group}: {str(e)}"
                            )
                    await asyncio.sleep(interval)
        finally:
            await client.disconnect()

    async def stop_task(self):
        self.stop_event.set()
        if self.task:
            await self.task
            self.task = None
        if os.path.exists(TASK_FILE):
            os.remove(TASK_FILE)

    def pause_task(self):
        self.pause_event.set()

    def resume_task(self):
        self.pause_event.clear()

    def stop_group(self, group_id):
        self.group_status[group_id] = False

    def start_group(self, group_id):
        self.group_status[group_id] = True

    def get_status(self):
        if not self.current_settings:
            return "لا توجد مهمة نشطة"
        status = "مُعَطَّل" if self.pause_event.is_set() else "نشطة"
        return f"الحالة: {status}\nالمحتوى: {self.current_settings['content'][:20]}...\nالفاصل: {self.current_settings['interval']} ثانية"

# 🗄️ تهيئة مدير المهام
task_manager = TaskManager()

# 🌐 وظيفة البحث عن المجموعات
async def get_groups_for_account(session_file):
    client = TelegramClient(os.path.join(SESSIONS_DIR, session_file), API_ID, API_HASH)
    await client.connect()
    dialogs = await client.get_dialogs()
    groups = []
    
    for dialog in dialogs:
        if dialog.is_group or dialog.is_channel:
            try:
                # التحقق من صلاحيات النشر
                participant = await client.get_permissions(dialog)
                can_post = participant.post_messages if hasattr(participant, 'post_messages') else False
            except:
                can_post = False
            groups.append({
                "id": dialog.id,
                "name": dialog.name,
                "can_post": can_post
            })
    
    await client.disconnect()
    return groups

# 🤖 إنشاء بوت telebot
bot = telebot.TeleBot(BOT_TOKEN)

# 🤖 وظائف البوت

@bot.message_handler(commands=['start'])
def start(message):
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        types.InlineKeyboardButton("➕ إضافة حساب", callback_data="add_account"),
        types.InlineKeyboardButton("🗑️ حذف حساب", callback_data="delete_account"),
        types.InlineKeyboardButton("👥 عرض المجموعات", callback_data="list_groups"),
        types.InlineKeyboardButton("⚙️ إعداد مهمة نشر", callback_data="setup_task"),
        types.InlineKeyboardButton("⏯️ التحكم في المهمة", callback_data="control_task"),
        types.InlineKeyboardButton("📊 عرض السجلات", callback_data="view_logs")
    )
    bot.send_message(
        message.chat.id,
        "مرحباً! أنا بوت إدارة النشر التلقائي لتيليجرام.\nاختر خياراً من القائمة:",
        reply_markup=keyboard
    )

# --- إدارة الحسابات ---
@bot.callback_query_handler(func=lambda call: call.data == "add_account")
def add_account_start(call):
    bot.edit_message_text(
        "أدخل رقم الهاتف مع مفتاح الدولة (مثال: +966500000000):",
        call.message.chat.id,
        call.message.message_id
    )
    bot.register_next_step_handler(call.message, add_account_phone_step)

def add_account_phone_step(message):
    phone = message.text.strip()
    
    # حفظ الهاتف في بيانات المستخدم
    user_data = {
        "phone": phone,
        "state": "waiting_for_code"
    }
    # حفظ بيانات المستخدم في ملف
    with open(f"user_{message.chat.id}.json", "w") as f:
        json.dump(user_data, f)
    
    # إنشاء عميل تيليجرام مؤقت
    temp_session = f"temp_{phone.replace('+', '')}"
    
    async def send_code_request():
        client = TelegramClient(os.path.join(SESSIONS_DIR, temp_session), API_ID, API_HASH)
        await client.connect()
        try:
            await client.send_code_request(phone)
            logger.info(f"تم إرسال رمز التحقق إلى {phone}")
        except Exception as e:
            logger.error(f"خطأ في إرسال رمز التحقق: {str(e)}")
            bot.send_message(message.chat.id, f"❌ خطأ في إرسال رمز التحقق: {str(e)}")
        finally:
            await client.disconnect()
    
    # تشغيل العملية الآسنخرونية
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(send_code_request())
        bot.send_message(message.chat.id, "تم إرسال الرمز. أدخل الرمز الذي تلقيته:")
    finally:
        loop.close()

def add_account_code_step(message):
    code = message.text.strip()
    
    # قراءة بيانات المستخدم
    try:
        with open(f"user_{message.chat.id}.json", "r") as f:
            user_data = json.load(f)
        phone = user_data["phone"]
    except Exception as e:
        logger.error(f"خطأ في قراءة بيانات المستخدم: {str(e)}")
        bot.send_message(message.chat.id, "حدث خطأ. يرجى المحاولة مرة أخرى.")
        return
    
    # إنشاء عميل تيليجرام
    temp_session = f"temp_{phone.replace('+', '')}"
    
    async def sign_in():
        client = TelegramClient(os.path.join(SESSIONS_DIR, temp_session), API_ID, API_HASH)
        await client.connect()
        try:
            await client.sign_in(phone, code)
            # حفظ الجلسة الدائمة
            session_file = f"{phone.replace('+', '')}.session"
            await client.session.save(os.path.join(SESSIONS_DIR, session_file))
            logger.info(f"تم تسجيل الدخول بنجاح باستخدام {phone}")
            return True
        except Exception as e:
            logger.error(f"خطأ في التحقق: {str(e)}")
            return str(e)
        finally:
            await client.disconnect()
    
    # تشغيل العملية الآسنخرونية
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(sign_in())
        if result is True:
            bot.send_message(message.chat.id, "✅ تم إضافة الحساب بنجاح!")
            
            # حذف الجلسة المؤقتة
            temp_path = os.path.join(SESSIONS_DIR, temp_session)
            if os.path.exists(f"{temp_path}.session"):
                os.remove(f"{temp_path}.session")
        else:
            bot.send_message(message.chat.id, f"❌ خطأ في التحقق: {result}")
    finally:
        loop.close()

@bot.callback_query_handler(func=lambda call: call.data == "delete_account")
def delete_account(call):
    sessions = [f for f in os.listdir(SESSIONS_DIR) if f.endswith('.session') and not f.startswith('temp_')]
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    
    for session in sessions:
        phone = session.replace('.session', '')
        keyboard.add(types.InlineKeyboardButton(phone, callback_data=f"del_{session}"))
    
    bot.edit_message_text(
        "اختر الحساب للحذف:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=keyboard
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("del_"))
def confirm_delete(call):
    session_file = call.data[4:]
    
    keyboard = types.InlineKeyboardMarkup()
    keyboard.row(
        types.InlineKeyboardButton("✅ نعم", callback_data=f"confirm_del_{session_file}"),
        types.InlineKeyboardButton("❌ لا", callback_data="cancel_delete")
    )
    
    bot.edit_message_text(
        f"هل أنت متأكد من حذف الحساب {session_file}؟",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=keyboard
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_del_"))
def execute_delete(call):
    session_file = call.data[12:]
    
    # حذف ملف الجلسة
    session_path = os.path.join(SESSIONS_DIR, session_file)
    if os.path.exists(session_path):
        os.remove(session_path)
    
    bot.edit_message_text(
        "✅ تم حذف الحساب بنجاح!",
        call.message.chat.id,
        call.message.message_id
    )

@bot.callback_query_handler(func=lambda call: call.data == "cancel_delete")
def cancel_delete(call):
    bot.edit_message_text(
        "تم إلغاء عملية الحذف.",
        call.message.chat.id,
        call.message.message_id
    )

@bot.callback_query_handler(func=lambda call: call.data == "list_groups")
def list_groups(call):
    sessions = [f for f in os.listdir(SESSIONS_DIR) if f.endswith('.session') and not f.startswith('temp_')]
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    
    for session in sessions:
        phone = session.replace('.session', '')
        keyboard.add(types.InlineKeyboardButton(phone, callback_data=f"groups_{session}"))
    
    bot.edit_message_text(
        "اختر الحساب لعرض مجموعاته:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=keyboard
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("groups_"))
def show_groups(call):
    session_file = call.data[7:]
    
    async def get_groups():
        return await get_groups_for_account(session_file)
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        groups = loop.run_until_complete(get_groups())
    finally:
        loop.close()
    
    if not groups:
        bot.edit_message_text(
            "لا توجد مجموعات متاحة لهذا الحساب.",
            call.message.chat.id,
            call.message.message_id
        )
        return
    
    message = "المجموعات المتاحة مع حالة الصلاحيات:\n\n"
    for group in groups:
        status = "✅" if group["can_post"] else "❌"
        message += f"{status} {group['name']}\n"
    
    bot.edit_message_text(
        message,
        call.message.chat.id,
        call.message.message_id
    )

# --- إعداد مهمة النشر ---
@bot.callback_query_handler(func=lambda call: call.data == "setup_task")
def setup_task(call):
    sessions = [f for f in os.listdir(SESSIONS_DIR) if f.endswith('.session') and not f.startswith('temp_')]
    
    if not sessions:
        bot.edit_message_text(
            "❌ لم تقم بإضافة أي حسابات بعد. أضف حساباً أولاً.",
            call.message.chat.id,
            call.message.message_id
        )
        return
    
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    for session in sessions:
        phone = session.replace('.session', '')
        keyboard.add(types.InlineKeyboardButton(phone, callback_data=f"task_account_{session}"))
    
    bot.edit_message_text(
        "اختر الحساب الذي ستستخدمه في النشر:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=keyboard
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("task_account_"))
def select_account(call):
    session_file = call.data[12:]
    
    async def get_groups():
        return await get_groups_for_account(session_file)
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        groups = loop.run_until_complete(get_groups())
    finally:
        loop.close()
    
    # حفظ البيانات في ملف
    user_data = {
        "account": session_file,
        "all_groups": groups,
        "selected_groups": []
    }
    with open(f"user_{call.message.chat.id}.json", "w") as f:
        json.dump(user_data, f)
    
    # عرض المجموعات القابلة للنشر فقط
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    for group in groups:
        if group["can_post"]:
            keyboard.add(types.InlineKeyboardButton(group["name"], callback_data=f"sel_{group['id']}"))
    
    if not keyboard.keyboard:
        bot.edit_message_text(
            "❌ لا توجد مجموعات لديك صلاحية النشر فيها.",
            call.message.chat.id,
            call.message.message_id
        )
        return
    
    keyboard.add(types.InlineKeyboardButton("➡️ التالي", callback_data="next_step"))
    
    bot.edit_message_text(
        "اختر المجموعات المستهدفة (اضغط على المجموعة لتحديدها):",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=keyboard
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("sel_"))
def select_groups(call):
    group_id = int(call.data[4:])
    
    # قراءة بيانات المستخدم
    try:
        with open(f"user_{call.message.chat.id}.json", "r") as f:
            user_data = json.load(f)
    except Exception as e:
        logger.error(f"خطأ في قراءة بيانات المستخدم: {str(e)}")
        bot.answer_callback_query(call.id, "حدث خطأ. يرجى المحاولة مرة أخرى.", show_alert=True)
        return
    
    # تخزين المجموعات المختارة
    if "selected_groups" not in user_
        user_data["selected_groups"] = []
    
    if group_id in user_data["selected_groups"]:
        user_data["selected_groups"].remove(group_id)
        status = "تم إلغاء التحديد"
    else:
        user_data["selected_groups"].append(group_id)
        status = "تم التحديد"
    
    # تحديث البيانات
    with open(f"user_{call.message.chat.id}.json", "w") as f:
        json.dump(user_data, f)
    
    # تحديث الأزرار
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    for group in user_data["all_groups"]:
        if group["can_post"]:
            status_icon = "✅" if group["id"] in user_data["selected_groups"] else "▫️"
            keyboard.add(types.InlineKeyboardButton(f"{status_icon} {group['name']}", callback_data=f"sel_{group['id']}"))
    
    keyboard.add(types.InlineKeyboardButton("➡️ التالي", callback_data="next_step"))
    
    bot.edit_message_text(
        "اختر المجموعات المستهدفة:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=keyboard
    )

@bot.callback_query_handler(func=lambda call: call.data == "next_step")
def next_setup_step(call):
    # قراءة بيانات المستخدم
    try:
        with open(f"user_{call.message.chat.id}.json", "r") as f:
            user_data = json.load(f)
    except Exception as e:
        logger.error(f"خطأ في قراءة بيانات المستخدم: {str(e)}")
        bot.answer_callback_query(call.id, "حدث خطأ. يرجى المحاولة مرة أخرى.", show_alert=True)
        return
    
    if not user_data.get("selected_groups"):
        bot.answer_callback_query(call.id, "يجب اختيار مجموعة واحدة على الأقل!", show_alert=True)
        return
    
    bot.edit_message_text(
        "أدخل المحتوى النصي المراد نشره:",
        call.message.chat.id,
        call.message.message_id
    )
    bot.register_next_step_handler(call.message, enter_content_step)

def enter_content_step(message):
    content = message.text
    
    # قراءة بيانات المستخدم
    try:
        with open(f"user_{message.chat.id}.json", "r") as f:
            user_data = json.load(f)
    except Exception as e:
        logger.error(f"خطأ في قراءة بيانات المستخدم: {str(e)}")
        bot.send_message(message.chat.id, "حدث خطأ. يرجى المحاولة مرة أخرى.")
        return
    
    user_data["content"] = content
    
    # تحديث البيانات
    with open(f"user_{message.chat.id}.json", "w") as f:
        json.dump(user_data, f)
    
    bot.send_message(message.chat.id, "أدخل الفاصل الزمني بين النشر (بالثواني، الحد الأدنى 120):")
    bot.register_next_step_handler(message, enter_interval_step)

def enter_interval_step(message):
    try:
        interval = int(message.text)
        if interval < 120:
            bot.send_message(message.chat.id, "❌ الحد الأدنى للفاصل الزمني هو 120 ثانية. أعد المحاولة:")
            bot.register_next_step_handler(message, enter_interval_step)
            return
        
        # قراءة بيانات المستخدم
        try:
            with open(f"user_{message.chat.id}.json", "r") as f:
                user_data = json.load(f)
        except Exception as e:
            logger.error(f"خطأ في قراءة بيانات المستخدم: {str(e)}")
            bot.send_message(message.chat.id, "حدث خطأ. يرجى المحاولة مرة أخرى.")
            return
        
        user_data["interval"] = interval
        
        # عرض ملخص الإعدادات
        account = user_data["account"]
        groups = user_data["selected_groups"]
        content = user_data["content"][:20] + "..." if len(user_data["content"]) > 20 else user_data["content"]
        
        summary = (
            f"🎯 ملخص الإعدادات:\n"
            f"الحساب: {account}\n"
            f"المجموعات: {len(groups)} مجموعة\n"
            f"المحتوى: {content}\n"
            f"الفاصل: {interval} ثانية\n\n"
            f"هل تريد حفظ هذه الإعدادات وتشغيل المهمة؟"
        )
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.row(
            types.InlineKeyboardButton("✅ نعم", callback_data="start_task"),
            types.InlineKeyboardButton("❌ لا", callback_data="cancel_task")
        )
        
        bot.send_message(message.chat.id, summary, reply_markup=keyboard)
        
    except ValueError:
        bot.send_message(message.chat.id, "❌ يرجى إدخال رقم صحيح. أعد المحاولة:")
        bot.register_next_step_handler(message, enter_interval_step)

# --- التحكم في المهمة ---
@bot.callback_query_handler(func=lambda call: call.data == "control_task")
def control_task(call):
    if not task_manager.current_settings:
        bot.edit_message_text(
            "❌ لا توجد مهمة نشطة حالياً.",
            call.message.chat.id,
            call.message.message_id
        )
        return
    
    status = task_manager.get_status()
    
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        types.InlineKeyboardButton("⏸️ إيقاف مؤقت" if not task_manager.pause_event.is_set() else "▶️ استئناف", callback_data="toggle_pause"),
        types.InlineKeyboardButton("⏹️ إيقاف المهمة", callback_data="stop_task"),
        types.InlineKeyboardButton("🔧 تعديل الإعدادات", callback_data="modify_task")
    )
    
    bot.edit_message_text(
        f"{status}\n\nاختر إجراءً:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=keyboard
    )

@bot.callback_query_handler(func=lambda call: call.data == "toggle_pause")
def toggle_pause(call):
    if task_manager.pause_event.is_set():
        task_manager.resume_task()
        status_text = "✅ تم استئناف المهمة"
    else:
        task_manager.pause_task()
        status_text = "⏸️ تم إيقاف المهمة مؤقتاً"
    
    bot.answer_callback_query(call.id, status_text, show_alert=True)
    control_task(call)

@bot.callback_query_handler(func=lambda call: call.data == "stop_task")
def stop_task(call):
    async def stop():
        await task_manager.stop_task()
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(stop())
    finally:
        loop.close()
    
    bot.edit_message_text(
        "⏹️ تم إيقاف المهمة بنجاح!",
        call.message.chat.id,
        call.message.message_id
    )

@bot.callback_query_handler(func=lambda call: call.data == "start_task")
def start_task(call):
    # قراءة بيانات المستخدم
    try:
        with open(f"user_{call.message.chat.id}.json", "r") as f:
            user_data = json.load(f)
    except Exception as e:
        logger.error(f"خطأ في قراءة بيانات المستخدم: {str(e)}")
        bot.send_message(call.message.chat.id, "حدث خطأ. يرجى المحاولة مرة أخرى.")
        return
    
    # تعيين البوت في مدير المهام
    task_manager.set_bot(bot, call.message.chat.id)
    
    async def start_task_async():
        await task_manager.start_task(
            user_data["account"],
            user_data["selected_groups"],
            user_data["content"],
            user_data["interval"]
        )
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(start_task_async())
        bot.send_message(
            call.message.chat.id,
            "✅ تم تشغيل المهمة بنجاح!\nاستخدم 'التحكم في المهمة' لمراقبة الحالة."
        )
    finally:
        loop.close()

@bot.callback_query_handler(func=lambda call: call.data == "modify_task")
def modify_task(call):
    if not task_manager.current_settings:
        bot.edit_message_text(
            "❌ لا توجد مهمة نشطة لتعديلها.",
            call.message.chat.id,
            call.message.message_id
        )
        return
    
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        types.InlineKeyboardButton("📝 تعديل المحتوى", callback_data="modify_content"),
        types.InlineKeyboardButton("⏱️ تعديل الفاصل الزمني", callback_data="modify_interval"),
        types.InlineKeyboardButton("👥 تعديل المجموعات", callback_data="modify_groups")
    )
    
    bot.edit_message_text(
        "اختر ما تريد تعديله:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=keyboard
    )

# --- واجهة المستخدم ---
@bot.callback_query_handler(func=lambda call: call.data == "view_logs")
def view_logs(call):
    if not task_manager.current_settings:
        bot.edit_message_text(
            "لا توجد مهمة نشطة لعرض سجلاتها.",
            call.message.chat.id,
            call.message.message_id
        )
        return
    
    log_text = "📊 سجل النشر:\n\n"
    total_messages = 0
    for group_id, count in task_manager.message_count.items():
        log_text += f"• المجموعة {group_id}: {count} رسالة\n"
        total_messages += count
    
    log_text += f"\nإجمالي الرسائل: {total_messages}"
    log_text += f"\nالحالة الحالية: {'مُعَطَّل' if task_manager.pause_event.is_set() else 'نشطة'}"
    
    bot.edit_message_text(
        log_text,
        call.message.chat.id,
        call.message.message_id
    )

# 🚀 بدء البوت
def main():
    # تحميل المهمة السابقة إذا وجدت
    if os.path.exists(TASK_FILE):
        try:
            with open(TASK_FILE, "r", encoding="utf-8") as f:
                settings = json.load(f)
            
            # تعيين البوت في مدير المهام
            task_manager.set_bot(bot, None)  # سيتم تعيين معرف المستخدم لاحقاً
            
            async def start_previous_task():
                await task_manager.start_task(
                    settings["account"],
                    settings["groups"],
                    settings["content"],
                    settings["interval"]
                )
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(start_previous_task())
                logger.info("تم استعادة المهمة السابقة بنجاح")
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"خطأ في استعادة المهمة: {str(e)}")
    
    # بدء البوت
    logger.info("البوت يعمل الآن...")
    bot.infinity_polling()

if __name__ == "__main__":
    # تأكد من وجود المتغيرات البيئية المطلوبة
    if BOT_TOKEN == "YOUR_BOT_TOKEN":
        logger.error("يرجى تعيين متغير البيئة BOT_TOKEN")
        exit(1)
    
    logger.info("بدء تشغيل البوت...")
    main()
