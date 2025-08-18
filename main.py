import os
import re
import time
import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta
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

# ===== الإعدادات المباشرة =====
API_ID = 23656977
API_HASH = '49d3f43531a92b3f5bc403766313ca1e'
BOT_TOKEN = '8110119856:AAGZ7RNsHQuHncEgZ4af7FVom8uSnMP_CAM'
ADMIN_ID = 7251748706  # أيدي المدير المحدد
TIMEOUT = 300  # 300 ثانية = 5 دقائق
MANDATORY_CHANNELS = ['crazys7', 'AWU87']  # قنوات الاشتراك الإجباري
MIN_INVITES = 5  # الحد الأدنى من الدعوات المطلوبة
WEBHOOK_URL = 'https://pixai7.onrender.com/webhook'  # رابط الويب هووك
PORT = 8000  # منفذ الخادم

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
    interval INTEGER DEFAULT 180,
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
    user_id INTEGER,
    referral_code TEXT UNIQUE,
    invited_users INTEGER DEFAULT 0
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS pulled_accounts (
    account_id INTEGER PRIMARY KEY,
    user_id INTEGER,
    phone TEXT,
    session TEXT,
    pulled_by INTEGER,
    active BOOLEAN DEFAULT 1
)
''')

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
    # الحصول على الإعدادات الحالية
    current_interval, current_message, current_active = get_user_settings(user_id)
    
    # تحديث القيم الجديدة
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
    return user_id == ADMIN_ID  # فقط المستخدم المحدد هو المدير

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
    except Exception:
        return False

async def start_publishing(user_id):
    """بدء عملية النشر للمستخدم"""
    if user_id in publishing_tasks:
        return  # العملية قيد التشغيل بالفعل
        
    # تحديث حالة النشر في قاعدة البيانات
    save_user_settings(user_id, publishing_active=True)
    
    async def publish_task():
        while user_id in publishing_tasks and publishing_tasks[user_id]['active']:
            try:
                # الحصول على إعدادات المستخدم
                interval, message, _ = get_user_settings(user_id)
                
                # الحصول على جلسة المستخدم
                cursor.execute("SELECT session FROM users WHERE user_id = ?", (user_id,))
                session_str = cursor.fetchone()[0]
                
                # تهيئة العميل
                client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
                await client.connect()
                
                # الحصول على المجموعات النشطة
                cursor.execute('''
                SELECT group_id, group_name FROM publishing 
                WHERE user_id = ? AND active = 1
                ''', (user_id,))
                groups = cursor.fetchall()
                
                # النشر في كل مجموعة
                for group_id, group_name in groups:
                    try:
                        await client.send_message(
                            entity=group_id,
                            message=message
                        )
                        logger.info(f"تم النشر في {group_name} ({group_id})")
                    except (ChannelPrivateError, ChatWriteForbiddenError):
                        # تحديث حالة المجموعة
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
                
                # الانتظار للفاصل الزمني
                await asyncio.sleep(interval)
                
            except Exception as e:
                logger.error(f"خطأ في مهمة النشر: {str(e)}")
                await asyncio.sleep(60)
    
    # بدء المهمة
    publishing_tasks[user_id] = {'active': True, 'task': asyncio.create_task(publish_task())}
    logger.info(f"تم تشغيل النشر للمستخدم {user_id}")

async def stop_publishing(user_id):
    """إيقاف عملية النشر للمستخدم"""
    if user_id in publishing_tasks:
        publishing_tasks[user_id]['active'] = False
        publishing_tasks[user_id]['task'].cancel()
        del publishing_tasks[user_id]
        
        # تحديث حالة النشر في قاعدة البيانات
        save_user_settings(user_id, publishing_active=False)
        logger.info(f"تم إيقاف النشر للمستخدم {user_id}")

# ===== إعداد Webhook =====
async def setup_webhook():
    """تهيئة Webhook لاستقبال التحديثات"""
    webhook_url = f"{WEBHOOK_URL}/{BOT_TOKEN}"
    await bot.start(bot_token=BOT_TOKEN)
    result = await bot(functions.bots.SetBotCommandsRequest(
        commands=[
            types.BotCommand(command='start', description='بدء استخدام البوت'),
            types.BotCommand(command='help', description='الحصول على المساعدة')
        ]
    ))
    result = await bot(functions.bots.SetBotWebhookRequest(
        url=webhook_url,
        certificate=None,
        drop_pending_updates=True
    ))
    logger.info(f"تم تعيين Webhook: {result} | URL: {webhook_url}")

# ===== معالجات الأحداث =====
@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    user_id = event.sender_id
    message = event.message
    match = re.search(r'ref-(\w+)', message.text, re.IGNORECASE)
    
    # تنظيف أي بيانات مؤقتة
    if user_id in user_data:
        try:
            client = user_data[user_id].get('client')
            if client and not client.is_connected():
                await client.disconnect()
        except:
            pass
        del user_data[user_id]
    
    # التحقق من الحظر
    if is_user_banned(user_id):
        await event.reply("❌ حسابك محظور من استخدام البوت.")
        return
    
    # تسجيل الدعوة
    if match:
        referral_code = match.group(1)
        cursor.execute('''
        UPDATE referrals SET invited_users = invited_users + 1 
        WHERE referral_code = ?
        ''', (referral_code,))
        conn.commit()
    
    # التحقق من اشتراك المستخدم في القنوات
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
    
    # التحقق من توثيق المستخدم
    if not is_user_verified(user_id):
        # التحقق من عدد الدعوات
        cursor.execute("SELECT invite_count FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        invite_count = result[0] if result else 0
        
        if invite_count < MIN_INVITES:
            # إنشاء رمز دعوة إذا لم يكن موجودًا
            cursor.execute("SELECT referral_code FROM referrals WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            referral_code = result[0] if result else generate_referral_code(user_id)
            
            if not result:
                cursor.execute('''
                INSERT INTO referrals (user_id, referral_code)
                VALUES (?, ?)
                ''', (user_id, referral_code))
                conn.commit()
            
            # إرسال رابط الدعوة
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
            # تحديث حالة المستخدم
            cursor.execute("UPDATE users SET verified = 1 WHERE user_id = ?", (user_id,))
            conn.commit()
    
    # عرض القائمة الرئيسية
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

# ... (بقية المعالجات كما هي في الكود السابق)

# ===== استعادة مهام النشر عند البدء =====
async def restore_publishing_tasks():
    cursor.execute("SELECT user_id FROM settings WHERE publishing_active = 1")
    active_users = [row[0] for row in cursor.fetchall()]
    for user_id in active_users:
        asyncio.create_task(start_publishing(user_id))
        logger.info(f"تم استعادة النشر للمستخدم: {user_id}")

# ===== تشغيل البوت مع Webhook =====
async def start_bot():
    # استعادة مهام النشر
    await restore_publishing_tasks()
    
    # تهيئة Webhook
    await setup_webhook()
    
    # إنشاء خادم Webhook
    app = web.Application()
    app.router.add_post(f'/{BOT_TOKEN}', bot._handle_webhook)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    
    logger.info(f"Bot is running with Webhook on port {PORT}")
    
    # إبقاء البوت نشطاً
    while True:
        await asyncio.sleep(3600)  # النوم لمدة ساعة

# ===== نقطة الدخول الرئيسية =====
if __name__ == '__main__':
    # تشغيل البوت في الخلفية
    def run_bot():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(start_bot())
        loop.run_forever()

    threading.Thread(target=run_bot, daemon=True).start()
    
    # خادم ويب بسيط لإبقاء التطبيق نشطاً
    from flask import Flask, jsonify
    flask_app = Flask(__name__)
    
    @flask_app.route('/')
    def home():
        return jsonify(status="running", uptime=time.time() - start_time)
    
    start_time = time.time()
    flask_app.run(host='0.0.0.0', port=5000)
