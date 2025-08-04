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
MANAGER_ID = 7251748706
WEBHOOK_URL = "https://pixai7.onrender.com"

# حالات المستخدم
MAIN_MENU, SEARCHING, RESULTS = range(3)

# إعداد التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def notify_manager(context: ContextTypes.DEFAULT_TYPE, user: dict):
    try:
        user_info = (
            f"👤 مستخدم جديد انضم إلى القنوات!\n\n"
            f"🆔 المعرف: {user.id}\n"
            f"👤 الاسم: {user.first_name}\n"
            f"📅 التاريخ: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        if user.username:
            user_info += f"\n🔖 اليوزر: @{user.username}"
        
        await context.bot.send_message(chat_id=MANAGER_ID, text=user_info)
    except Exception as e:
        logger.error(f"خطأ في إرسال إشعار للمدير: {e}")

async def check_subscription(user_id, context: ContextTypes.DEFAULT_TYPE):
    try:
        for channel in CHANNELS:
            member = await context.bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                return False
        return True
    except Exception as e:
        logger.error(f"خطأ في التحقق من الاشتراك: {e}")
        return False

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("انقر للبحث 🎧", callback_data='search')],
        [InlineKeyboardButton("حـــ🤍ـــول", callback_data='about')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text("🌟 قائمة البحث الرئيسية 🌟", reply_markup=reply_markup)
    else:
        await update.message.reply_text("🌟 قائمة البحث الرئيسية 🌟", reply_markup=reply_markup)
    return MAIN_MENU

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if await check_subscription(user_id, context):
        await notify_manager(context, update.effective_user)
        await main_menu(update, context)
    else:
        await show_channels(update)

async def show_channels(update: Update):
    buttons = [
        [InlineKeyboardButton("قناة 1", url="https://t.me/crazys7"),
         InlineKeyboardButton("قناة 2", url="https://t.me/AWU87")],
        [InlineKeyboardButton("تحقق | Check", callback_data='check_subscription')]
    ]
    await update.message.reply_text("❗️ يجب الاشتراك في القنوات التالية أولاً:", reply_markup=InlineKeyboardMarkup(buttons))

async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if await check_subscription(query.from_user.id, context):
        await notify_manager(context, query.from_user)
        await query.answer("تم التحقق بنجاح! ✅")
        await main_menu(update, context)
    else:
        await query.answer("لم تكتمل الاشتراكات بعد! ❌", show_alert=True)

async def start_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("🔎 أرسل كلمة البحث الآن:")
    return SEARCHING

async def perform_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    search_query = update.message.text
    url = f"https://api.pexels.com/v1/search?query={search_query}&per_page=80"
    headers = {"Authorization": PEXELS_API_KEY}
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            results = response.json().get('photos', [])
            if results:
                context.user_data.update({
                    'results': results,
                    'current_index': 0,
                    'current_query': search_query
                })
                await show_result(update, context)
                return RESULTS
        await update.message.reply_text("⚠️ لم يتم العثور على نتائج. حاول بكلمات أخرى.")
    except Exception as e:
        logger.error(f"خطأ في البحث: {e}")
        await update.message.reply_text("❌ حدث خطأ في البحث. يرجى المحاولة لاحقًا.")
    await main_menu(update, context)
    return MAIN_MENU

async def show_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    index = context.user_data['current_index']
    result = context.user_data['results'][index]
    
    keyboard = []
    if index > 0:
        keyboard.append(InlineKeyboardButton("« السابق", callback_data='prev'))
    if index < len(context.user_data['results']) - 1:
        keyboard.append(InlineKeyboardButton("التالي »", callback_data='next'))
    
    reply_markup = InlineKeyboardMarkup([
        keyboard,
        [InlineKeyboardButton("اعجبني ❤️", callback_data='like'),
         InlineKeyboardButton("رجوع ↩️", callback_data='back_to_menu')]
    ])
    
    media = InputMediaPhoto(result['src']['large'], caption=f"📸 المصور: {result['photographer']}")
    
    if update.callback_query:
        await update.callback_query.edit_message_media(media=media, reply_markup=reply_markup)
    else:
        await update.message.reply_photo(photo=result['src']['large'], caption=media.caption, reply_markup=reply_markup)

async def navigate_results(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action = update.callback_query.data
    context.user_data['current_index'] += 1 if action == 'next' else -1
    await update.callback_query.answer()
    await show_result(update, context)
    return RESULTS

async def like_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("💚 تمت الإعجاب بالصورة!")
    await update.callback_query.edit_message_reply_markup(reply_markup=None)
    await update.callback_query.message.reply_text("🔍 لإجراء بحث جديد، أرسل /start")

async def show_about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    about_text = """
           🌿🌿🌿
         🌿      🌿
       🌿        🌿
     🌿 @AWU87  🌿
   🌿            🌿
 🌿 @crazys7    🌿
       \     /
        \   /
         | |
         | |
        /   \\
       /_____\\
    🌱 أرض الإبداع 🌱
    """
    await update.callback_query.edit_message_text(
        about_text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("رجوع ↩️", callback_data='back')]])
    )

async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await main_menu(update, context)
    return MAIN_MENU

def main():
    # إنشاء التطبيق
    application = Application.builder().token(TOKEN).build()
    
    # تسجيل handlers
    handlers = [
        CommandHandler('start', start),
        CallbackQueryHandler(check_subscription_callback, pattern='^check_subscription$'),
        CallbackQueryHandler(start_search, pattern='^search$'),
        CallbackQueryHandler(show_about, pattern='^about$'),
        CallbackQueryHandler(back_to_menu, pattern='^back$'),
        CallbackQueryHandler(back_to_menu, pattern='^back_to_menu$'),
        MessageHandler(filters.TEXT & ~filters.COMMAND, perform_search),
        CallbackQueryHandler(navigate_results, pattern='^(prev|next)$'),
        CallbackQueryHandler(like_result, pattern='^like$')
    ]
    
    for handler in handlers:
        application.add_handler(handler)
    
    # تشغيل البوت باستخدام ويب هووك فقط
    port = int(os.environ.get('PORT', 8443))
    application.run_webhook(
        listen="0.0.0.0",
        port=port,
        webhook_url=WEBHOOK_URL,
        secret_token=TOKEN
    )

if __name__ == '__main__':
    main()
