import os
import logging
from dotenv import load_dotenv
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError

# تحميل المتغيرات من .env
load_dotenv()

# تهيئة السجلات
logging.basicConfig(format='[%(levelname)s] %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# تهيئة البوت
bot = TelegramClient(
    session='bot_session',
    api_id=int(os.getenv('23656977')),
    api_hash=os.getenv('49d3f43531a92b3f5bc403766313ca1e')
).start(bot_token=os.getenv('7966976239:AAHyzY1KwJBWdVncELgl-O9VMFZoav6smZM'))

# تخزين بيانات المستخدم المؤقتة
user_data = {}

# زر لوحة المفاتيح
keyboard = [[Button.inline("تسجيل الدخول", b"login")]]

@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    """معالجة أمر /start"""
    await event.reply(
        "مرحباً! أنا بوت إنشاء جلسات التلجرام.",
        buttons=keyboard
    )

@bot.on(events.CallbackQuery(data=b"login"))
async def login_handler(event):
    """بدء عملية تسجيل الدخول"""
    user_id = event.sender_id
    user_data[user_id] = {'step': 'phone'}
    
    await event.edit("أرسل رقم هاتفك مع رمز الدولة (مثال: +20123456789):")

@bot.on(events.NewMessage)
async def handle_messages(event):
    """معالجة خطوات تسجيل الدخول"""
    user_id = event.sender_id
    data = user_data.get(user_id, {})
    
    if data.get('step') == 'phone':
        # حفظ رقم الهاتف والمضي قدماً
        phone = event.text.strip()
        user_data[user_id] = {
            'step': 'code',
            'phone': phone
        }
        
        # إرسال طلب الكود
        client = TelegramClient(StringSession(), api_id, api_hash)
        await client.connect()
        sent_code = await client.send_code_request(phone)
        
        user_data[user_id]['client'] = client
        user_data[user_id]['phone_code_hash'] = sent_code.phone_code_hash
        
        await event.reply("تم إرسال كود التحقق. أرسله الآن:")
    
    elif data.get('step') == 'code':
        # معالجة كود التحقق
        code = event.text.strip()
        client = data['client']
        phone = data['phone']
        phone_code_hash = data['phone_code_hash']
        
        try:
            # محاولة تسجيل الدخول
            await client.sign_in(
                phone=phone,
                code=code,
                phone_code_hash=phone_code_hash
            )
            
            # الحصول على جلسة المستخدم
            session_str = client.session.save()
            await client.disconnect()
            
            # إرسال الجلسة للمستخدم
            await event.reply(f"✅ تسجيل الدخول ناجح!\n\nجلسة حسابك:\n`{session_str}`")
            
            # حذف البيانات المؤقتة
            del user_data[user_id]
            
        except SessionPasswordNeededError:
            user_data[user_id]['step'] = 'password'
            await event.reply("حسابك محمي بكلمة سر. أرسلها الآن:")
        
        except Exception as e:
            await event.reply(f"❌ خطأ: {str(e)}")
            del user_data[user_id]
    
    elif data.get('step') == 'password':
        # معالجة كلمة السر الثانية
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
            del user_data[user_id]

if __name__ == '__main__':
    logger.info("تم تشغيل البوت!")
    bot.run_until_disconnected()
