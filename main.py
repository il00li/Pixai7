import os
import json
import time
import asyncio
from collections import defaultdict
from telethon import TelegramClient, functions, errors
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
import logging

# تفعيل نظام التسجيل للمساعدة في التشخيص
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ⚙️ الإعدادات الأساسية (يجب على المستخدم تعديلها)
API_ID = 23656977# ← أدخل هنا الـ API ID من my.telegram.org
API_HASH = "49d3f43531a92b3f5bc403766313ca1e"  # ← أدخل هنا الـ API HASH
BOT_TOKEN = "7966976239:AAELE0s0mZR8od1e55Xe1YcA-IDLgBsJ0bw"  # ← أدخل هنا رمز البوت من BotFather

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
                    except Exception as e:
                        logger.error(f"خطأ في نشر الرسالة في {group}: {str(e)}")
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

# 🤖 وظائف البوت

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("➕ إضافة حساب", callback_data="add_account")],
        [InlineKeyboardButton("🗑️ حذف حساب", callback_data="delete_account")],
        [InlineKeyboardButton("👥 عرض المجموعات", callback_data="list_groups")],
        [InlineKeyboardButton("⚙️ إعداد مهمة نشر", callback_data="setup_task")],
        [InlineKeyboardButton("⏯️ التحكم في المهمة", callback_data="control_task")],
        [InlineKeyboardButton("📊 عرض السجلات", callback_data="view_logs")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "مرحباً! أنا بوت إدارة النشر التلقائي لتيليجرام.\nاختر خياراً من القائمة:",
        reply_markup=reply_markup
    )

# --- إدارة الحسابات ---
async def add_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.edit_message_text("أدخل رقم الهاتف مع مفتاح الدولة (مثال: +966500000000):")
    return ACCOUNT_PHONE

async def add_account_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    context.user_data["phone"] = phone
    
    # إنشاء عميل تيليجرام مؤقت
    temp_session = f"temp_{phone.replace('+', '')}"
    client = TelegramClient(os.path.join(SESSIONS_DIR, temp_session), API_ID, API_HASH)
    await client.connect()
    
    # طلب إرسال الرمز
    await client.send_code_request(phone)
    context.user_data["client"] = client
    context.user_data["temp_session"] = temp_session
    
    await update.message.reply_text("تم إرسال الرمز. أدخل الرمز الذي تلقيته:")
    return ACCOUNT_CODE

async def add_account_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    client = context.user_data["client"]
    phone = context.user_data["phone"]
    
    try:
        await client.sign_in(phone, code)
        # حفظ الجلسة الدائمة
        session_file = f"{phone.replace('+', '')}.session"
        await client.session.save(os.path.join(SESSIONS_DIR, session_file))
        await update.message.reply_text("✅ تم إضافة الحساب بنجاح!")
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ في التحقق: {str(e)}")
    finally:
        await client.disconnect()
        # حذف الجلسة المؤقتة
        if "temp_session" in context.user_data:
            temp_path = os.path.join(SESSIONS_DIR, context.user_data["temp_session"])
            if os.path.exists(f"{temp_path}.session"):
                os.remove(f"{temp_path}.session")
    
    return ConversationHandler.END

async def delete_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sessions = [f for f in os.listdir(SESSIONS_DIR) if f.endswith('.session') and not f.startswith('temp_')]
    keyboard = []
    
    for session in sessions:
        phone = session.replace('.session', '')
        keyboard.append([InlineKeyboardButton(phone, callback_data=f"del_{session}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text("اختر الحساب للحذف:", reply_markup=reply_markup)

async def confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    session_file = query.data[4:]
    
    keyboard = [
        [InlineKeyboardButton("✅ نعم", callback_data=f"confirm_del_{session_file}"),
         InlineKeyboardButton("❌ لا", callback_data="cancel_delete")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"هل أنت متأكد من حذف الحساب {session_file}؟", reply_markup=reply_markup)

async def execute_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    session_file = query.data[12:]
    
    # حذف ملف الجلسة
    session_path = os.path.join(SESSIONS_DIR, session_file)
    if os.path.exists(session_path):
        os.remove(session_path)
    
    await query.edit_message_text("✅ تم حذف الحساب بنجاح!")

async def cancel_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.edit_message_text("تم إلغاء عملية الحذف.")

async def list_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sessions = [f for f in os.listdir(SESSIONS_DIR) if f.endswith('.session') and not f.startswith('temp_')]
    keyboard = []
    
    for session in sessions:
        phone = session.replace('.session', '')
        keyboard.append([InlineKeyboardButton(phone, callback_data=f"groups_{session}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text("اختر الحساب لعرض مجموعاته:", reply_markup=reply_markup)

async def show_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    session_file = query.data[7:]
    groups = await get_groups_for_account(session_file)
    
    if not groups:
        await query.edit_message_text("لا توجد مجموعات متاحة لهذا الحساب.")
        return
    
    message = "المجموعات المتاحة مع حالة الصلاحيات:\n\n"
    for group in groups:
        status = "✅" if group["can_post"] else "❌"
        message += f"{status} {group['name']}\n"
    
    await query.edit_message_text(message)

# --- إعداد مهمة النشر ---
async def setup_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sessions = [f for f in os.listdir(SESSIONS_DIR) if f.endswith('.session') and not f.startswith('temp_')]
    
    if not sessions:
        await update.callback_query.edit_message_text("❌ لم تقم بإضافة أي حسابات بعد. أضف حساباً أولاً.")
        return
    
    keyboard = []
    for session in sessions:
        phone = session.replace('.session', '')
        keyboard.append([InlineKeyboardButton(phone, callback_data=f"task_account_{session}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text("اختر الحساب الذي ستستخدمه في النشر:", reply_markup=reply_markup)

async def select_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    session_file = query.data[12:]
    context.user_data["account"] = session_file
    
    groups = await get_groups_for_account(session_file)
    context.user_data["all_groups"] = groups
    
    # عرض المجموعات القابلة للنشر فقط
    keyboard = []
    for group in groups:
        if group["can_post"]:
            keyboard.append([InlineKeyboardButton(group["name"], callback_data=f"sel_{group['id']}")])
    
    if not keyboard:
        await query.edit_message_text("❌ لا توجد مجموعات لديك صلاحية النشر فيها.")
        return
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("اختر المجموعات المستهدفة (اضغط على المجموعة لتحديدها):", reply_markup=reply_markup)

async def select_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    group_id = int(query.data[4:])
    
    # تخزين المجموعات المختارة
    if "selected_groups" not in context.user_data:
        context.user_data["selected_groups"] = []
    
    if group_id in context.user_data["selected_groups"]:
        context.user_data["selected_groups"].remove(group_id)
        status = "تم إلغاء التحديد"
    else:
        context.user_data["selected_groups"].append(group_id)
        status = "تم التحديد"
    
    # تحديث الأزرار
    keyboard = []
    for group in context.user_data["all_groups"]:
        if group["can_post"]:
            status_icon = "✅" if group["id"] in context.user_data["selected_groups"] else "▫️"
            keyboard.append([InlineKeyboardButton(f"{status_icon} {group['name']}", callback_data=f"sel_{group['id']}")])
    
    keyboard.append([InlineKeyboardButton("➡️ التالي", callback_data="next_step")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("اختر المجموعات المستهدفة:", reply_markup=reply_markup)

async def next_setup_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("selected_groups"):
        await update.callback_query.answer("يجب اختيار مجموعة واحدة على الأقل!", show_alert=True)
        return
    
    await update.callback_query.edit_message_text("أدخل المحتوى النصي المراد نشره:")
    return SETUP_CONTENT

async def enter_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    content = update.message.text
    context.user_data["content"] = content
    await update.message.reply_text("أدخل الفاصل الزمني بين النشر (بالثواني، الحد الأدنى 120):")
    return SETUP_INTERVAL

async def enter_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        interval = int(update.message.text)
        if interval < 120:
            await update.message.reply_text("❌ الحد الأدنى للفاصل الزمني هو 120 ثانية. أعد المحاولة:")
            return SETUP_INTERVAL
        
        context.user_data["interval"] = interval
        
        # عرض ملخص الإعدادات
        account = context.user_data["account"]
        groups = context.user_data["selected_groups"]
        content = context.user_data["content"][:20] + "..." if len(context.user_data["content"]) > 20 else context.user_data["content"]
        
        summary = (
            f"🎯 ملخص الإعدادات:\n"
            f"الحساب: {account}\n"
            f"المجموعات: {len(groups)} مجموعة\n"
            f"المحتوى: {content}\n"
            f"الفاصل: {interval} ثانية\n\n"
            f"هل تريد حفظ هذه الإعدادات وتشغيل المهمة؟"
        )
        
        keyboard = [
            [InlineKeyboardButton("✅ نعم", callback_data="start_task"),
             InlineKeyboardButton("❌ لا", callback_data="cancel_task")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(summary, reply_markup=reply_markup)
        
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ يرجى إدخال رقم صحيح. أعد المحاولة:")
        return SETUP_INTERVAL

# --- التحكم في المهمة ---
async def control_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not task_manager.current_settings:
        await update.callback_query.edit_message_text("❌ لا توجد مهمة نشطة حالياً.")
        return
    
    status = task_manager.get_status()
    keyboard = [
        [InlineKeyboardButton("⏸️ إيقاف مؤقت" if not task_manager.pause_event.is_set() else "▶️ استئناف", callback_data="toggle_pause")],
        [InlineKeyboardButton("⏹️ إيقاف المهمة", callback_data="stop_task")],
        [InlineKeyboardButton("🔧 تعديل الإعدادات", callback_data="modify_task")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(f"{status}\n\nاختر إجراءً:", reply_markup=reply_markup)

async def toggle_pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if task_manager.pause_event.is_set():
        task_manager.resume_task()
        status_text = "✅ تم استئناف المهمة"
    else:
        task_manager.pause_task()
        status_text = "⏸️ تم إيقاف المهمة مؤقتاً"
    
    await update.callback_query.answer(status_text)
    await control_task(update, context)

async def stop_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await task_manager.stop_task()
    await update.callback_query.edit_message_text("⏹️ تم إيقاف المهمة بنجاح!")

async def modify_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not task_manager.current_settings:
        await update.callback_query.edit_message_text("❌ لا توجد مهمة نشطة لتعديلها.")
        return
    
    keyboard = [
        [InlineKeyboardButton("📝 تعديل المحتوى", callback_data="modify_content")],
        [InlineKeyboardButton("⏱️ تعديل الفاصل الزمني", callback_data="modify_interval")],
        [InlineKeyboardButton("👥 تعديل المجموعات", callback_data="modify_groups")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text("اختر ما تريد تعديله:", reply_markup=reply_markup)

# --- واجهة المستخدم ---
async def view_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not task_manager.current_settings:
        await update.callback_query.edit_message_text("لا توجد مهمة نشطة لعرض سجلاتها.")
        return
    
    log_text = "📊 سجل النشر:\n\n"
    total_messages = 0
    for group_id, count in task_manager.message_count.items():
        log_text += f"• المجموعة {group_id}: {count} رسالة\n"
        total_messages += count
    
    log_text += f"\nإجمالي الرسائل: {total_messages}"
    log_text += f"\nالحالة الحالية: {'مُعَطَّل' if task_manager.pause_event.is_set() else 'نشطة'}"
    await update.callback_query.edit_message_text(log_text)

# --- معالجات الأخطاء ---
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("تم إلغاء العملية.")
    return ConversationHandler.END

# 🚀 بدء البوت (النسخة المحدثة والصحيحة)
def main():
    # تحميل المهمة السابقة إذا وجدت
    if os.path.exists(TASK_FILE):
        try:
            with open(TASK_FILE, "r", encoding="utf-8") as f:
                settings = json.load(f)
            asyncio.create_task(
                task_manager.start_task(
                    settings["account"],
                    settings["groups"],
                    settings["content"],
                    settings["interval"]
                )
            )
            logger.info("تم استعادة المهمة السابقة بنجاح")
        except Exception as e:
            logger.error(f"خطأ في استعادة المهمة: {str(e)}")
    
    # تهيئة التطبيق
    application = Application.builder().token(BOT_TOKEN).build()
    
    # معالج المحادثة لإضافة الحساب
    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(add_account_start, pattern="^add_account$"),
            CallbackQueryHandler(setup_task, pattern="^setup_task$")
        ],
        states={
            ACCOUNT_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_account_phone)],
            ACCOUNT_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_account_code)],
            SETUP_ACCOUNT: [CallbackQueryHandler(select_account, pattern="^task_account_")],
            SETUP_GROUPS: [
                CallbackQueryHandler(select_groups, pattern="^sel_"),
                CallbackQueryHandler(next_setup_step, pattern="^next_step$")
            ],
            SETUP_CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_content)],
            SETUP_INTERVAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_interval)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # إضافة المعالجات
    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)
    
    # معالجات القوائم
    application.add_handler(CallbackQueryHandler(delete_account, pattern="^delete_account$"))
    application.add_handler(CallbackQueryHandler(confirm_delete, pattern="^del_"))
    application.add_handler(CallbackQueryHandler(execute_delete, pattern="^confirm_del_"))
    application.add_handler(CallbackQueryHandler(cancel_delete, pattern="^cancel_delete$"))
    application.add_handler(CallbackQueryHandler(list_groups, pattern="^list_groups$"))
    application.add_handler(CallbackQueryHandler(show_groups, pattern="^groups_"))
    
    # معالجات التحكم في المهمة
    application.add_handler(CallbackQueryHandler(control_task, pattern="^control_task$"))
    application.add_handler(CallbackQueryHandler(toggle_pause, pattern="^toggle_pause$"))
    application.add_handler(CallbackQueryHandler(stop_task, pattern="^stop_task$"))
    application.add_handler(CallbackQueryHandler(modify_task, pattern="^modify_task$"))
    
    # معالجات السجلات
    application.add_handler(CallbackQueryHandler(view_logs, pattern="^view_logs$"))
    
    # تشغيل البوت (التصحيح هنا - هذه هي الطريقة الصحيحة للإصدار 20.x)
    print("البوت يعمل الآن... تأكد من أن إعدادات API_ID وAPI_HASH وBOT_TOKEN صحيحة.")
    print("لإيقاف البوت، اضغط Ctrl+C")
    application.run_polling()

if __name__ == "__main__":
    main()
```
