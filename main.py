import asyncio
import logging
from datetime import datetime
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
    JobQueue
)
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
import re

# إعدادات التلجرام
TOKEN = "7966976239:AAEy5WkQDszmVbuInTnuOyUXskhyO7ak9Nc"
API_ID = 23656977
API_HASH = "49d3f43531a92b3f5bc403766313ca1e"

# حالات المحادثة
LOGIN, PHONE, CODE, ADD_SUPER, PUBLISH_INTERVAL = range(5)

# تخزين البيانات
users_data = {}
global_stats = {
    'total_publish': 0,
    'user_publish': {},
    'total_users': 0,
    'total_groups': 0
}

# إعداد التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# لوحة المفاتيح الرئيسية
def main_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("═ LOGIN | تسجيل ═", callback_data="login")
        ],
        [
            InlineKeyboardButton("بدء النشر", callback_data="start_publish"),
            InlineKeyboardButton("اضف سوبر", callback_data="add_super")
        ],
        [
            InlineKeyboardButton("مساعدة", callback_data="help"),
            InlineKeyboardButton("احصائيات", callback_data="stats")
        ]
    ])

# لوحة فترات النشر
def interval_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("2 دقائق", callback_data="2"),
            InlineKeyboardButton("5 دقائق", callback_data="5"),
            InlineKeyboardButton("10 دقائق", callback_data="10")
        ],
        [
            InlineKeyboardButton("20 دقيقة", callback_data="20"),
            InlineKeyboardButton("30 دقيقة", callback_data="30"),
            InlineKeyboardButton("60 دقيقة", callback_data="60")
        ],
        [
            InlineKeyboardButton("120 دقيقة", callback_data="120"),
            InlineKeyboardButton("رجوع", callback_data="back")
        ]
    ])

# زر الرجوع
def back_button():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("رجوع", callback_data="back")]
    ])

# بدء البوت
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_data:
        users_data[user_id] = {
            'phone': None,
            'session': None,
            'client': None,
            'groups': [],
            'publish_count': 0,
            'phone_code_hash': None
        }
        global_stats['total_users'] += 1
    
    await update.message.reply_text(
        "مرحباً! اختر أحد الخيارات:",
        reply_markup=main_keyboard()
    )

# معالجة أزرار Inline
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    
    if data == "login":
        await query.edit_message_text(
            "أرسل رقم هاتفك مع رمز الدولة (مثال: +20123456789):",
            reply_markup=back_button()
        )
        return LOGIN
    
    elif data == "add_super":
        await query.edit_message_text(
            "أرسل رابط أو معرف المجموعة (يجب أن تكون مشرفاً):",
            reply_markup=back_button()
        )
        return ADD_SUPER
    
    elif data == "start_publish":
        await query.edit_message_text(
            "اختر الفترة الزمنية بين النشرات:",
            reply_markup=interval_keyboard()
        )
        return PUBLISH_INTERVAL
    
    elif data == "help":
        help_text = (
            "❖ **مساعدة استخدام البوت**:\n\n"
            "1. تسجيل الدخول: أضف رقم هاتفك للحصول على كود التحقق\n"
            "2. إضافة سوبر: أضف المجموعات التي تريد النشر فيها\n"
            "3. بدء النشر: اختر الفترة الزمنية وابدأ النشر التلقائي\n\n"
            "✪ تحذير: لا تشارك كود التحقق مع أحد\n"
            "✪ المطور: @Ili8_8ill"
        )
        await query.edit_message_text(
            help_text,
            parse_mode="Markdown",
            reply_markup=back_button()
        )
    
    elif data == "stats":
        user_pub = users_data[user_id]['publish_count'] if user_id in users_data else 0
        stats_text = (
            f"📊 **الإحصائيات**:\n\n"
            f"• إجمالي النشر: {global_stats['total_publish']}\n"
            f"• نشراتك: {user_pub}\n"
            f"• المستخدمين: {global_stats['total_users']}\n"
            f"• المجموعات: {global_stats['total_groups']}"
        )
        await query.edit_message_text(
            stats_text,
            parse_mode="Markdown",
            reply_markup=back_button()
        )
    
    elif data == "back":
        await query.edit_message_text(
            "اختر أحد الخيارات:",
            reply_markup=main_keyboard()
        )
        return ConversationHandler.END
    
    elif data in ["2", "5", "10", "20", "30", "60", "120"]:
        interval = int(data)
        context.user_data['publish_interval'] = interval
        
        if user_id not in users_data or not users_data[user_id]['groups']:
            await query.edit_message_text(
                "⚠️ يجب إضافة مجموعات أولاً!",
                reply_markup=back_button()
            )
            return
        
        await query.edit_message_text(
            f"⏱ تم ضبط النشر كل {interval} دقيقة\n"
            "أرسل الرسالة التي تريد نشرها:",
            reply_markup=back_button()
        )
        return PUBLISH_INTERVAL

# معالجة تسجيل الدخول
async def login_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    phone = update.message.text
    
    # التحقق من صيغة الرقم
    if not re.match(r'^\+\d{8,15}$', phone):
        await update.message.reply_text(
            "❌ رقم هاتف غير صحيح. يرجى إرساله بالصيغة الصحيحة: +XXXXXXXXXXX",
            reply_markup=back_button()
        )
        return LOGIN
    
    users_data[user_id]['phone'] = phone
    
    try:
        # إعادة استخدام العميل إذا كان موجوداً
        if users_data[user_id].get('client') is None:
            client = TelegramClient(StringSession(), API_ID, API_HASH)
            users_data[user_id]['client'] = client
        else:
            client = users_data[user_id]['client']
        
        await client.connect()
        sent = await client.send_code_request(phone)
        users_data[user_id]['phone_code_hash'] = sent.phone_code_hash
        
        await update.message.reply_text(
            "تم إرسال كود التحقق. أرسله الآن (5 أرقام):",
            reply_markup=back_button()
        )
        return CODE
    
    except errors.PhoneNumberInvalidError:
        await update.message.reply_text(
            "❌ رقم الهاتف غير صحيح. يرجى المحاولة مرة أخرى:",
            reply_markup=back_button()
        )
        return LOGIN
    except errors.PhoneNumberBannedError:
        await update.message.reply_text(
            "❌ هذا الرقم محظور من قبل تيليجرام.",
            reply_markup=back_button()
        )
        return LOGIN
    except Exception as e:
        logger.error(f"Login error: {e}")
        await update.message.reply_text(
            f"❌ خطأ في تسجيل الدخول: {str(e)}",
            reply_markup=back_button()
        )
        return LOGIN

# معالجة كود التحقق
async def login_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    code = update.message.text.replace(" ", "")
    
    # التحقق من صيغة الكود
    if not code.isdigit() or len(code) != 5:
        await update.message.reply_text(
            "❌ كود التحقق يجب أن يكون 5 أرقام. أرسله مرة أخرى:",
            reply_markup=back_button()
        )
        return CODE
    
    client = users_data[user_id]['client']
    phone = users_data[user_id]['phone']
    phone_code_hash = users_data[user_id]['phone_code_hash']
    
    try:
        # تسجيل الدخول مع التعامل مع كلمة المرور الثنائية
        try:
            await client.sign_in(
                phone=phone,
                code=code,
                phone_code_hash=phone_code_hash
            )
        except errors.SessionPasswordNeededError:
            await update.message.reply_text(
                "🔐 الحساب محمي بكلمة مرور ثنائية. أرسل كلمة المرور:",
                reply_markup=back_button()
            )
            return PASSWORD
        
        session_str = client.session.save()
        users_data[user_id]['session'] = session_str
        
        await update.message.reply_text(
            "✅ تم تسجيل الدخول بنجاح!",
            reply_markup=main_keyboard()
        )
        return ConversationHandler.END
    
    except errors.PhoneCodeInvalidError:
        await update.message.reply_text(
            "❌ كود التحقق غير صحيح. أرسله مرة أخرى:",
            reply_markup=back_button()
        )
        return CODE
    except errors.PhoneCodeExpiredError:
        await update.message.reply_text(
            "❌ كود التحقق منتهي الصلاحية. يرجى إعادة عملية التسجيل.",
            reply_markup=main_keyboard()
        )
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Verification error: {e}")
        await update.message.reply_text(
            f"❌ خطأ في التحقق: {str(e)}",
            reply_markup=back_button()
        )
        return CODE

# معالجة كلمة المرور الثنائية
async def two_step_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    password = update.message.text
    client = users_data[user_id]['client']
    
    try:
        await client.sign_in(password=password)
        session_str = client.session.save()
        users_data[user_id]['session'] = session_str
        
        await update.message.reply_text(
            "✅ تم تسجيل الدخول بنجاح!",
            reply_markup=main_keyboard()
        )
        return ConversationHandler.END
    
    except errors.PasswordHashInvalidError:
        await update.message.reply_text(
            "❌ كلمة المرور غير صحيحة. أرسلها مرة أخرى:",
            reply_markup=back_button()
        )
        return PASSWORD
    except Exception as e:
        logger.error(f"Password error: {e}")
        await update.message.reply_text(
            f"❌ خطأ في التحقق: {str(e)}",
            reply_markup=back_button()
        )
        return PASSWORD

# إضافة مجموعة للنشر
async def add_supergroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    group_identifier = update.message.text
    
    if group_identifier.startswith("https://t.me/"):
        group_identifier = group_identifier.split("/")[-1]
    
    # إضافة المجموعة فقط إذا لم تكن موجودة
    if group_identifier not in users_data[user_id]['groups']:
        users_data[user_id]['groups'].append(group_identifier)
        global_stats['total_groups'] += 1
    
    await update.message.reply_text(
        f"✅ تمت إضافة/تحديث المجموعة: {group_identifier}\n"
        "يمكنك إضافة المزيد أو الرجوع للقائمة الرئيسية",
        reply_markup=back_button()
    )
    return ADD_SUPER

# بدء النشر التلقائي
async def start_publishing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    message_text = update.message.text
    interval = context.user_data['publish_interval']
    
    # إيقاف أي نشر سابق لنفس المستخدم
    current_jobs = context.job_queue.get_jobs_by_name(str(user_id))
    for job in current_jobs:
        job.schedule_removal()
    
    # بدء النشر الجديد
    context.job_queue.run_repeating(
        publish_message,
        interval * 60,
        first=0,
        user_id=user_id,
        data=message_text,
        name=str(user_id)
    )
    
    await update.message.reply_text(
        f"🚀 بدأ النشر كل {interval} دقيقة!\n"
        "لإيقاف النشر: /stop",
        reply_markup=main_keyboard()
    )
    return ConversationHandler.END

# وظيفة النشر الفعلية
async def publish_message(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    user_id = job.user_id
    message_text = job.data
    
    if user_id not in users_data or not users_data[user_id]['session']:
        return
    
    try:
        client = TelegramClient(
            StringSession(users_data[user_id]['session']),
            API_ID,
            API_HASH
        )
        await client.connect()
        
        for group in users_data[user_id]['groups']:
            try:
                await client.send_message(group, message_text)
                users_data[user_id]['publish_count'] += 1
                global_stats['total_publish'] += 1
                await asyncio.sleep(10)  # زيادة التأخير بين المجموعات
            except Exception as e:
                logger.error(f"Publish error in {group}: {e}")
        
        await client.disconnect()
    
    except Exception as e:
        logger.error(f"Client error: {e}")

# إيقاف النشر
async def stop_publishing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    current_jobs = context.job_queue.get_jobs_by_name(str(user_id))
    
    if current_jobs:
        for job in current_jobs:
            job.schedule_removal()
        await update.message.reply_text("⏹ تم إيقاف النشر التلقائي.")
    else:
        await update.message.reply_text("ℹ️ لا يوجد نشر نشط لإيقافه.")

# إلغاء المحادثة
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "تم الإلغاء.",
        reply_markup=main_keyboard()
    )
    return ConversationHandler.END

# الدالة الرئيسية
def main():
    application = Application.builder().token(TOKEN).build()
    
    # محادثة تسجيل الدخول
    login_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern="^login$")],
        states={
            LOGIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_phone)],
            CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_code)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, two_step_password)]
        },
        fallbacks=[CallbackQueryHandler(button_handler, pattern="^back$")]
    )
    
    # محادثة إضافة مجموعات
    super_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern="^add_super$")],
        states={
            ADD_SUPER: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_supergroup)]
        },
        fallbacks=[CallbackQueryHandler(button_handler, pattern="^back$")]
    )
    
    # محادثة بدء النشر
    publish_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern="^start_publish$")],
        states={
            PUBLISH_INTERVAL: [
                CallbackQueryHandler(button_handler, pattern="^\d+$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, start_publishing)
            ]
        },
        fallbacks=[CallbackQueryHandler(button_handler, pattern="^back$")]
    )
    
    # إضافة المعالجات
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stop", stop_publishing))
    application.add_handler(login_conv)
    application.add_handler(super_conv)
    application.add_handler(publish_conv)
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # تشغيل البوت
    application.run_polling()

if __name__ == "__main__":
    main() 
