import logging
from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import requests
import datetime
import os
import asyncio

# ================ إعدادات البوت ================
TOKEN = "7742801098:AAFFk0IuvH49BZbIuDocUILi2PcFyEzaI8s"
PEXELS_API_KEY = "1OrBtuFWP0BxjzlGqusrMj6RTjy7i8duDbgVDwJbSehBlHgRxKMnuG4F"
CHANNELS = ["@crazys7", "@AWU87"]
MANAGER_ID = 7251748706
WEBHOOK_URL = "https://pixai7.onrender.com"

# ================ حالات المستخدم ================
class UserState(StatesGroup):
    MAIN_MENU = State()
    SEARCHING = State()
    RESULTS = State()

# ================ إعداد التسجيل ================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================ إنشاء كائنات البوت ================
bot = Bot(token=TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# ================ وظائف البوت ================
async def notify_manager(user: types.User):
    try:
        user_info = f"👤 مستخدم جديد انضم إلى القنوات!\n\n🆔 المعرف: {user.id}\n👤 الاسم: {user.first_name}\n📅 التاريخ: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        if user.username: user_info += f"\n🔖 اليوزر: @{user.username}"
        await bot.send_message(chat_id=MANAGER_ID, text=user_info)
    except Exception as e:
        logger.error(f"خطأ في إرسال إشعار للمدير: {e}")

async def check_subscription(user_id: int):
    try:
        for channel in CHANNELS:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                return False
        return True
    except Exception as e:
        logger.error(f"خطأ في التحقق من الاشتراك: {e}")
        return False

@router.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if await check_subscription(user_id):
        await notify_manager(message.from_user)
        await show_main_menu(message, state)
    else:
        await show_channels(message)

async def show_main_menu(message: types.Message, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="انقر للبحث 🎧", callback_data='search')],
        [InlineKeyboardButton(text="حـــ🤍ـــول", callback_data='about')]
    ])
    await message.answer("🌟 قائمة البحث الرئيسية 🌟", reply_markup=keyboard)
    await state.set_state(UserState.MAIN_MENU)

async def show_channels(message: types.Message):
    buttons = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="قناة 1", url="https://t.me/crazys7"),
         InlineKeyboardButton(text="قناة 2", url="https://t.me/AWU87")],
        [InlineKeyboardButton(text="تحقق | Check", callback_data='check_subscription')]
    ])
    await message.answer("❗️ يجب الاشتراك في القنوات التالية أولاً:", reply_markup=buttons)

@router.callback_query(F.data == 'check_subscription')
async def check_subscription_callback(callback: CallbackQuery, state: FSMContext):
    if await check_subscription(callback.from_user.id):
        await notify_manager(callback.from_user)
        await callback.answer("تم التحقق بنجاح! ✅")
        await show_main_menu(callback.message, state)
    else:
        await callback.answer("لم تكتمل الاشتراكات بعد! ❌", show_alert=True)

@router.callback_query(F.data == 'search')
async def start_search(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🔎 أرسل كلمة البحث الآن:")
    await state.set_state(UserState.SEARCHING)

@router.message(UserState.SEARCHING)
async def perform_search(message: types.Message, state: FSMContext):
    search_query = message.text
    url = f"https://api.pexels.com/v1/search?query={search_query}&per_page=80"
    headers = {"Authorization": PEXELS_API_KEY}
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            results = response.json().get('photos', [])
            if results:
                await state.update_data(results=results, current_index=0, current_query=search_query)
                await show_result(message, state)
                await state.set_state(UserState.RESULTS)
                return
        await message.answer("⚠️ لم يتم العثور على نتائج. حاول بكلمات أخرى.")
    except Exception as e:
        logger.error(f"خطأ في البحث: {e}")
        await message.answer("❌ حدث خطأ في البحث. يرجى المحاولة لاحقًا.")
    await show_main_menu(message, state)
    await state.set_state(UserState.MAIN_MENU)

async def show_result(message: types.Message, state: FSMContext):
    data = await state.get_data()
    index = data['current_index']
    result = data['results'][index]
    
    keyboard = []
    if index > 0: keyboard.append(InlineKeyboardButton(text="« السابق", callback_data='prev'))
    if index < len(data['results']) - 1: keyboard.append(InlineKeyboardButton(text="التالي »", callback_data='next'))
    
    action_buttons = [
        InlineKeyboardButton(text="اعجبني ❤️", callback_data='like'),
        InlineKeyboardButton(text="رجوع ↩️", callback_data='back_to_menu')
    ]
    
    reply_markup = InlineKeyboardMarkup(inline_keyboard=[keyboard, action_buttons])
    
    await message.answer_photo(
        photo=result['src']['large'],
        caption=f"📸 المصور: {result['photographer']}",
        reply_markup=reply_markup
    )

@router.callback_query(F.data.in_(['prev', 'next']), UserState.RESULTS)
async def navigate_results(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    current_index = data['current_index']
    new_index = current_index + 1 if callback.data == 'next' else current_index - 1
    await state.update_data(current_index=new_index)
    await callback.message.delete()
    await show_result(callback.message, state)

@router.callback_query(F.data == 'like', UserState.RESULTS)
async def like_result(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("💚 تمت الإعجاب بالصورة!")
    await callback.message.answer("🔍 لإجراء بحث جديد، أرسل /start")

@router.callback_query(F.data == 'about')
async def show_about(callback: CallbackQuery):
    about_text = """
       🌿🌿🌿
     🌿      🌿
   🌿        🌿
 🌿 @AWU87  🌿
   🌿            🌿
     🌿 @crazys7 🌿
         \     /
          \   /
           | |
           | |
          /   \\
         /_____\\
      🌱 أرض الإبداع 🌱
    """
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="رجوع ↩️", callback_data='back')]
    ])
    await callback.message.edit_text(about_text, reply_markup=keyboard)

@router.callback_query(F.data.in_(['back', 'back_to_menu']))
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    await show_main_menu(callback.message, state)

# ================ إعدادات التشغيل ================
async def on_startup():
    await bot.set_webhook(WEBHOOK_URL)
    logging.info("تم تشغيل البوت بنجاح!")

async def on_shutdown():
    await bot.delete_webhook()
    logging.info("إيقاف البوت...")

# ================ التشغيل الرئيسي ================
async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    # تحديد منفذ التشغيل (افتراضي 8443)
    port = int(os.environ.get('PORT', 8443))
    
    # التشغيل على Render (يفترض وجود متغير RENDER)
    if "RENDER" in os.environ:
        # تشغيل كخادم ويب
        from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
        from aiohttp import web
        
        app = web.Application()
        webhook_requests_handler = SimpleRequestHandler(
            dispatcher=dp,
            bot=bot,
        )
        
        webhook_requests_handler.register(app, path="/")
        setup_application(app, dp, bot=bot)
        
        async def on_startup(app):
            await bot.set_webhook(WEBHOOK_URL)
            logging.info("تم تشغيل البوت بنجاح على Render!")
        
        app.on_startup.append(on_startup)
        
        web.run_app(app, host='0.0.0.0', port=port)
    else:
        # للتشغيل المحلي
        asyncio.run(main())
