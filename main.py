import os
import logging
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, PhoneCodeExpiredError

# تحميل متغيرات البيئة
load_dotenv()

# تهيئة الإعدادات
API_ID = int(os.getenv('API_ID', 23656977))
API_HASH = os.getenv('API_HASH', '49d3f43531a92b3f5bc403766313ca1e')
BOT_TOKEN = os.getenv('BOT_TOKEN', '7966976239:AAHyzY1KwJBWdVncELgl-O9VMFZoav6smZM')
TIMEOUT = 120  # 120 ثانية = دقيقتين

# تهيئة السجلات
logging.basicConfig(
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# تخزين بيانات المستخدم المؤقتة
user_data = {}

# بدء البوت
bot = TelegramClient(
    session='bot_session',
    api_id=API_ID,
    api_hash=API_HASH
).start(bot_token=BOT_TOKEN)

# زر لوحة المفاتيح
keyboard = [[Button.inline("تسجيل الدخول", b"login")]]

async def send_reminder(user_id):
    """إرسال تذكير للمستخدم قبل انتهاء المهلة"""
    await asyncio.sleep(TIMEOUT - 30)  # تذكير بعد 90 ثانية (30 ثانية قبل النهاية)
    
    if user_id in user_data and user_data[user_id].get('step') == 'code':
        try:
            await bot.send_message(
                user_id,
                "⏳ المهلة المتبقية: 30 ثانية فقط! أرسل كود التحقق الآن."
            )
        except Exception:
            logger.warning(f"فشل إرسال تذكير للمستخدم {user_id}")

async def handle_timeout(user_id):
    """معالجة انتهاء المهلة الزمنية"""
    await asyncio.sleep(TIMEOUT)
    
    if user_id in user_data and user_data[user_id].get('step') == 'code':
        try:
            client = user_data[user_id]['client']
            await client.disconnect()
            await bot.send_message(
                user_id,
                "⌛ انتهت المهلة (2 دقيقة). يرجى البدء من جديد باستخدام /start"
            )
            del user_data[user_id]
            logger.info(f"انتهت مهلة المستخدم {user_id}")
        except Exception as e:
            logger.error(f"خطأ في معالجة المهلة: {str(e)}")

@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    await event.reply(
        "مرحباً! أنا بوت إنشاء جلسات التلجرام.",
        buttons=keyboard
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
    
    # معالجة رقم الهاتف
    if data.get('step') == 'phone':
        phone = event.text.strip()
        try:
            client = TelegramClient(StringSession(), API_ID, API_HASH)
            await client.connect()
            sent_code = await client.send_code_request(phone)
            
            user_data[user_id] = {
                'step': 'code',
                'phone': phone,
                'client': client,
                'phone_code_hash': sent_code.phone_code_hash,
                'start_time': datetime.now()
            }
            
            # بدء مؤقتات التذكير والمهلة
            asyncio.create_task(send_reminder(user_id))
            asyncio.create_task(handle_timeout(user_id))
            
            await event.reply(
                f"📩 تم إرسال كود التحقق. لديك دقيقتان (120 ثانية) لإدخاله.\n"
                f"⏱ المهلة تنتهي في: {(datetime.now() + timedelta(seconds=TIMEOUT)).strftime('%H:%M:%S')}"
            )
        except Exception as e:
            await event.reply(f"❌ خطأ: {str(e)}")
            if user_id in user_data:
                del user_data[user_id]
    
    # معالجة كود التحقق
    elif data.get('step') == 'code':
        code = event.text.strip()
        client = data['client']
        phone = data['phone']
        phone_code_hash = data['phone_code_hash']
        
        try:
            # حساب الوقت المنقضي
            elapsed = (datetime.now() - data['start_time']).total_seconds()
            remaining = TIMEOUT - elapsed
            
            if remaining <= 0:
                await event.reply("⌛ انتهت المهلة! يرجى البدء من جديد باستخدام /start")
                await client.disconnect()
                del user_data[user_id]
                return
                
            # محاولة تسجيل الدخول
            await client.sign_in(
                phone=phone,
                code=code,
                phone_code_hash=phone_code_hash
            )
            
            # الحصول على الجلسة وإرسالها
            session_str = client.session.save()
            await client.disconnect()
            await event.reply(
                f"✅ تسجيل الدخول ناجح!\n\n"
                f"⏱ الوقت المستغرق: {elapsed:.1f} ثانية\n"
                f"🔑 جلسة حسابك:\n`{session_str}`"
            )
            del user_data[user_id]
            
        except PhoneCodeExpiredError:
            await event.reply("❌ انتهت صلاحية الكود! يرجى البدء من جديد باستخدام /start")
            await client.disconnect()
            del user_data[user_id]
            
        except SessionPasswordNeededError:
            user_data[user_id]['step'] = 'password'
            await event.reply("🔒 حسابك محمي بكلمة سر. أرسلها الآن:")
            
        except Exception as e:
            await event.reply(f"❌ خطأ: {str(e)}")
            try:
                await client.disconnect()
            except:
                pass
            if user_id in user_data:
                del user_data[user_id]
    
    # معالجة كلمة السر
    elif data.get('step') == 'password':
        password = event.text
        client = data['client']
        
        try:
            await client.sign_in(password=password)
            session_str = client.session.save()
            await client.disconnect()
            await event.reply(f"✅ تسجيل الدخول ناجح!\n\nجلسة حسابك:\n`{session_str}`")
            del user_data[user_id]
        except Exception as e:
            await event.reply(f"❌ خطأ في كلمة السر: {str(e)}")
            try:
                await client.disconnect()
            except:
                pass
            if user_id in user_data:
                del user_data[user_id]

if __name__ == '__main__':
    logger.info(f"تم تشغيل البوت | API_ID: {API_ID} | المهلة: {TIMEOUT} ثانية")
    bot.run_until_disconnected()
