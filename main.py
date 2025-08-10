import asyncio
import logging
import re
import string
import random
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional

import telethon
from telethon import TelegramClient, events
from telethon.tl.functions.messages import GetAllChatsRequest
from telethon.tl.functions.channels import GetParticipantsRequest
from telethon.tl.types import ChannelParticipant, Channel, ChatInviteExported
from telethon.errors import (FloodWaitError, PhoneNumberInvalidError, 
                            SessionPasswordNeededError, UserNotParticipantError)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('bot.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Configuration constants
BOT_TOKEN = "8247037355:AAH2rRm9PJCXqcVISS8g-EL1lv3tvQTXFys"
API_ID = "23656977"
API_HASH = "49d3f43531a92b3f5bc403766313ca1e"
REQUIRED_CHANNELS = ["@crazys7", "@AWU87"]

# Data structures
class BotUser:
    def __init__(self):
        self.phone = None
        self.code = None
        self.password = None
        self.auth_key = None
        self.groups = []
        self.publish_interval = 10  # in minutes
        self.publishing_active = False
        self.publish_count = 0

users_data: Dict[int, BotUser] = {}  # user_id: BotUser
global_stats = {
    "total_publishes": 0,
    "total_users": 0,
    "total_groups": 0
}

# Helper functions
async def generate_string_session(client: TelegramClient) -> str:
    """Generate string session for user authentication"""
    try:
        await client.connect()
        await client.start()
        return await client.session.save()
    except Exception as e:
        logger.error(f"Error generating string session: {e}")
        return None

async def is_subscribed(client: TelegramClient, channel: str) -> bool:
    """Check if user is subscribed to a channel"""
    try:
        result = await client.get_entity(channel)
        if not isinstance(result, telethon.tl.types.Channel):
            return False
        participant = await client(GetParticipantsRequest(channel=result, limit=1))
        return any(participant.participants)
    except Exception as e:
        logger.error(f"Error checking subscription to {channel}: {e}")
        return False

async def validate_phone_number(phone: str) -> bool:
    """Validate phone number format"""
    pattern = r'^\+\d{10,15}$'
    return bool(re.match(pattern, phone))

async def check_group_membership(client: TelegramClient, group_id: int) -> bool:
    """Check if user is a member of a group"""
    try:
        group = await client.get_entity(group_id)
        if not isinstance(group, telethon.tl.types.Channel):
            return False
        participant = await client(GetParticipantsRequest(channel=group, limit=1))
        return any(participant.participants)
    except Exception as e:
        logger.error(f"Error checking group membership: {e}")
        return False

# Bot initialization
bot = TelegramClient('auto_publish_bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    """Handle /start command"""
    user_id = event.sender_id
    if user_id not in users_data:
        users_data[user_id] = BotUser()
        global_stats["total_users"] += 1
    
    keyboard = [
        [Button.inline("تسجيل دخول", data="login")],
        [Button.inline("بدء النشر", data="publish")],
        [Button.inline("إضافة مجموعات", data="add_groups")],
        [Button.inline("إحصائيات", data="stats")],
        [Button.inline("مساعدة", data="help")]
    ]
    
    await event.respond(
        "👋 **مرحبًا!** أنا بوت النشر التلقائي. اختر من الخيارات أدناه:",
        buttons=keyboard
    )

# Login flow
@bot.on(events.CallbackQuery(data=b'login'))
async def login_flow(event):
    """Start login flow"""
    user_id = event.sender_id
    await event.edit(
        "📝 **تسجيل الدخول**\n\nيرجى إرسال رقم هاتفك (+XXXXXXXXXX):",
        buttons=None
    )
    users_data[user_id].current_state = "LOGIN_PHONE"

@bot.on(events.NewMessage(func=lambda e: getattr(e.sender_id, 'current_state', None) == 'LOGIN_PHONE'))
async def login_phone(event):
    """Handle phone number input"""
    user_id = event.sender_id
    phone = event.text
    
    if not await validate_phone_number(phone):
        await event.respond("❌ **رقم الهاتف غير صالح!** يرجى إعادة المحاولة.")
        return
    
    try:
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        await client.send_code_request(phone)
        
        users_data[user_id].phone = phone
        users_data[user_id].current_state = "LOGIN_CODE"
        users_data[user_id].client = client
        
        await event.respond("💬 **تم إرسال كود التحقق.** يرجى إدخال الكود:")
    except Exception as e:
        logger.error(f"Error during login: {e}")
        await event.respond("❌ **حدث خطأ أثناء تسجيل الدخول.** يرجى المحاولة مرة أخرى.")

@bot.on(events.NewMessage(func=lambda e: getattr(e.sender_id, 'current_state', None) == 'LOGIN_CODE'))
async def login_code(event):
    """Handle verification code input"""
    user_id = event.sender_id
    code = event.text
    client = users_data[user_id].client
    
    try:
        user = await client.sign_in(user_id.phone, code)
        
        # Handle 2FA if required
        if await client.is_password_needed():
            users_data[user_id].current_state = "LOGIN_2FA"
            await event.respond("🔐 **مطلوب كلمة مرور الحماية二段階認証.** يرجى إدخالها:")
            return
        
        # Generate string session
        string_session = await generate_string_session(client)
        users_data[user_id].auth_key = string_session
        
        await event.respond("🎉 **تم تسجيل الدخول بنجاح!**")
    except SessionPasswordNeededError:
        users_data[user_id].current_state = "LOGIN_2FA"
        await event.respond("🔐 **مطلوب كلمة مرور الحماية二段階認証.** يرجى إدخالها:")
    except Exception as e:
        logger.error(f"Error during code verification: {e}")
        await event.respond("❌ **كود التحقق غير صحيح!** يرجى إعادة المحاولة.")

@bot.on(events.NewMessage(func=lambda e: getattr(e.sender_id, 'current_state', None) == 'LOGIN_2FA'))
async def login_2fa(event):
    """Handle 2FA password input"""
    user_id = event.sender_id
    password = event.text
    client = users_data[user_id].client
    
    try:
        await client.sign_in(password=password)
        string_session = await generate_string_session(client)
        users_data[user_id].auth_key = string_session
        
        await event.respond("🎉 **تم تسجيل الدخول بنجاح!**")
    except Exception as e:
        logger.error(f"Error during 2FA verification: {e}")
        await event.respond("❌ **كلمة المرور غير صحيحة!** يرجى إعادة المحاولة.")

# Group management
@bot.on(events.CallbackQuery(data=b'add_groups'))
async def add_groups_flow(event):
    """Start adding groups flow"""
    user_id = event.sender_id
    if not users_data[user_id].auth_key:
        await event.edit("⚠️ **يرجى تسجيل الدخول أولاً!**")
        return
    
    await event.edit(
        "➕ **إضافة مجموعات**\n\nيرجى إرسال معرف أو رابط المجموعة:"
    )
    users_data[user_id].current_state = "ADD_GROUP"

@bot.on(events.NewMessage(func=lambda e: getattr(e.sender_id, 'current_state', None) == 'ADD_GROUP'))
async def add_group(event):
    """Handle group addition"""
    user_id = event.sender_id
    group_link = event.text
    client = users_data[user_id].client
    
    try:
        group = await client.get_entity(group_link)
        
        # Check if it's a channel or group
        if not (isinstance(group, telethon.tl.types.Channel) or 
                isinstance(group, telethon.tl.types.Chat)):
            await event.respond("❌ **الرابط غير صالح!** يرجى التحقق من معرف المجموعة.")
            return
        
        # Check membership
        if not await check_group_membership(client, group.id):
            await event.respond("❌ **أنت لست عضوًا في هذه المجموعة!**")
            return
        
        users_data[user_id].groups.append(group.id)
        global_stats["total_groups"] += 1
        
        await event.respond(f"✅ **تم إضافة المجموعة:** {group.title}")
    except Exception as e:
        logger.error(f"Error adding group: {e}")
        await event.respond("❌ **حدث خطأ.** يرجى التحقق من الرابط ومباركة مجددا.")

# Publishing workflow
@bot.on(events.CallbackQuery(data=b'publish'))
async def publish_flow(event):
    """Start publishing flow"""
    user_id = event.sender_id
    
    # Check if user is logged in
    if not users_data[user_id].auth_key:
        await event.edit("⚠️ **يرجى تسجيل الدخول أولاً!**")
        return
    
    # Check mandatory channel subscription
    client = users_data[user_id].client
    if not all(await asyncio.gather(*[is_subscribed(client, ch) for ch in REQUIRED_CHANNELS])):
        await event.edit("❌ **يرجى الاشتراك في القنوات المطلوبة:** " + " و ".join(REQUIRED_CHANNELS))
        return
    
    # If no groups added
    if not users_data[user_id].groups:
        await event.edit("❌ **لم تقم بإضافة أي مجموعات!**")
        return
    
    await event.edit(
        "📝 **إعدادات النشر**\n\nيرجى إرسال المحتوى الذي تريد نشره:",
        buttons=None
    )
    users_data[user_id].current_state = "PUBLISH_CONTENT"

@bot.on(events.NewMessage(func=lambda e: getattr(e.sender_id, 'current_state', None) == 'PUBLISH_CONTENT'))
async def publish_content(event):
    """Handle publication content"""
    user_id = event.sender_id
    content = event.text
    
    await event.respond(
        "🕒 **تحديد فترة النشر**\n\nيرجى إرسال فترة النشر بالدقائق (2-120):"
    )
    users_data[user_id].content = content
    users_data[user_id].current_state = "PUBLISH_INTERVAL"

@bot.on(events.NewMessage(func=lambda e: getattr(e.sender_id, 'current_state', None) == 'PUBLISH_INTERVAL'))
async def publish_interval(event):
    """Handle publication interval"""
    user_id = event.sender_id
    try:
        interval = int(event.text)
        if not (2 <= interval <= 120):
            await event.respond("❌ **فترة النشر يجب أن تكون بين 2-120 دقيقة!**")
            return
        
        users_data[user_id].publish_interval = interval
        
        # Start publishing
        asyncio.create_task(start_publishing(user_id))
        
        await event.respond(
            f"🚀 **بدأ النشر كل {interval} دقيقة!**\nلإيقاف النشر: /stop"
        )
    except ValueError:
        await event.respond("❌ **يرجى إدخال رقم صالح!**")

async def start_publishing(user_id: int):
    """Start publishing messages at specified interval"""
    if users_data[user_id].publishing_active:
        return
    
    users_data[user_id].publishing_active = True
    client = users_data[user_id].client
    content = users_data[user_id].content
    interval = users_data[user_id].publish_interval
    
    while users_data[user_id].publishing_active:
        # Check group membership before publishing
        valid_groups = []
        for group_id in users_data[user_id].groups:
            if await check_group_membership(client, group_id):
                valid_groups.append(group_id)
        
        # Update groups if some are no longer accessible
        if not valid_groups:
            users_data[user_id].publishing_active = False
            await bot.send_message(
                user_id, 
                "❌ **لم تعد عضوًا في أي من المجموعات المضافة!**"
            )
            return
        
        users_data[user_id].groups = valid_groups
        
        # Publish to groups with delay
        for group_id in valid_groups:
            try:
                group = await client.get_entity(group_id)
                await client.send_message(group, content, parse_mode='markdown')
                users_data[user_id].publish_count += 1
                global_stats["total_publishes"] += 1
                await asyncio.sleep(10)  # Avoid sending too quickly
            except Exception as e:
                logger.error(f"Error publishing to group {group_id}: {e}")
        
        # Wait for next interval
        await asyncio.sleep(interval * 60)

@bot.on(events.NewMessage(pattern='/stop'))
async def stop_publishing(event):
    """Stop publishing"""
    user_id = event.sender_id
    if users_data[user_id].publishing_active:
        users_data[user_id].publishing_active = False
        await event.respond("🛑 **تم إيقاف النشر!**")
    else:
        await event.respond("❌ **لم يتم بدء النشر!**")

# Stats and help
@bot.on(events.CallbackQuery(data=b'stats'))
async def show_stats(event):
    """Show user stats"""
    user_id = event.sender_id
    if user_id not in users_data:
        users_data[user_id] = BotUser()
        global_stats["total_users"] += 1
    
    stats_text = (
        f"📊 **إحصائياتك**:\n"
        f"• عدد النشرات: {users_data[user_id].publish_count}\n"
        f"• عدد المجموعات: {len(users_data[user_id].groups)}\n\n"
        f"📊 **الإحصائيات العامة**:\n"
        f"• إجمالي النشرات: {global_stats['total_publishes']}\n"
        f"• إجمالي المستخدمين: {global_stats['total_users']}\n"
        f"• إجمالي المجموعات: {global_stats['total_groups']}"
    )
    await event.edit(stats_text)

@bot.on(events.CallbackQuery(data=b'help'))
async def show_help(event):
    """Show help message"""
    help_text = (
        "📋 **المساعدة**:\n\n"
        "• /start - بدء التواصل مع البوت\n"
        "• تسجيل دخول - تسجيل الدخول عبر رقم الهاتف\n"
        "• إضافة مجموعات - إضافة مجموعات للنشر\n"
        "• بدء النشر - بدء النشر التلقائي\n"
        "• /stop - إيقاف النشر\n"
        "\n📝 **ملاحظات**:\n"
        "- يجب الاشتراك في القنوات المطلوبة لاستخدام البوت\n"
        "- لا تشارك أي أكواد تحقق مع أي شخص\n"
        "- لا تنشر محتوى غير قانوني"
    )
    await event.edit(help_text)

# Error handling
@bot.on(events.NewMessage(func=lambda e: True))
async def general_error_handler(event):
    """Handle unexpected messages"""
    user_id = event.sender_id
    await event.respond("⚠️ **رسالة غير متوقعة.** يرجى استخدام لوحة المفاتيح.")

async def main():
    """Main coroutine for bot operation"""
    await bot.run_until_disconnected()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.critical(f"Bot crashed with error: {e}")
        exit(1)
 
