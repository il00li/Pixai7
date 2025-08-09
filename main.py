import os
import re
import asyncio
import logging
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardRemove
)
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackContext,
    MessageHandler,
    Filters,
    ConversationHandler,
    CallbackQueryHandler
)

# إعدادات البوت
TOKEN = "8312137482:AAEORpBnD8CmFfB39ayJT4UputPoSh_qCRw"
ADMIN_ID = 7251748706  # وضع إداري آيديك هنا

# مراحل المحادثة
PHONE, CODE, REPORT_TYPE, REPORT_LINK, REPORT_MESSAGE, CONFIRMATION = range(6)

# أنواع البلاغات
REPORT_TYPES = {
    "spam": "بريد مزعج",
    "violence": "عنف",
    "porn": "إباحي",
    "terrorism": "إرهاب",
    "scam": "احتيال",
    "hate": "خطاب كراهية"
}

# تخزين بيانات الجلسة
sessions = {}
reports = {}

# بدء البوت
def start(update: Update, context: CallbackContext) -> int:
    user = update.message.from_user
    keyboard = [
        [InlineKeyboardButton("بدء جلسة جديدة", callback_data="new_session")]
    ]
    update.message.reply_text(
        "مرحباً! 🌍\n"
        "هذا البوت يساعدك في الإبلاغ عن المحتوى الضار لخلق بيئة تلجرام أنظف.\n\n"
        "اضغط على الزر لبدء جلسة الإبلاغ:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return PHONE

# معالجة إنشاء جلسة
def handle_session(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    query.edit_message_text(
        "📱 الرجاء إرسال رقم هاتفك (مع رمز الدولة) مثل:\n"
        "+201234567890\n\n"
        "سيتم إرسال كود التحقق إلى حسابك على تلجرام."
    )
    return PHONE

# معالجة رقم الهاتف
def handle_phone(update: Update, context: CallbackContext) -> int:
    phone = update.message.text
    if not re.match(r"^\+\d{10,15}$", phone):
        update.message.reply_text("❌ رقم غير صحيح! الرجاء إدخال رقم صحيح مع رمز الدولة مثل: +201234567890")
        return PHONE
    
    # في الواقع هنا يجب إرسال الكود إلى المستخدم عبر تلجرام
    # لكن لأغراض التجربة سنستخدم كود وهمي
    context.user_data['phone'] = phone
    context.user_data['code'] = "12345"  # في الواقع يتم توليد كود عشوائي
    
    update.message.reply_text(
        f"🔑 تم إرسال كود التحقق إلى {phone}\n"
        "الرجاء إدخال الكود المكون من 5 أرقام:"
    )
    return CODE

# معالجة كود التحقق
def handle_code(update: Update, context: CallbackContext) -> int:
    user_code = update.message.text
    if user_code != context.user_data.get('code', ''):
        update.message.reply_text("❌ كود التحقق غير صحيح! الرجاء المحاولة مرة أخرى.")
        return CODE
    
    # تخزين الجلسة
    user_id = update.message.from_user.id
    sessions[user_id] = {
        'phone': context.user_data['phone'],
        'verified': True
    }
    
    # بناء لوحة المفاتيح لأنواع البلاغات
    keyboard = [
        [InlineKeyboardButton(name, callback_data=type_id)]
        for type_id, name in REPORT_TYPES.items()
    ]
    
    update.message.reply_text(
        "✅ تم التحقق بنجاح!\n\n"
        "الرجاء اختيار نوع البلاغ:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return REPORT_TYPE

# معالجة نوع البلاغ
def handle_report_type(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    report_type = query.data
    context.user_data['report_type'] = report_type
    
    query.edit_message_text(
        f"📌 نوع البلاغ: {REPORT_TYPES[report_type]}\n\n"
        "الرجاء إرسال رابط المجموعة/القناة/الحساب:"
    )
    return REPORT_LINK

# معالجة رابط البلاغ
def handle_report_link(update: Update, context: CallbackContext) -> int:
    link = update.message.text
    if not re.match(r"^(https?://t\.me/|@)[a-zA-Z0-9_]{5,32}$", link):
        update.message.reply_text("❌ رابط غير صحيح! الرجاء إرسال رابط صحيح مثل:\nhttps://t.me/group_name\nأو @username")
        return REPORT_LINK
    
    context.user_data['report_link'] = link
    update.message.reply_text(
        "✍️ الرجاء كتابة تفاصيل البلاغ:\n"
        "(وصف المشكلة، المستخدمين المتورطين، إلخ)"
    )
    return REPORT_MESSAGE

# معالجة تفاصيل البلاغ
def handle_report_message(update: Update, context: CallbackContext) -> int:
    report_message = update.message.text
    context.user_data['report_message'] = report_message
    
    # تأكيد البلاغ
    report_details = (
        f"📝 تفاصيل البلاغ:\n"
        f"النوع: {REPORT_TYPES[context.user_data['report_type']]}\n"
        f"الرابط: {context.user_data['report_link']}\n"
        f"التفاصيل: {report_message}"
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ تأكيد الإرسال", callback_data="confirm_send")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="cancel")]
    ]
    
    update.message.reply_text(
        report_details + "\n\n"
        "الرجاء التأكيد قبل الإرسال:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CONFIRMATION

# إرسال البلاغات
def send_reports(context: CallbackContext, user_id: int):
    report = reports.get(user_id)
    if not report:
        return
    
    # في الواقع هنا سيتم إرسال البلاغات إلى إدارة تلجرام
    # هذا جزء محاكاة فقط
    context.bot.send_message(
        chat_id=user_id,
        text=f"🚀 تم إرسال البلاغ #{report['count']} إلى إدارة تلجرام"
    )
    
    report['count'] += 1
    if report['count'] <= 10:  # إرسال 10 بلاغات كمثال
        context.job_queue.run_once(
            lambda ctx: send_reports(ctx, user_id),
            10,  # كل 10 ثواني
            context=user_id
        )
    else:
        context.bot.send_message(
            chat_id=user_id,
            text="✅ تم إكمال عملية الإبلاغ! تم إرسال 10 بلاغات إلى إدارة تلجرام."
        )
        del reports[user_id]

# معالجة التأكيد
def handle_confirmation(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    
    if query.data == "confirm_send":
        user_id = query.from_user.id
        reports[user_id] = {
            'type': context.user_data['report_type'],
            'link': context.user_data['report_link'],
            'message': context.user_data['report_message'],
            'count': 1
        }
        
        query.edit_message_text(
            "⏳ جاري بدء عملية الإبلاغ...\n"
            "سأقوم بإرسال البلاغات بشكل متكرر حتى يتم حظر المحتوى.\n\n"
            "يمكنك إيقاف العملية بأي وقت باستخدام /stop"
        )
        
        # بدء إرسال البلاغات
        send_reports(context, user_id)
        return ConversationHandler.END
    else:
        query.edit_message_text("❌ تم إلغاء عملية الإبلاغ.")
        return ConversationHandler.END

# إيقاف البلاغات
def stop_reporting(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    if user_id in reports:
        del reports[user_id]
        update.message.reply_text("⏹️ تم إيقاف عملية الإبلاغ بنجاح!")
    else:
        update.message.reply_text("⚠️ لا توجد عملية إبلاغ جارية.")

# إعداد البوت
def main() -> None:
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    
    updater = Updater(TOKEN)
    dispatcher = updater.dispatcher
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            PHONE: [
                CallbackQueryHandler(handle_session, pattern='^new_session$'),
                MessageHandler(Filters.text & ~Filters.command, handle_phone)
            ],
            CODE: [MessageHandler(Filters.text & ~Filters.command, handle_code)],
            REPORT_TYPE: [CallbackQueryHandler(handle_report_type)],
            REPORT_LINK: [MessageHandler(Filters.text & ~Filters.command, handle_report_link)],
            REPORT_MESSAGE: [MessageHandler(Filters.text & ~Filters.command, handle_report_message)],
            CONFIRMATION: [CallbackQueryHandler(handle_confirmation)]
        },
        fallbacks=[CommandHandler('stop', stop_reporting)]
    )
    
    dispatcher.add_handler(conv_handler)
    dispatcher.add_handler(CommandHandler("stop", stop_reporting))
    
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
