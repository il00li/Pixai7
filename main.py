import logging
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    InputMediaPhoto
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)
import requests
import datetime
import os

# إعدادات البوت
TOKEN = "7742801098:AAFFk0IuvH49BZbIuDocUILi2PcFyEzaI8s"
PEXELS_API_KEY = "1OrBtuFWP0BxjzlGqusrMj6RTjy7i8duDbgVDwJbSehBlHgRxKMnuG4F"
CHANNELS = ["@crazys7", "@AWU87"]
MANAGER_ID = 7251748706  # معرف المدير المحدث
WEBHOOK_URL = "https://pixai7.onrender.com"  # رابط الويب هووك

# حالات المستخدم
(
    MAIN_MENU,
    SEARCHING,
    RESULTS
) = range(3)

# إعداد التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# إرسال إشعار للمدير
async def notify_manager(context: ContextTypes.DEFAULT_TYPE, user: dict):
    try:
        # تنسيق الرسالة
        user_info = (
            f"👤 مستخدم جديد انضم إلى القنوات!\n\n"
            f"🆔 المعرف: {user.id}\n"
            f"👤 الاسم: {user.first_name}\n"
            f"📅 التاريخ: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        # إضافة اسم المستخدم إذا كان متوفراً
        if user.username:
            user_info += f"\n🔖 اليوزر: @{user.username}"
        
        # إرسال الإشعار للمدير
        await context.bot.send_message(
            chat_id=MANAGER_ID,
            text=user_info
        )
        logger.info(f"تم إرسال إشعار للمدير عن المستخدم {user.id}")
    except Exception as e:
        logger.error(f"خطأ في إرسال إشعار للمدير: {e}")

# فحص الاشتراك في القنوات
async def check_subscription(user_id, context: ContextTypes.DEFAULT_TYPE):
    try:
        for channel in CHANNELS:
            member = await context.bot.get_chat_member(
                chat_id=channel,
                user_id=user_id
            )
            if member.status not in ['member', 'administrator', 'creator']:
                return False
        return True
    except Exception as e:
        logger.error(f"Subscription check error: {e}")
        return False

# القائمة الرئيسية
async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("انقر للبحث 🎧", callback_data='search')],
        [InlineKeyboardButton("حـــ🤍ـــول", callback_data='about')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            "🌟 قائمة البحث الرئيسية 🌟",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "🌟 قائمة البحث الرئيسية 🌟",
            reply_markup=reply_markup
        )
    return MAIN_MENU

# بدء البوت
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if await check_subscription(user_id, context):
        # إرسال إشعار للمدير عند التحقق الناجح
        await notify_manager(context, update.effective_user)
        await main_menu(update, context)
        return MAIN_MENU
    else:
        await show_channels(update)

async def show_channels(update: Update):
    buttons = [
        [
            InlineKeyboardButton("قناة 1", url="https://t.me/crazys7"),
            InlineKeyboardButton("قناة 2", url="https://t.me/AWU87")
        ],
        [InlineKeyboardButton("تحقق | Check", callback_data='check_subscription')]
    ]
    await update.message.reply_text(
        "❗️ يجب الاشتراك في القنوات التالية أولاً:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# التحقق من الاشتراك
async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    if await check_subscription(user_id, context):
        # إرسال إشعار للمدير عند التحقق الناجح
        await notify_manager(context, query.from_user)
        await query.answer("تم التحقق بنجاح! ✅")
        await main_menu(update, context)
        return MAIN_MENU
    else:
        await query.answer("لم تكتمل الاشتراكات بعد! ❌", show_alert=True)
        return None

# بدء عملية البحث
async def start_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🔎 أرسل كلمة البحث الآن:")
    return SEARCHING

# البحث في Pexels API (صور فقط)
async def perform_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    search_query = update.message.text
    context.user_data['current_query'] = search_query
    context.user_data['current_index'] = 0
    
    url = f"https://api.pexels.com/v1/search?query={search_query}&per_page=80"
    headers = {"Authorization": PEXELS_API_KEY}
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        results = data.get('photos', [])
        
        if results:
            context.user_data['results'] = results
            context.user_data['current_index'] = 0
            await show_result(update, context)
            return RESULTS
        else:
            await update.message.reply_text("⚠️ لم يتم العثور على نتائج. حاول بكلمات أخرى.")
            await main_menu(update, context)
            return MAIN_MENU
    else:
        await update.message.reply_text("❌ حدث خطأ في البحث. يرجى المحاولة لاحقًا.")
        await main_menu(update, context)
        return MAIN_MENU

# عرض نتيجة البحث (صور فقط)
async def show_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    index = context.user_data['current_index']
    results = context.user_data['results']
    result = results[index]
    
    # تجهيز المعلومات
    media_url = result['src']['large']  # حجم مناسب للتلجرام
    caption = f"📸 المصور: {result['photographer']}"
    
    # إنشاء أزرار التنقل
    keyboard = []
    if index > 0:
        keyboard.append(InlineKeyboardButton("« السابق", callback_data='prev'))
    if index < len(results) - 1:
        keyboard.append(InlineKeyboardButton("التالي »", callback_data='next'))
    
    action_buttons = [
        InlineKeyboardButton("اعجبني ❤️", callback_data='like'),
        InlineKeyboardButton("رجوع ↩️", callback_data='back_to_menu')
    ]
    
    reply_markup = InlineKeyboardMarkup([keyboard, action_buttons])
    
    # إرسال الصورة
    if update.callback_query:
        await update.callback_query.edit_message_media(
            media=InputMediaPhoto(media_url, caption=caption),
            reply_markup=reply_markup
        )
    else:
        # إذا كانت الرسالة الأولى
        await update.message.reply_photo(
            photo=media_url,
            caption=caption,
            reply_markup=reply_markup
        )

# التنقل بين النتائج
async def navigate_results(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    action = query.data
    
    current_index = context.user_data['current_index']
    
    if action == 'next':
        context.user_data['current_index'] += 1
    elif action == 'prev':
        context.user_data['current_index'] -= 1
    
    await query.answer()
    await show_result(update, context)
    return RESULTS

# زر "اعجبني"
async def like_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("💚 تمت الإعجاب بالصورة!")
    
    # حذف الأزرار وإبقاء الصورة فقط
    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text("🔍 لإجراء بحث جديد، أرسل /start")

# قسم "حول"
async def show_about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    about_text = """
               🌿🌿🌿
             🌿          🌿
           🌿         🌿
         🌿   @AWU87   🌿
       🌿             🌿
     🌿   @crazys7    🌿
           \\       /
            \\     /
             \\   /
              | |
              | |  
              | |
              | |
             /   \\
            /_____\\

         🌱 أرض الإبداع 🌱
    """
    keyboard = [[InlineKeyboardButton("رجوع ↩️", callback_data='back')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(
        about_text,
        reply_markup=reply_markup
    )

# الرجوع للقائمة الرئيسية
async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await main_menu(update, context)
    return MAIN_MENU

# إعداد البوت مع ويب هووك
def main():
    application = Application.builder().token(TOKEN).build()

    # تسجيل handlers
    application.add_handler(CommandHandler('start', start))
    
    # handlers للتحقق من الاشتراك
    application.add_handler(CallbackQueryHandler(check_subscription_callback, pattern='^check_subscription$'))
    
    # handlers للقائمة الرئيسية
    application.add_handler(CallbackQueryHandler(start_search, pattern='^search$'))
    application.add_handler(CallbackQueryHandler(show_about, pattern='^about$'))
    application.add_handler(CallbackQueryHandler(back_to_menu, pattern='^back$'))
    application.add_handler(CallbackQueryHandler(back_to_menu, pattern='^back_to_menu$'))
    
    # handlers للبحث
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, perform_search))
    
    # handlers للنتائج
    application.add_handler(CallbackQueryHandler(navigate_results, pattern='^(prev|next)$'))
    application.add_handler(CallbackQueryHandler(like_result, pattern='^like$'))

    # تعيين ويب هووك (للاستخدام على Render)
    if "RENDER" in os.environ:
        application.run_webhook(
            listen="0.0.0.0",
            port=int(os.environ.get("PORT", 8443)),
            webhook_url=WEBHOOK_URL,
            secret_token='YOUR_SECRET_TOKEN'  # يمكنك إضافة توكن سري إذا لزم الأمر
        )
    else:
        # للتشغيل المحلي
        application.run_polling()

if __name__ == '__main__':
    main()
