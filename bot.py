"""
Ko'p funksiyali Video Downloader — Telegram Bot
=================================================

Funksiyalar:
- Instagram, TikTok, YouTube Shorts linklarini qabul qiladi
- Video VA rasm/karusel postlarni yuklab beradi
- Til tanlash (O'zbek / Rus)
- Foydalanuvchi statistikasi (nechta video yuklagani)
- Sifat tanlash (HD / Past sifat)
- Yuklanish progress-bar bilan ko'rsatiladi
- Guruhlarda ham ishlaydi (BotFather'da privacy mode o'chirilishi kerak)
"""

import os
import re
import json
import uuid
import logging
import asyncio
import tempfile

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputMediaVideo,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
import yt_dlp

# ------------------------------------------------------------------
# SOZLAMALAR
# ------------------------------------------------------------------

BOT_TOKEN = os.environ.get("BOT_TOKEN", "SIZNING_TOKENINGIZ_BU_YERGA")
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")
MAX_FILE_SIZE_MB = 50

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

URL_PATTERN = re.compile(
    r"(https?://(www\.)?(instagram\.com|tiktok\.com|vm\.tiktok\.com|"
    r"youtube\.com/shorts|youtu\.be)/\S+)"
)

# ------------------------------------------------------------------
# MATNLAR (TIL)
# ------------------------------------------------------------------

TEXTS = {
    "uz": {
        "choose_lang": "Tilni tanlang / Выберите язык:",
        "welcome": (
            "Salom! Menga Instagram, TikTok yoki YouTube Shorts linkini "
            "yuboring, men video yoki rasmlarni yuklab beraman."
        ),
        "not_a_link": "Iltimos, to'g'ri link yuboring (Instagram, TikTok yoki YouTube Shorts).",
        "choose_quality": "Sifatni tanlang:",
        "hd": "🎬 HD sifat",
        "sd": "📉 Past sifat (tezroq)",
        "mp3": "🎵 MP3 (audio)",
        "downloading": "⏳ Yuklanmoqda...",
        "sending": "📤 Yuborilmoqda...",
        "done": "✅ Tayyor!",
        "too_big": "❌ Fayl juda katta (50MB dan oshadi), Telegram orqali yuborib bo'lmaydi.",
        "error": "❌ Yuklab bo'lmadi. Link yopiq (private) akkauntga tegishli bo'lishi yoki tuzilma o'zgargan bo'lishi mumkin.",
        "unexpected_error": "❌ Kutilmagan xatolik yuz berdi. Birozdan so'ng qayta urinib ko'ring.",
        "stats": "📊 Siz jami *{count}* ta media yuklab oldingiz.",
        "lang_set": "✅ Til o'zbek tiliga o'rnatildi.",
    },
    "ru": {
        "choose_lang": "Выберите язык / Tilni tanlang:",
        "welcome": (
            "Привет! Отправь мне ссылку из Instagram, TikTok или YouTube Shorts, "
            "и я скачаю видео или фото."
        ),
        "not_a_link": "Пожалуйста, отправьте корректную ссылку (Instagram, TikTok или YouTube Shorts).",
        "choose_quality": "Выберите качество:",
        "hd": "🎬 HD качество",
        "sd": "📉 Низкое качество (быстрее)",
        "mp3": "🎵 MP3 (аудио)",
        "downloading": "⏳ Загрузка...",
        "sending": "📤 Отправка...",
        "done": "✅ Готово!",
        "too_big": "❌ Файл слишком большой (более 50MB), Telegram не позволяет отправить.",
        "error": "❌ Не удалось скачать. Возможно, аккаунт закрытый или изменилась структура сайта.",
        "unexpected_error": "❌ Произошла непредвиденная ошибка. Попробуйте снова чуть позже.",
        "stats": "📊 Вы всего скачали *{count}* медиафайлов.",
        "lang_set": "✅ Язык установлен на русский.",
    },
}


def t(user_id: int, key: str) -> str:
    lang = get_user(user_id).get("lang", "uz")
    return TEXTS[lang][key]


# ------------------------------------------------------------------
# MA'LUMOTLARNI SAQLASH (til, statistika)
# ------------------------------------------------------------------

def load_data() -> dict:
    if not os.path.exists(DATA_FILE):
        return {"users": {}}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"users": {}}


def save_data(data: dict) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_user(user_id: int) -> dict:
    data = load_data()
    return data["users"].get(str(user_id), {"lang": "uz", "count": 0})


def set_user_lang(user_id: int, lang: str) -> None:
    data = load_data()
    user = data["users"].setdefault(str(user_id), {"lang": "uz", "count": 0})
    user["lang"] = lang
    save_data(data)


def increment_user_count(user_id: int, by: int = 1) -> None:
    data = load_data()
    user = data["users"].setdefault(str(user_id), {"lang": "uz", "count": 0})
    user["count"] = user.get("count", 0) + by
    save_data(data)


# ------------------------------------------------------------------
# TELEGRAM HANDLERLAR: START / TIL / STATISTIKA
# ------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = load_data()
    if str(user_id) not in data["users"]:
        await ask_language(update, context)
    else:
        await update.message.reply_text(t(user_id, "welcome"))


async def ask_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🇺🇿 O'zbekcha", callback_data="lang|uz"),
                InlineKeyboardButton("🇷🇺 Русский", callback_data="lang|ru"),
            ]
        ]
    )
    await update.message.reply_text(
        "Tilni tanlang / Выберите язык:", reply_markup=keyboard
    )


async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ask_language(update, context)


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    count = get_user(user_id).get("count", 0)
    await update.message.reply_text(
        t(user_id, "stats").format(count=count), parse_mode="Markdown"
    )


# ------------------------------------------------------------------
# YORDAMCHI: progress-bar matni
# ------------------------------------------------------------------

def build_progress_bar(percent: float) -> str:
    filled = int(percent / 10)
    bar = "■" * filled + "□" * (10 - filled)
    return f"[{bar}] {percent:.0f}%"


# ------------------------------------------------------------------
# YUKLAB OLISH FUNKSIYASI (alohida thread'da ishlaydi)
# ------------------------------------------------------------------

def extract_and_download(url: str, output_dir: str, quality: str, progress_callback):
    """
    yt-dlp bilan ma'lumotni yuklab oladi. Karusel (bir nechta rasm/video)
    bo'lsa, hammasini yuklaydi. Yuklangan fayllar ro'yxatini qaytaradi:
    [{"path": ..., "media_type": "video" | "photo" | "audio"}, ...]
    """
    output_template = os.path.join(output_dir, "%(id)s_%(autonumber)s.%(ext)s")

    def hook(d):
        if d.get("status") == "downloading":
            percent_str = d.get("_percent_str", "0%").strip().replace("%", "")
            try:
                percent = float(percent_str)
            except ValueError:
                percent = 0.0
            progress_callback(percent)

    if quality == "mp3":
        ydl_opts = {
            "outtmpl": output_template,
            "format": "bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "noplaylist": False,
            "progress_hooks": [hook],
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
        }
    else:
        fmt = "worst[ext=mp4]/worst" if quality == "sd" else "best[ext=mp4]/best"
        ydl_opts = {
            "outtmpl": output_template,
            "format": fmt,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": False,  # karusel postlar uchun kerak
            "progress_hooks": [hook],
        }

    results = []
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

        entries = info.get("entries") if info.get("entries") is not None else [info]

        for entry in entries:
            if entry is None:
                continue
            raw_filename = ydl.prepare_filename(entry)

            if quality == "mp3":
                # Audio ajratib olingandan keyin fayl kengaytmasi .mp3 ga o'zgaradi
                filename = os.path.splitext(raw_filename)[0] + ".mp3"
                media_type = "audio"
            else:
                filename = raw_filename
                ext = entry.get("ext", "")
                media_type = "video" if ext in ("mp4", "mov", "mkv", "webm") else "photo"

            if not os.path.exists(filename):
                continue

            results.append({"path": filename, "media_type": media_type})

    return results


# ------------------------------------------------------------------
# XABAR HANDLER: LINK ANIQLASH VA SIFAT SO'RASH
# ------------------------------------------------------------------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text or ""
    match = URL_PATTERN.search(text)

    if not match:
        await update.message.reply_text(t(user_id, "not_a_link"))
        return

    url = match.group(1)

    # Uzun URL'ni callback_data ichiga to'g'ridan-to'g'ri joylashtirib bo'lmaydi
    # (Telegram cheklovi 64 bayt), shuning uchun vaqtinchalik ID orqali saqlaymiz.
    download_id = uuid.uuid4().hex[:8]
    context.bot_data.setdefault("pending", {})[download_id] = url

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    t(user_id, "hd"), callback_data=f"dl|{download_id}|hd"
                ),
                InlineKeyboardButton(
                    t(user_id, "sd"), callback_data=f"dl|{download_id}|sd"
                ),
            ],
            [
                InlineKeyboardButton(
                    t(user_id, "mp3"), callback_data=f"dl|{download_id}|mp3"
                ),
            ],
        ]
    )
    await update.message.reply_text(t(user_id, "choose_quality"), reply_markup=keyboard)


# ------------------------------------------------------------------
# CALLBACK HANDLER: TIL TANLASH VA SIFAT TANLASH
# ------------------------------------------------------------------

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data_parts = query.data.split("|")

    if data_parts[0] == "lang":
        lang = data_parts[1]
        set_user_lang(user_id, lang)
        await query.edit_message_text(TEXTS[lang]["lang_set"])
        return

    if data_parts[0] == "dl":
        download_id, quality = data_parts[1], data_parts[2]
        url = context.bot_data.get("pending", {}).pop(download_id, None)

        if not url:
            await query.edit_message_text(t(user_id, "error"))
            return

        await query.edit_message_text(t(user_id, "downloading") + " " + build_progress_bar(0))
        await do_download(update, context, url, quality, query.message.chat_id, query.message.message_id)


# ------------------------------------------------------------------
# YUKLASH VA YUBORISH JARAYONI
# ------------------------------------------------------------------

async def do_download(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
    quality: str,
    chat_id: int,
    status_message_id: int,
):
    user_id = update.effective_user.id
    loop = asyncio.get_event_loop()

    last_percent = {"value": -100}

    def progress_callback(percent: float):
        if percent - last_percent["value"] >= 10:
            last_percent["value"] = percent
            text = t(user_id, "downloading") + " " + build_progress_bar(percent)
            asyncio.run_coroutine_threadsafe(
                context.bot.edit_message_text(
                    chat_id=chat_id, message_id=status_message_id, text=text
                ),
                loop,
            )

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            results = await loop.run_in_executor(
                None, extract_and_download, url, tmpdir, quality, progress_callback
            )

            if not results:
                await context.bot.edit_message_text(
                    chat_id=chat_id, message_id=status_message_id, text=t(user_id, "error")
                )
                return

            valid_results = []
            for r in results:
                size_mb = os.path.getsize(r["path"]) / (1024 * 1024)
                if size_mb <= MAX_FILE_SIZE_MB:
                    valid_results.append(r)

            if not valid_results:
                await context.bot.edit_message_text(
                    chat_id=chat_id, message_id=status_message_id, text=t(user_id, "too_big")
                )
                return

            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=status_message_id, text=t(user_id, "sending")
            )

            if len(valid_results) == 1:
                r = valid_results[0]
                with open(r["path"], "rb") as f:
                    if r["media_type"] == "audio":
                        await context.bot.send_audio(chat_id=chat_id, audio=f)
                    elif r["media_type"] == "video":
                        await context.bot.send_video(chat_id=chat_id, video=f)
                    else:
                        await context.bot.send_photo(chat_id=chat_id, photo=f)
            else:
                # Audio fayllar karusel bo'lmaydi, lekin ehtiyot uchun alohida yuboramiz
                audio_results = [r for r in valid_results if r["media_type"] == "audio"]
                media_results = [r for r in valid_results if r["media_type"] != "audio"]

                for r in audio_results:
                    with open(r["path"], "rb") as f:
                        await context.bot.send_audio(chat_id=chat_id, audio=f)

                for i in range(0, len(media_results), 10):
                    chunk = media_results[i : i + 10]
                    media = []
                    open_files = []
                    for r in chunk:
                        f = open(r["path"], "rb")
                        open_files.append(f)
                        if r["media_type"] == "video":
                            media.append(InputMediaVideo(f))
                        else:
                            media.append(InputMediaPhoto(f))
                    await context.bot.send_media_group(chat_id=chat_id, media=media)
                    for f in open_files:
                        f.close()

            increment_user_count(user_id, by=len(valid_results))

            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=status_message_id, text=t(user_id, "done")
            )

    except yt_dlp.utils.DownloadError as e:
        logger.error(f"Yuklab olishda xatolik: {e}")
        await context.bot.edit_message_text(
            chat_id=chat_id, message_id=status_message_id, text=t(user_id, "error")
        )
    except Exception as e:
        logger.error(f"Kutilmagan xatolik: {e}")
        await context.bot.edit_message_text(
            chat_id=chat_id, message_id=status_message_id, text=t(user_id, "unexpected_error")
        )


# ------------------------------------------------------------------
# BOTNI ISHGA TUSHIRISH
# ------------------------------------------------------------------

def main():
    if BOT_TOKEN == "SIZNING_TOKENINGIZ_BU_YERGA":
        print(
            "❗ BOT_TOKEN o'rnatilmagan. Muhit o'zgaruvchisi sifatida sozlang:\n"
            "   export BOT_TOKEN='sizning_tokeningiz'\n"
            "   python bot.py"
        )
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("language", language_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot ishga tushdi...")
    app.run_polling()


if __name__ == "__main__":
    main()
