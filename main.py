import telebot
import google.generativeai as genai
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# تكوين التوكنات والمفاتيح
TOKEN = "8299954739:AAHlkfRH4N0cDjv-IToJkXQwwIqYCtzcVCQ"
GEMINI_API_KEY = "AIzaSyAEULfP5zi5irv4yRhFugmdsjBoLk7kGsE"
ADMIN_ID = 7251748706
MANDATORY_CHANNELS = ["@crazys7", "@AWU87"]  # القنوات الإجبارية

# تهيئة الذكاء الاصطناعي Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-pro')

# إنشاء البوت
bot = telebot.TeleBot(TOKEN)

# تخزين مؤقت لحالة المشتركين
subscribed_users = set()

# وظيفة للتحقق من الاشتراك في القنوات
def check_subscription(user_id):
    try:
        for channel in MANDATORY_CHANNELS:
            member = bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                return False
        return True
    except Exception as e:
        print(f"Error checking subscription: {e}")
        return False

# إنشاء لوحة مفاتيح للاشتراك الإجباري
def subscription_keyboard():
    markup = InlineKeyboardMarkup()
    for channel in MANDATORY_CHANNELS:
        markup.add(InlineKeyboardButton(f"اشترك في {channel}", url=f"https://t.me/{channel[1:]}"))
    markup.add(InlineKeyboardButton("✅ تأكيد الاشتراك", callback_data="check_subscription"))
    return markup

# معالجة أمر /start
@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    if check_subscription(user_id):
        bot.reply_to(message, "مرحباً! أنا بوت الذكاء الاصطناعي المشابه لـ ChatGPT.\nاطرح علي أي سؤال وسأجيبك بذكاء!")
        subscribed_users.add(user_id)
        bot.send_message(ADMIN_ID, f"✅ مستخدم جديد انضم:\nID: {user_id}\nUsername: @{message.from_user.username}")
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
        bot.send_message(ADMIN_ID, f"✅ مستخدم جديد أكد الاشتراك:\nID: {user_id}\nUsername: @{call.from_user.username}")
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
    
    # توليد الرد باستخدام Gemini
    try:
        response = model.generate_content(message.text)
        bot.reply_to(message, response.text)
    except Exception as e:
        bot.reply_to(message, f"❌ حدث خطأ: {str(e)}")

# تشغيل البوت
print("Bot is running...")
bot.polling()
