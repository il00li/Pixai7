import os
import json
import asyncio
import logging
from datetime import datetime
from telethon import TelegramClient, events, Button, functions, types
from telethon.errors import FloodWaitError, ChannelInvalidError, ChatWriteForbiddenError

# التكوينات الأساسية
API_ID = 23656977
API_HASH = '49d3f43531a92b3f5bc403766313ca1e'
BOT_TOKEN = '7966976239:AAHQAAu13b-8jot_BDUE_BniviWKlD5Bclc'  # استبدل هذا برمز البوت الخاص بك
DATA_DIR = 'data'
ACCOUNTS_FILE = os.path.join(DATA_DIR, 'accounts.json')
TASKS_FILE = os.path.join(DATA_DIR, 'tasks.json')
LOGS_DIR = os.path.join(DATA_DIR, 'logs')
MIN_INTERVAL = 120  # 2 دقائق بالثواني

# إنشاء المجلدات اللازمة
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# إعدادات التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename=os.path.join(LOGS_DIR, 'bot.log')
logger = logging.getLogger(__name__)

# هياكل البيانات
accounts = {}
tasks = {}
active_tasks = {}
user_states = {}

class AccountManager:
    @staticmethod
    def load_data():
        global accounts, tasks
        try:
            if os.path.exists(ACCOUNTS_FILE):
                with open(ACCOUNTS_FILE, 'r') as f:
                    accounts = json.load(f)
            if os.path.exists(TASKS_FILE):
                with open(TASKS_FILE, 'r') as f:
                    tasks = json.load(f)
        except Exception as e:
            logger.error(f"خطأ في تحميل البيانات: {e}")

    @staticmethod
    def save_accounts():
        with open(ACCOUNTS_FILE, 'w') as f:
            json.dump(accounts, f, indent=4, ensure_ascii=False)

    @staticmethod
    def save_tasks():
        with open(TASKS_FILE, 'w') as f:
            json.dump(tasks, f, indent=4, ensure_ascii=False)

    @staticmethod
    def get_user_accounts(user_id):
        return accounts.get(str(user_id), {}

    @staticmethod
    def add_account(user_id, phone, session_file):
        user_id = str(user_id)
        if user_id not in accounts:
            accounts[user_id] = {}
        accounts[user_id][phone] = {
            'session': session_file,
            'groups': {},
            'last_check': datetime.now().isoformat()
        }
        AccountManager.save_accounts()

    @staticmethod
    def delete_account(user_id, phone):
        user_id = str(user_id)
        if user_id in accounts and phone in accounts[user_id]:
            del accounts[user_id][phone]
            AccountManager.save_accounts()
            return True
        return False

class TaskManager:
    @staticmethod
    def create_task(user_id, account, groups, content, interval):
        user_id = str(user_id)
        tasks[user_id] = {
            'account': account,
            'groups': {g: {'status': 'active', 'count': 0} for g in groups},
            'content': content,
            'interval': max(interval, MIN_INTERVAL),
            'status': 'active',
            'created_at': datetime.now().isoformat(),
            'last_run': None
        }
        TaskManager.save_tasks()
        return tasks[user_id]

    @staticmethod
    def get_task(user_id):
        user_id = str(user_id)
        return tasks.get(user_id)

    @staticmethod
    def update_task(user_id, **kwargs):
        user_id = str(user_id)
        if user_id in tasks:
            tasks[user_id].update(kwargs)
            TaskManager.save_tasks()
            return True
        return False

    @staticmethod
    def save_tasks():
        with open(TASKS_FILE, 'w') as f:
            json.dump(tasks, f, indent=4, ensure_ascii=False)

    @staticmethod
    def pause_group(user_id, group_id):
        user_id = str(user_id)
        if user_id in tasks and group_id in tasks[user_id]['groups']:
            tasks[user_id]['groups'][group_id]['status'] = 'paused'
            TaskManager.save_tasks()
            return True
        return False

    @staticmethod
    def resume_group(user_id, group_id):
        user_id = str(user_id)
        if user_id in tasks and group_id in tasks[user_id]['groups']:
            tasks[user_id]['groups'][group_id]['status'] = 'active'
            TaskManager.save_tasks()
            return True
        return False

class TelegramAutoPoster:
    def __init__(self):
        self.bot = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)
        self.register_handlers()
        self.running_tasks = {}
        
    def register_handlers(self):
        self.bot.add_event_handler(self.handle_start, events.NewMessage(pattern='/start'))
        self.bot.add_event_handler(self.handle_add_account, events.NewMessage(pattern='/add_account'))
        self.bot.add_event_handler(self.handle_delete_account, events.NewMessage(pattern='/delete_account'))
        self.bot.add_event_handler(self.handle_create_task, events.NewMessage(pattern='/create_task'))
        self.bot.add_event_handler(self.handle_control_task, events.NewMessage(pattern='/control_task'))
        self.bot.add_event_handler(self.handle_callback, events.CallbackQuery())
        self.bot.add_event_handler(self.handle_message, events.NewMessage())

    async def handle_start(self, event):
        user_id = event.sender_id
        buttons = [
            [Button.inline("➕ إضافة حساب", b"add_account")],
            [Button.inline("📝 إنشاء مهمة نشر", b"create_task")],
            [Button.inline("⚙️ التحكم بالمهمة", b"control_task")]
        ]
        await event.respond("**مرحباً في بوت النشر التلقائي!**\nاختر أحد الخيارات:", buttons=buttons)

    async def handle_add_account(self, event):
        user_id = event.sender_id
        user_states[user_id] = {'action': 'add_account', 'step': 'phone'}
        await event.respond("📱 أدخل رقم الهاتف مع رمز الدولة (مثال: +201234567890):")

    async def handle_delete_account(self, event):
        user_id = event.sender_id
        user_accounts, _ = AccountManager.get_user_accounts(user_id)
        
        if not user_accounts:
            await event.respond("❌ ليس لديك أي حسابات مسجلة.")
            return
        
        buttons = []
        for phone in user_accounts:
            buttons.append([Button.inline(f"❌ {phone}", f"delete_account:{phone}")])
        
        buttons.append([Button.inline("🔙 رجوع", b"main_menu")])
        await event.respond("**اختر الحساب لحذفه:**", buttons=buttons)

    async def handle_create_task(self, event):
        user_id = event.sender_id
        user_accounts, _ = AccountManager.get_user_accounts(user_id)
        
        if not user_accounts:
            await event.respond("❌ ليس لديك أي حسابات مسجلة. أضف حساب أولاً.")
            return
        
        user_states[user_id] = {'action': 'create_task', 'step': 'select_account'}
        buttons = []
        for phone in user_accounts:
            buttons.append([Button.inline(f"👤 {phone}", f"select_account:{phone}")])
        
        buttons.append([Button.inline("🔙 رجوع", b"main_menu")])
        await event.respond("**اختر الحساب للنشر:**", buttons=buttons)

    async def handle_control_task(self, event):
        user_id = event.sender_id
        task = TaskManager.get_task(user_id)
        
        if not task:
            await event.respond("❌ ليس لديك مهمة نشطة.")
            return
        
        status_icon = "🟢" if task['status'] == 'active' else "🔴"
        buttons = [
            [Button.inline("⏸ إيقاف مؤقت", b"pause_task")],
            [Button.inline("▶️ استئناف النشر", b"resume_task")],
            [Button.inline("✏️ تعديل المحتوى", b"edit_content")],
            [Button.inline("⏱ تعديل الفاصل الزمني", b"edit_interval")],
            [Button.inline("📊 عرض الإحصائيات", b"show_stats")]
        ]
        await event.respond(
            f"**تحكم بالمهمة:**\n"
            f"- الحالة: {status_icon} {task['status']}\n"
            f"- عدد المجموعات: {len(task['groups'])}\n"
            f"- الفاصل الزمني: {task['interval']} ثانية",
            buttons=buttons
        )

    async def handle_callback(self, event):
        user_id = event.sender_id
        data = event.data.decode('utf-8')
        
        if data == "add_account":
            await self.handle_add_account(event)
        
        elif data == "create_task":
            await self.handle_create_task(event)
        
        elif data == "control_task":
            await self.handle_control_task(event)
        
        elif data == "main_menu":
            await self.handle_start(event)
        
        elif data.startswith("delete_account:"):
            phone = data.split(":")[1]
            if AccountManager.delete_account(user_id, phone):
                await event.respond(f"✅ تم حذف الحساب {phone} بنجاح")
            else:
                await event.respond("❌ فشل في حذف الحساب")
        
        elif data.startswith("select_account:"):
            phone = data.split(":")[1]
            user_states[user_id] = {
                'action': 'create_task',
                'step': 'select_groups',
                'account': phone
            }
            await event.respond("📝 أرسل روابط المجموعات (كل رابط في سطر مستقل):")
        
        elif data == "pause_task":
            if TaskManager.update_task(user_id, status='paused'):
                await event.respond("⏸ تم إيقاف المهمة مؤقتاً")
            else:
                await event.respond("❌ فشل في إيقاف المهمة")
        
        elif data == "resume_task":
            if TaskManager.update_task(user_id, status='active'):
                await event.respond("▶️ تم استئناف المهمة")
            else:
                await event.respond("❌ فشل في استئناف المهمة")
        
        await event.answer()

    async def handle_message(self, event):
        user_id = event.sender_id
        state = user_states.get(user_id, {})
        
        if state.get('action') == 'add_account' and state.get('step') == 'phone':
            phone = event.text.strip()
            if not phone.startswith('+'):
                await event.respond("❌ رقم الهاتف يجب أن يبدأ بعلامة +")
                return
            
            user_states[user_id] = {'action': 'add_account', 'step': 'code', 'phone': phone}
            await event.respond("🔑 أدخل رمز التحقق الذي تلقيته:")
        
        elif state.get('action') == 'add_account' and state.get('step') == 'code':
            code = event.text.strip()
            phone = state.get('phone')
            
            try:
                session_file = f"sessions/{user_id}_{phone}.session"
                client = TelegramClient(session_file, API_ID, API_HASH)
                await client.connect()
                
                if not await client.is_user_authorized():
                    await client.sign_in(phone, code=code)
                
                AccountManager.add_account(user_id, phone, session_file)
                await event.respond(f"✅ تم إضافة الحساب {phone} بنجاح!")
                del user_states[user_id]
                
                # تحديث قائمة المجموعات
                await self.update_account_groups(user_id, phone, client)
                
            except Exception as e:
                await event.respond(f"❌ فشل في إضافة الحساب: {str(e)}")
        
        elif state.get('action') == 'create_task' and state.get('step') == 'select_groups':
            groups = [line.strip() for line in event.text.split('\n') if line.strip()]
            account = state.get('account')
            
            user_states[user_id] = {
                'action': 'create_task',
                'step': 'enter_content',
                'account': account,
                'groups': groups
            }
            await event.respond("📝 أدخل المحتوى النصي الذي تريد نشره:")
        
        elif state.get('action') == 'create_task' and state.get('step') == 'enter_content':
            content = event.text
            account = state.get('account')
            groups = state.get('groups')
            
            user_states[user_id] = {
                'action': 'create_task',
                'step': 'set_interval',
                'account': account,
                'groups': groups,
                'content': content
            }
            await event.respond("⏱ أدخل الفاصل الزمني بين النشرات (بالثواني - الحد الأدنى 120 ثانية):")
        
        elif state.get('action') == 'create_task' and state.get('step') == 'set_interval':
            try:
                interval = max(int(event.text), MIN_INTERVAL)
                account = state.get('account')
                groups = state.get('groups')
                content = state.get('content')
                
                task = TaskManager.create_task(user_id, account, groups, content, interval)
                await event.respond(
                    f"✅ تم إنشاء المهمة بنجاح!\n"
                    f"- الحساب: {account}\n"
                    f"- عدد المجموعات: {len(groups)}\n"
                    f"- الفاصل الزمني: {interval} ثانية"
                )
                
                # بدء مهمة النشر
                if user_id not in self.running_tasks or self.running_tasks[user_id].done():
                    self.running_tasks[user_id] = asyncio.create_task(self.run_posting_task(user_id))
                
                del user_states[user_id]
                
            except ValueError:
                await event.respond("❌ يجب إدخال رقم صحيح للفاصل الزمني")

    async def update_account_groups(self, user_id, phone, client):
        try:
            dialogs = await client.get_dialogs()
            groups = {}
            
            for dialog in dialogs:
                if isinstance(dialog.entity, types.Channel) and dialog.is_group:
                    groups[str(dialog.id)] = {
                        'title': dialog.title,
                        'username': dialog.entity.username,
                        'last_check': datetime.now().isoformat()
                    }
            
            accounts[str(user_id)][phone]['groups'] = groups
            AccountManager.save_accounts()
            
        except Exception as e:
            logger.error(f"Error updating groups for {phone}: {e}")

    async def run_posting_task(self, user_id):
        user_id = str(user_id)
        while True:
            task = TaskManager.get_task(user_id)
            if not task or task['status'] != 'active':
                await asyncio.sleep(10)
                continue
            
            account_info = accounts.get(user_id, {}).get(task['account'])
            if not account_info:
                await self.bot.send_message(user_id, "❌ الحساب المرتبط بالمهمة غير موجود")
                break
            
            try:
                # إنشاء عميل للحساب
                client = TelegramClient(
                    account_info['session'],
                    API_ID,
                    API_HASH
                )
                await client.connect()
                
                if not await client.is_user_authorized():
                    await self.bot.send_message(user_id, f"❌ جلسة الحساب {task['account']} منتهية الصلاحية")
                    break
                
                # تنفيذ النشر في المجموعات
                for group_id, group_info in task['groups'].items():
                    if group_info['status'] != 'active':
                        continue
                    
                    try:
                        await client.send_message(int(group_id), task['content'])
                        task['groups'][group_id]['count'] += 1
                        logger.info(f"تم النشر في {group_id} للحساب {task['account']}")
                    except (FloodWaitError, ChannelInvalidError, ChatWriteForbiddenError) as e:
                        logger.warning(f"خطأ في النشر لـ {group_id}: {str(e)}")
                        task['groups'][group_id]['status'] = 'error'
                
                # تحديث بيانات المهمة
                task['last_run'] = datetime.now().isoformat()
                TaskManager.update_task(user_id, **task)
                
                # الانتظار للفاصل الزمني
                await asyncio.sleep(task['interval'])
                
            except Exception as e:
                logger.error(f"خطأ في مهمة النشر: {str(e)}")
                await self.bot.send_message(user_id, f"❌ خطأ جسيم في المهمة: {str(e)}")
                await asyncio.sleep(60)

    def run(self):
        self.bot.run_until_disconnected()

if __name__ == '__main__':
    AccountManager.load_data()
    TaskManager.save_tasks()
    poster = TelegramAutoPoster()
    
    # بدء مهام النشر للمهام النشطة
    for user_id in tasks:
        if tasks[user_id]['status'] == 'active':
            poster.running_tasks[user_id] = asyncio.create_task(poster.run_posting_task(user_id))
    
    poster.run()
