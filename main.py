import telebot
import requests
import json
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask, request
import threading
import time

# تكوين التوكنات والمفاتيح
TOKEN = "8299954739:AAHlkfRH4N0cDjv-IToJkXQwwIqYCtzcVCQ"
ADMIN_ID = 7251748706
MANDATORY_CHANNELS = ["@crazys7", "@AWU87"]
WEBHOOK_URL = "https://pixai7.onrender.com/" + TOKEN
GROQ_API_KEY = "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"  # استبدل بمفتاح Groq الخاص بك

# إنشاء البوت
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# تخزين مؤقت لحالة المشتركين
subscribed_users = set()

# وظيفة للحفاظ على تشغيل الخادم
def keep_alive():
    while True:
        time.sleep(300)
        try:
            requests.get(WEBHOOK_URL)
        except: 
            pass

# وظيفة للتحقق من الاشتراك في القنوات
def check_subscription(user_id):
    try:
        for channel in MANDATORY_CHANNELS:
            member = bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                return False
        return True
    except Exception as e:
        print(f"خطأ في التحقق من الاشتراك: {e}")
        return False

# إنشاء لوحة مفاتيح للاشتراك الإجباري
def subscription_keyboard():
    markup = InlineKeyboardMarkup()
    for channel in MANDATORY_CHANNELS:
        markup.add(InlineKeyboardButton(f"اشترك في {channel}", url=f"https://t.me/{channel[1:]}"))
    markup.add(InlineKeyboardButton("✅ تأكيد الاشتراك", callback_data="check_subscription"))
    return markup

# وظيفة الذكاء الاصطناعي باستخدام Llama 3
def get_ai_response(prompt):
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "messages": [
            {"role": "system", "content": "أنت مساعد ذكي يتحدث العربية بطلاقة."},
            {"role": "user", "content": prompt}
        ],
        "model": "llama3-70b-8192",
        "temperature": 0.7,
        "max_tokens": 2000,
        "top_p": 1,
        "stream": False
    }
    
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )
        
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        else:
            return f"❌ خطأ في API: {response.status_code} - {response.text}"
            
    except Exception as e:
        return f"❌ خطأ في الاتصال: {str(e)}"

# معالجة أمر /start
@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    if check_subscription(user_id):
        bot.reply_to(message, "مرحباً! أنا بوت الذكاء الاصطناعي المشابه لـ ChatGPT.\nاطرح علي أي سؤال وسأجيبك بذكاء!")
        subscribed_users.add(user_id)
        bot.send_message(ADMIN_ID, f"✅ مستخدم جديد انضم:\nID: {user_id}\nالمستخدم: @{message.from_user.username}")
    else:
        bot.send_message(
            message.chat.id,
            "📢 يجب الاشتراك في القنوات التالية أولاً:",
            reply_markup=subscription_keyboard()
        )

# معالجة التأكيد الاشتراك
@bot.callback_query_handler(func=lambda call: call.data == "check_subscription")
def check_subscription_callback(call):
    user_id = call.from_user.id
    if check_subscription(user_id):
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="✅ تم التأكيد! يمكنك الآن استخدام البوت."
        )
        subscribed_users.add(user_id)
        bot.send_message(ADMIN_ID, f"✅ مستخدم جديد أكد الاشتراك:\nID: {user_id}\nالمستخدم: @{call.from_user.username}")
    else:
        bot.answer_callback_query(call.id, "❌ لم تشترك في جميع القنوات المطلوبة!", show_alert=True)

# معالجة الرسائل النصية
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id
    
    # التحقق من الاشتراك
    if user_id not in subscribed_users:
        if check_subscription(user_id):
            subscribed_users.add(user_id)
        else:
            bot.send_message(
                message.chat.id,
                "⛔ يجب عليك الاشتراك في القنوات أولاً:",
                reply_markup=subscription_keyboard()
            )
            return
    
    # إظهار أن البوت يكتب
    bot.send_chat_action(message.chat.id, 'typing')
    
    # الحصول على الرد من الذكاء الاصطناعي
    response = get_ai_response(message.text)
    bot.reply_to(message, response)

# تهيئة ويب هووك
@app.route('/' + TOKEN, methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    return 'Invalid content type', 403

@app.route('/')
def index():
    return '🤖 البوت يعمل بنجاح!', 200

# تشغيل البوت
if __name__ == '__main__':
    # إزالة ويب هووكات السابقة
    bot.remove_webhook()
    time.sleep(1)
    
    # تعيين ويب هووك جديد
    bot.set_webhook(url=WEBHOOK_URL)
    
    # بدء تشغيل خادم الحفاظ على النشاط
    threading.Thread(target=keep_alive).start()
    
    # بدء تشغيل الخادم
    app.run(host='0.0.0.0', port=8080)
