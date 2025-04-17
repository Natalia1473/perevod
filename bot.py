#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import tempfile
import logging
import asyncio

from pydub import AudioSegment
from telegram import Update
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext
from deepgram import Deepgram
from googletrans import Translator
from telegram.error import TelegramError

# В requirements.txt:
# deepgram-sdk==2.12.0
# googletrans==4.0.0-rc1
# python-telegram-bot==13.14
# pydub==0.25.1

# Переменные окружения
TELEGRAM_TOKEN      = os.environ["TELEGRAM_TOKEN"]
DEEPGRAM_API_KEY    = os.environ["DEEPGRAM_API_KEY"]
RENDER_EXTERNAL_URL = os.environ["RENDER_EXTERNAL_URL"].replace("https://", "").replace("http://", "")
PORT                = int(os.environ.get("PORT", "443"))

# Логирование
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)

# Инициализация Deepgram и переводчика
dg_client  = Deepgram(DEEPGRAM_API_KEY)
translator = Translator()

async def _transcribe_with_deepgram(path: str) -> str:
    """Асинхронная транскрипция через Deepgram, принудительно для русского."""
    with open(path, 'rb') as f:
        audio_bytes = f.read()
    source  = {'buffer': audio_bytes, 'mimetype': 'audio/wav'}
    options = {
        'punctuate': True,
        'language': 'ru'        # ← вот здесь принудительно указываем русский
    }
    resp = await dg_client.transcription.prerecorded(source, options)
    # безопасно достаём текст
    channels = resp.get('results', {}).get('channels', [])
    if not channels or not channels[0].get('alternatives'):
        return ""
    return channels[0]['alternatives'][0].get('transcript', "")

def transcribe_voice(path: str) -> str:
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_transcribe_with_deepgram(path))
    finally:
        loop.close()

def handle_voice(update: Update, context: CallbackContext):
    """Обработка голосового: транскрипция (русский) → перевод (английский)."""
    ogg_path = wav_path = None
    try:
        tg_file = context.bot.get_file((update.message.voice or update.message.audio).file_id)

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as ogg:
            tg_file.download(custom_path=ogg.name)
            ogg_path = ogg.name

        wav_path = ogg_path.replace(".ogg", ".wav")
        AudioSegment.from_file(ogg_path).export(wav_path, format="wav")

        orig = transcribe_voice(wav_path).strip()
        if not orig:
            return update.message.reply_text("Не удалось распознать речь.")

        translated = translator.translate(orig, dest='en').text.strip()
        update.message.reply_text(translated)

    except TelegramError as te:
        logging.error(f"Telegram error: {te}")
    except Exception as e:
        logging.error(f"Error: {e}")
        update.message.reply_text("Ошибка при обработке аудио.")
    finally:
        for p in (ogg_path, wav_path):
            if p and os.path.exists(p):
                os.remove(p)

def main():
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(MessageHandler(Filters.voice | Filters.audio, handle_voice))

    webhook_url = f"https://{RENDER_EXTERNAL_URL}/{TELEGRAM_TOKEN}"
    logging.info(f"Setting webhook: {webhook_url}")
    updater.start_webhook(
        listen="0.0.0.0", port=PORT,
        url_path=TELEGRAM_TOKEN, webhook_url=webhook_url
    )
    logging.info("Bot started")
    updater.idle()

if __name__ == "__main__":
    main()
