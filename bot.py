import asyncio
import logging
import os
import sys
import sqlite3
from aiogram import Bot, Dispatcher, F, html
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, FSInputFile, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
import yt_dlp

TOKEN = os.getenv("8858895999:AAFHOkyvINgssJqgtnuV7UKd_odCbC0R38o")
# Majburiy obuna uchun kanal usernamesi (Masalan: "@kanal_username" yoki shart bo'lmasa None qoldiring)
REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", None) 

# --- MA'LUMOTLAR BAZASINI BIR FAYLNING O'ZIDA YARATISH ---
def init_db():
    db = sqlite3.connect("bot_database.db")
    cursor = db.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        downloads_count INTEGER DEFAULT 0
    )
    """)
    db.commit()
    db.close()

def add_user(user_id: int):
    db = sqlite3.connect("bot_database.db")
    cursor = db.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    db.commit()
    db.close()

def get_stats():
    db = sqlite3.connect("bot_database.db")
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    db.close()
    return count

def increment_download(user_id: int):
    db = sqlite3.connect("bot_database.db")
    cursor = db.cursor()
    cursor.execute("UPDATE users SET downloads_count = downloads_count + 1 WHERE user_id = ?", (user_id,))
    db.commit()
    db.close()

dp = Dispatcher()

# Majburiy obunani tekshirish funksiyasi
async def check_subscription(bot: Bot, user_id: int) -> bool:
    if not REQUIRED_CHANNEL:
        return True
    try:
        member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
        if member.status in ["member", "administrator", "creator"]:
            return True
    except Exception:
        pass
    return False

@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    init_db()
    add_user(message.from_user.id)
    
    if REQUIRED_CHANNEL and not await check_subscription(message.bot, message.from_user.id):
        kb = InlineKeyboardBuilder()
        kb.button(text="📢 Kanalga obuna bo'lish", url=f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}")
        kb.button(text="✅ Obunani tekshirish", callback_data="check_sub")
        await message.answer("Botdan foydalanish uchun avval quyidagi kanalimizga obuna bo'ling:", reply_markup=kb.as_markup())
        return

    await message.answer(
        f"Salom, {html.bold(message.from_user.full_name)}! 🚀\n\n"
        "🌐 **Qo'llab-quvvatlanadigan platformalar:**\n"
        "• YouTube, Instagram, TikTok, Facebook, X (Twitter), Pinterest, SoundCloud!\n\n"
        "📥 **Imkoniyatlar:**\n"
        "1. Istalgan havolani yuboring (Videoni **suvsiz** yoki to'liq MP3 qilib oling).\n"
        "2. Shunchaki **qo'shiq nomini yozing**, uni qidirib topib MP3 formatida beraman!"
    )

@dp.callback_query(F.data == "check_sub")
async def verify_sub(callback: CallbackQuery):
    if await check_subscription(callback.bot, callback.from_user.id):
        await callback.message.edit_text("Rahmat! Endi botdan to'liq foydalanishingiz mumkin. Havola yoki qo'shiq nomini yuboring.")
    else:
        await callback.answer("Siz hali kanalga obuna bo'lmadingiz!", show_alert=True)

# Admin uchun statistika buyrug'i
@dp.message(Command("stats"))
async def stats_handler(message: Message) -> None:
    count = get_stats()
    await message.answer(f"📊 Botimizdagi jami foydalanuvchilar soni: **{count}** ta", parse_mode="Markdown")

# Havolalar kelganda menyu chiqarish
@dp.message(F.text.startswith("http"))
async def media_menu(message: Message):
    url = message.text.strip()
    init_db()
    add_user(message.from_user.id)
    
    if REQUIRED_CHANNEL and not await check_subscription(message.bot, message.from_user.id):
        await message.answer("⚠️ Botdan foydalanish uchun kanalimizga obuna bo'lishingiz kerak!")
        return

    builder = InlineKeyboardBuilder()
    builder.button(text="🎬 Video (Suvsiz / HD)", callback_data=f"dl_vid_{url}")
    builder.button(text="🎵 Musiqa (MP3)", callback_data=f"dl_mp3_{url}")
    builder.adjust(1)
    
    await message.answer("Nimani yuklab beray?", reply_markup=builder.as_markup())

# Yuklab olish jarayoni (yt-dlp orqali)
@dp.callback_query(F.data.startswith("dl_"))
async def process_media_download(callback: CallbackQuery):
    data_parts = callback.data.split("_", 2)
    dl_type = data_parts[1] 
    url = data_parts[2]
    
    await callback.message.edit_text("📥 Fayl yuklab olinmoqda, iltimos kuting...")
    
    bot_info = await callback.bot.get_me()
    bot_username = bot_info.username
    
    file_path = None
    try:
        if dl_type == "vid":
            ydl_opts = {
                'format': 'best',
                'outtmpl': 'downloads/%(id)s.%(ext)s',
                'max_filesize': 50 * 1024 * 1024,
            }
        else:
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': 'downloads/%(id)s.%(ext)s',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'max_filesize': 50 * 1024 * 1024,
            }
            
        os.makedirs("downloads", exist_ok=True)
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if dl_type == "mp3":
                filename = os.path.splitext(filename)[0] + ".mp3"
            file_path = filename
            
        if file_path and os.path.exists(file_path):
            caption_text = f"@{bot_username} orqali yuklab olindi 🚀"
            
            if dl_type == "vid":
                await callback.message.answer_video(FSInputFile(file_path), caption=caption_text)
            else:
                await callback.message.answer_audio(FSInputFile(file_path), caption=caption_text)
            
            increment_download(callback.from_user.id)
            await callback.message.delete()
            os.remove(file_path)
        else:
            await callback.message.edit_text("❌ Kechirasiz, faylni yuklab bo'lmadi yoki hajmi 50MB dan katta.")
            
    except Exception as e:
        await callback.message.edit_text(f"❌ Xatolik yuz berdi: {str(e)}")
        if file_path and os.path.exists(file_path):
            os.remove(file_path)

# Qo'shiq nomi bo'yicha qidirib topish
@dp.message(F.text & ~F.text.startswith("/") & ~F.text.startswith("http"))
async def search_song(message: Message):
    query = message.text.strip()
    init_db()
    add_user(message.from_user.id)
    
    if REQUIRED_CHANNEL and not await check_subscription(message.bot, message.from_user.id):
        await message.answer("⚠️ Botdan foydalanish uchun kanalimizga obuna bo'lishingiz kerak!")
        return

    waiting_msg = await message.answer("🔍 Musiqa qidirilmoqda...")
    
    bot_info = await message.bot.get_me()
    bot_username = bot_info.username
    
    file_path = None
    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': 'downloads/%(id)s.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'max_filesize': 50 * 1024 * 1024,
            'default_search': 'ytsearch1',
            'noplaylist': True,
        }
        
        os.makedirs("downloads", exist_ok=True)
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch1:{query}", download=True)
            if 'entries' in info:
                info = info['entries'][0]
                
            filename = ydl.prepare_filename(info)
            filename = os.path.splitext(filename)[0] + ".mp3"
            file_path = filename
            title = info.get('title', 'Musiqa')
            
        if file_path and os.path.exists(file_path):
            caption_text = f"🎶 **{title}**\n\n@{bot_username} orqali topib yuklandi 🚀"
            await message.answer_audio(FSInputFile(file_path), caption=caption_text, parse_mode="Markdown")
            increment_download(message.from_user.id)
            await waiting_msg.delete()
            os.remove(file_path)
        else:
            await waiting_msg.edit_text("❌ Kechirasiz, bu nomdagi musiqani topib bo'lmadi.")
            
    except Exception as e:
        await waiting_msg.edit_text(f"❌ Xatolik yuz berdi: {str(e)}")
        if file_path and os.path.exists(file_path):
            os.remove(file_path)

async def main() -> None:
    if not TOKEN:
        raise ValueError("BOT_TOKEN topilmadi!")
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    print("Mukammal Media Bot bitta faylda ishga tushdi va buyruqlarni kutmoqda...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
