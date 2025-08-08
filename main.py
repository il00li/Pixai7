import telebot
import sqlite3
import time
import threading
from datetime import datetime, timedelta
import google.generativeai as genai
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# إعدادات الذكاء الاصطناعي
genai.configure(api_key='AIzaSyAEULfP5zi5irv4yRhFugmdsjBoLk7kGsE')
model = genai.GenerativeModel('gemini-pro')

# توكن البوت
TOKEN = '8312137482:AAEORpBnD8CmFfB39ayJT4UputPoSh_qCRw'
bot = telebot.TeleBot(TOKEN)

# إعدادات المدير
ADMIN_ID = 8419586314
DEVELOPER_INFO = """
مطور مبتدئ في عالم بوتات تيليجرام، بدأ رحلته بشغف كبير لتعلم البرمجة وصناعة أدوات ذكية تساعد المستخدمين وتضيف قيمة للمجتمعات الرقمية. يسعى لتطوير مهاراته يومًا بعد يوم من خلال التجربة، التعلم، والمشاركة في مشاريع بسيطة لكنها فعالة.

ما يميزه في هذه المرحلة:
- حب الاستكشاف والتعلم الذاتي
- بناء بوتات بسيطة بمهام محددة
- استخدام أدوات مثل BotFather و Python
- الانفتاح على النقد والتطوير المستمر

القنوات المرتبطة:
@crazys7 - @AWU87

رؤية المطور:
الانطلاق من الأساسيات نحو الاحتراف، خطوة بخطوة، مع طموح لصناعة بوتات تلبي احتياجات حقيقية وتحدث فرقًا.

للتواصل:
تابع الحساب @Ili8_8ill
"""

# إعداد قاعدة البيانات
conn = sqlite3.connect('bot_db.sqlite', check_same_thread=False)
c = conn.cursor()

# إنشاء الجداول
c.execute('''CREATE TABLE IF NOT EXISTS mandatory_channels (
             channel_id TEXT PRIMARY KEY)''')

c.execute('''CREATE TABLE IF NOT EXISTS users (
             user_id INTEGER PRIMARY KEY,
             username TEXT,
             invite_count INTEGER DEFAULT 0,
             is_banned BOOLEAN DEFAULT 0)''')

c.execute('''CREATE TABLE IF NOT EXISTS channels (
             channel_id TEXT PRIMARY KEY,
             owner_id INTEGER,
             frequency INTEGER,
             is_active BOOLEAN DEFAULT 0,
             next_post_time DATETIME,
             FOREIGN KEY(owner_id) REFERENCES users(user_id))''')

c.execute('''CREATE TABLE IF NOT EXISTS invites (
             code TEXT PRIMARY KEY,
             creator_id INTEGER,
             used_count INTEGER DEFAULT 0)''')

conn.commit()

# وظيفة مساعدة للتحقق من الاشتراك
def check_subscription(user_id):
    c.execute("SELECT channel_id FROM mandatory_channels")
    mandatory_channels = c.fetchall()
    
    for channel in mandatory_channels:
        try:
            chat_member = bot.get_chat_member(channel[0], user_id)
            if chat_member.status not in ['member', 'administrator', 'creator']:
                return False
        except Exception as e:
            print(f"Error checking subscription: {e}")
            return False
    return True

# وظيفة إنشاء رابط دعوة
def generate_invite_link(user_id):
    code = f"INV_{user_id}_{int(time.time())}"
    c.execute("INSERT OR REPLACE INTO invites (code, creator_id) VALUES (?, ?)", (code, user_id))
    conn.commit()
    return f"https://t.me/{(bot.get_me()).username}?start={code}"

# وظيفة إنشاء محتوى باستخدام الذكاء الاصطناعي
def generate_ai_content():
    try:
        response = model.generate_content("أنشئ محتوى عشوائي مناسب لقناة تليجرام")
        return response.text
    except Exception as e:
        print(f"AI Error: {e}")
        return "محتوى تجريبي للنشر 🚀"

# وظيفة النشر التلقائي
def auto_posting():
    while True:
        try:
            now = datetime.now()
            c.execute("SELECT channel_id, frequency FROM channels WHERE is_active = 1 AND next_post_time <= ?", (now,))
            channels = c.fetchall()
            
            for channel in channels:
                content = generate_ai_content()
                try:
                    bot.send_message(channel[0], content)
                    
                    # تحديث وقت النشر التالي
                    next_time = now + timedelta(hours=channel[1])
                    c.execute("UPDATE channels SET next_post_time = ? WHERE channel_id = ?", (next_time, channel[0]))
                    conn.commit()
                except Exception as e:
                    print(f"Error posting to channel: {e}")
                    # تعطيل القناة إذا كانت هناك مشكلة
                    c.execute("UPDATE channels SET is_active = 0 WHERE channel_id = ?", (channel[0],))
                    conn.commit()
            
            time.sleep(60)  # التحقق كل دقيقة
        except Exception as e:
            print(f"Auto-posting error: {e}")
            time.sleep(300)

# بدء خلفية النشر التلقائي
thread = threading.Thread(target=auto_posting)
thread.daemon = True
thread.start()

# لوحة المفاتيح الرئيسية
def main_keyboard(user_id):
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    c.execute("SELECT COUNT(*) FROM channels WHERE owner_id = ?", (user_id,))
    channel_count = c.fetchone()[0]
    
    # التحقق من عضوية VIP
    c.execute("SELECT invite_count FROM users WHERE user_id = ?", (user_id,))
    invite_count = c.fetchone()[0] if c.fetchone() else 0
    
    if channel_count == 0 or invite_count >= 5:
        keyboard.add(InlineKeyboardButton("اضف قناتك🧚", callback_data="add_channel"))
    
    c.execute("SELECT is_active FROM channels WHERE owner_id = ?", (user_id,))
    active_status = "🟢" if any(row[0] for row in c.fetchall()) else "🔴"
    
    keyboard.add(
        InlineKeyboardButton(f"تفعيل النشر {active_status}", callback_data="toggle_posting"),
        InlineKeyboardButton("احصائيات🐾", callback_data="stats"),
        InlineKeyboardButton("المطور </>", callback_data="developer")
    )
    return keyboard

# معالج البداية
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    args = message.text.split()[1] if len(message.text.split()) > 1 else None
    
    # التحقق من رابط الدعوة
    if args and args.startswith('INV_'):
        c.execute("SELECT creator_id FROM invites WHERE code = ?", (args,))
        invite_data = c.fetchone()
        if invite_data:
            creator_id = invite_data[0]
            c.execute("UPDATE users SET invite_count = invite_count + 1 WHERE user_id = ?", (creator_id,))
            c.execute("UPDATE invites SET used_count = used_count + 1 WHERE code = ?", (args,))
            conn.commit()
    
    # تسجيل المستخدم
    c.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", 
              (user_id, message.from_user.username))
    conn.commit()
    
    # التحقق من الاشتراك
    if not check_subscription(user_id):
        c.execute("SELECT channel_id FROM mandatory_channels")
        channels = [row[0] for row in c.fetchall()]
        
        if channels:
            keyboard = InlineKeyboardMarkup()
            for channel in channels:
                keyboard.add(InlineKeyboardButton(f"انضم {channel}", url=f"https://t.me/{channel}"))
            keyboard.add(InlineKeyboardButton("تم الاشتراك ✅", callback_data="check_subscription"))
            
            bot.send_message(user_id, "يجب الاشتراك في القنوات التالية أولاً:", reply_markup=keyboard)
            return
    
    # عرض القائمة الرئيسية
    bot.send_message(user_id, "مرحباً! اختر أحد الخيارات:", reply_markup=main_keyboard(user_id))

# معالج الأزرار
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    data = call.data
    
    if data == "check_subscription":
        if check_subscription(user_id):
            bot.edit_message_text("تم التحقق بنجاح! اختر أحد الخيارات:", 
                                  user_id, 
                                  call.message.message_id, 
                                  reply_markup=main_keyboard(user_id))
        else:
            bot.answer_callback_query(call.id, "لم تكتمل الاشتراكات بعد!", show_alert=True)
    
    elif data == "add_channel":
        # التحقق من عدد القنوات
        c.execute("SELECT COUNT(*) FROM channels WHERE owner_id = ?", (user_id,))
        channel_count = c.fetchone()[0]
        
        # التحقق من عضوية VIP للإضافة الثانية
        if channel_count >= 1:
            c.execute("SELECT invite_count FROM users WHERE user_id = ?", (user_id,))
            invite_count = c.fetchone()[0]
            
            if invite_count < 5:
                keyboard = InlineKeyboardMarkup()
                keyboard.add(InlineKeyboardButton("إنشاء رابط دعوة", callback_data="create_invite"))
                keyboard.add(InlineKeyboardButton("اتصل بالمدير", url=f"tg://user?id={ADMIN_ID}"))
                
                bot.edit_message_text("لإضافة قناة أخرى، يجب دعوة 5 أعضاء:\n\n"
                                     f"دعواتك الحالية: {invite_count}/5",
                                     user_id,
                                     call.message.message_id,
                                     reply_markup=keyboard)
                return
        
        # بدء إضافة القناة
        msg = bot.edit_message_text("أرسل معرف القناة (مثل @channel_name):", 
                                   user_id, 
                                   call.message.message_id)
        bot.register_next_step_handler(msg, process_channel_name)

    elif data == "create_invite":
        invite_link = generate_invite_link(user_id)
        bot.edit_message_text(f"رابط الدعوة الخاص بك:\n\n{invite_link}\n\n"
                             "شارك هذا الرابط مع أصدقائك، سيتم احتساب الدعوة بعد اشتراكهم في القنوات الإجبارية.",
                             user_id,
                             call.message.message_id,
                             reply_markup=InlineKeyboardMarkup().add(
                                 InlineKeyboardButton("العودة", callback_data="back_to_main")))

    elif data == "toggle_posting":
        c.execute("SELECT channel_id, is_active FROM channels WHERE owner_id = ?", (user_id,))
        channels = c.fetchall()
        
        if not channels:
            bot.answer_callback_query(call.id, "ليس لديك قنوات مفعلة!", show_alert=True)
            return
        
        keyboard = InlineKeyboardMarkup()
        for channel_id, is_active in channels:
            status = "🟢" if is_active else "🔴"
            keyboard.add(InlineKeyboardButton(f"{channel_id} {status}", 
                                            callback_data=f"toggle_{channel_id}"))
        
        keyboard.add(InlineKeyboardButton("العودة", callback_data="back_to_main"))
        bot.edit_message_text("اختر القناة لتغيير حالة النشر:",
                             user_id,
                             call.message.message_id,
                             reply_markup=keyboard)

    elif data.startswith("toggle_"):
        channel_id = data[7:]
        c.execute("SELECT is_active FROM channels WHERE channel_id = ?", (channel_id,))
        is_active = not c.fetchone()[0]
        
        c.execute("UPDATE channels SET is_active = ? WHERE channel_id = ?", (is_active, channel_id))
        conn.commit()
        
        # تحديث الزر في الرسالة
        callback_handler(call)

    elif data == "stats":
        c.execute("SELECT COUNT(*) FROM channels WHERE owner_id = ?", (user_id,))
        channel_count = c.fetchone()[0]
        
        c.execute("SELECT invite_count FROM users WHERE user_id = ?", (user_id,))
        invite_count = c.fetchone()[0]
        
        active_channels = []
        c.execute("SELECT channel_id FROM channels WHERE owner_id = ? AND is_active = 1", (user_id,))
        for row in c.fetchall():
            active_channels.append(row[0])
        
        stats_text = (
            f"📊 احصائياتك:\n\n"
            f"• عدد القنوات: {channel_count}\n"
            f"• القنوات النشطة: {', '.join(active_channels) if active_channels else 'لا يوجد'}\n"
            f"• عدد الدعوات: {invite_count}\n"
            f"• القنوات المطلوبة للإضافة التالية: {max(0, 5 - invite_count)}"
        )
        
        bot.edit_message_text(stats_text,
                            user_id,
                            call.message.message_id,
                            reply_markup=InlineKeyboardMarkup().add(
                                InlineKeyboardButton("العودة", callback_data="back_to_main")))

    elif data == "developer":
        bot.edit_message_text(DEVELOPER_INFO,
                            user_id,
                            call.message.message_id,
                            reply_markup=InlineKeyboardMarkup().add(
                                InlineKeyboardButton("العودة", callback_data="back_to_main")))

    elif data == "back_to_main":
        bot.edit_message_text("اختر أحد الخيارات:",
                            user_id,
                            call.message.message_id,
                            reply_markup=main_keyboard(user_id))

# معالج إضافة القناة
def process_channel_name(message):
    user_id = message.from_user.id
    channel_id = message.text.strip().replace('@', '')
    
    # التحقق من صحة القناة
    try:
        chat = bot.get_chat(f"@{channel_id}")
        if chat.type not in ['channel', 'supergroup']:
            bot.send_message(user_id, "هذا ليس معرف قناة صالح!")
            return
    except:
        bot.send_message(user_id, "تعذر العثور على القناة! تأكد من إضافة البوت كمسؤول.")
        return
    
    # التحقق من ملكية القناة
    try:
        admins = bot.get_chat_administrators(f"@{channel_id}")
        if not any(admin.user.id == user_id for admin in admins):
            bot.send_message(user_id, "يجب أن تكون مسؤولاً في القناة لإضافتها!")
            return
    except:
        bot.send_message(user_id, "تعذر التحقق من الصلاحيات! تأكد من إضافة البوت كمسؤول.")
        return
    
    # حفظ القناة مؤقتاً
    bot.send_message(user_id, "تم التحقق من القناة بنجاح!")
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("كل 12 ساعة", callback_data=f"freq_{channel_id}_12"),
        InlineKeyboardButton("كل 24 ساعة", callback_data=f"freq_{channel_id}_24")
    )
    bot.send_message(user_id, "اختر فترة النشر:", reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data.startswith('freq_'))
def set_frequency(call):
    user_id = call.from_user.id
    _, channel_id, frequency = call.data.split('_')
    frequency = int(frequency)
    
    # إضافة القناة إلى قاعدة البيانات
    next_post_time = datetime.now() + timedelta(hours=frequency)
    c.execute("INSERT OR REPLACE INTO channels (channel_id, owner_id, frequency, next_post_time) VALUES (?, ?, ?, ?)",
              (channel_id, user_id, frequency, next_post_time))
    conn.commit()
    
    bot.edit_message_text(f"تم إضافة القناة @{channel_id} بنجاح!",
                         user_id,
                         call.message.message_id,
                         reply_markup=InlineKeyboardMarkup().add(
                             InlineKeyboardButton("العودة", callback_data="back_to_main")))

# لوحة تحكم المدير
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("إدارة القنوات الإجبارية", callback_data="manage_mandatory"),
        InlineKeyboardButton("إدارة المستخدمين", callback_data="manage_users"),
        InlineKeyboardButton("حظر مستخدم", callback_data="ban_user"),
        InlineKeyboardButton("إلغاء حظر مستخدم", callback_data="unban_user")
    )
    bot.send_message(ADMIN_ID, "لوحة تحكم المدير:", reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data.startswith('manage_'))
def admin_actions(call):
    if call.from_user.id != ADMIN_ID:
        return
    
    action = call.data.split('_')[1]
    
    if action == "mandatory":
        keyboard = InlineKeyboardMarkup()
        c.execute("SELECT channel_id FROM mandatory_channels")
        channels = c.fetchall()
        
        for channel in channels:
            keyboard.add(InlineKeyboardButton(f"حذف {channel[0]}", callback_data=f"del_mandatory_{channel[0]}"))
        
        keyboard.add(InlineKeyboardButton("إضافة قناة", callback_data="add_mandatory"))
        keyboard.add(InlineKeyboardButton("إغلاق", callback_data="close_admin"))
        
        bot.edit_message_text("القنوات الإجبارية الحالية:",
                             ADMIN_ID,
                             call.message.message_id,
                             reply_markup=keyboard)
    
    elif action == "users":
        # عرض إحصائيات المستخدمين
        c.execute("SELECT COUNT(*) FROM users")
        total_users = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")
        banned_users = c.fetchone()[0]
        
        bot.edit_message_text(f"إحصائيات المستخدمين:\n\n"
                             f"• إجمالي المستخدمين: {total_users}\n"
                             f"• المستخدمين المحظورين: {banned_users}",
                             ADMIN_ID,
                             call.message.message_id,
                             reply_markup=InlineKeyboardMarkup().add(
                                 InlineKeyboardButton("العودة", callback_data="back_to_admin")))

@bot.callback_query_handler(func=lambda call: call.data == "add_mandatory")
def add_mandatory_channel(call):
    msg = bot.send_message(ADMIN_ID, "أرسل معرف القناة الإجبارية (مثل @channel_name):")
    bot.register_next_step_handler(msg, process_mandatory_channel)

def process_mandatory_channel(message):
    channel_id = message.text.strip().replace('@', '')
    c.execute("INSERT OR IGNORE INTO mandatory_channels (channel_id) VALUES (?)", (channel_id,))
    conn.commit()
    bot.send_message(ADMIN_ID, f"تمت إضافة القناة @{channel_id} إلى القنوات الإجبارية!")

@bot.callback_query_handler(func=lambda call: call.data.startswith('del_mandatory_'))
def delete_mandatory_channel(call):
    channel_id = call.data.split('_')[2]
    c.execute("DELETE FROM mandatory_channels WHERE channel_id = ?", (channel_id,))
    conn.commit()
    bot.answer_callback_query(call.id, f"تم حذف القناة @{channel_id}!")
    admin_actions(call)  # تحديث القائمة

@bot.callback_query_handler(func=lambda call: call.data == "ban_user")
def ban_user_prompt(call):
    msg = bot.send_message(ADMIN_ID, "أرسل معرف المستخدم لحظره:")
    bot.register_next_step_handler(msg, process_ban_user)

def process_ban_user(message):
    try:
        user_id = int(message.text)
        c.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (user_id,))
        c.execute("UPDATE channels SET is_active = 0 WHERE owner_id = ?", (user_id,))
        conn.commit()
        bot.send_message(ADMIN_ID, f"تم حظر المستخدم {user_id} وإيقاف قنواته!")
    except:
        bot.send_message(ADMIN_ID, "معرف مستخدم غير صالح!")

@bot.callback_query_handler(func=lambda call: call.data == "unban_user")
def unban_user_prompt(call):
    msg = bot.send_message(ADMIN_ID, "أرسل معرف المستخدم لإلغاء حظره:")
    bot.register_next_step_handler(msg, process_unban_user)

def process_unban_user(message):
    try:
        user_id = int(message.text)
        c.execute("UPDATE users SET is_banned = 0 WHERE user_id = ?", (user_id,))
        conn.commit()
        bot.send_message(ADMIN_ID, f"تم إلغاء حظر المستخدم {user_id}!")
    except:
        bot.send_message(ADMIN_ID, "معرف مستخدم غير صالح!")

@bot.callback_query_handler(func=lambda call: call.data in ["back_to_admin", "close_admin"])
def admin_back(call):
    if call.data == "close_admin":
        bot.delete_message(ADMIN_ID, call.message.message_id)
    else:
        admin_panel(call.message)

# بدء البوت
print("تم تشغيل البوت بنجاح!")
bot.infinity_polling()
