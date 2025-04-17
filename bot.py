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

# Убедись, что в requirements.txt указаны:
# deepgram-sdk==2.12.0
# googletrans==4.0.0-rc1

# Переменные окружения (Render -> Environment)
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY")
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")  # без http://
PORT = int(os.environ.get("PORT", "443"))

# Обрезаем протокол, если случайно добавили
if RENDER_EXTERNAL_URL:
    RENDER_EXTERNAL_URL = RENDER_EXTERNAL_URL.replace("https://", "").replace("http://", "")

# Логирование
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logging.info(
    f"Env -> RENDER_EXTERNAL_URL={RENDER_EXTERNAL_URL!r}, PORT={PORT!r}, "
    f"TOKEN set={bool(TELEGRAM_TOKEN)}, DEEPGRAM_API_KEY set={bool(DEEPGRAM_API_KEY)}"
)

# Инициируем Deepgram и Translator
dg_client = Deepgram(DEEPGRAM_API_KEY)
translator = Translator()

async def _transcribe_with_deepgram(path: str) -> str:
    """Асинхронная транскрипция через Deepgram."""
    audio_bytes = open(path, 'rb').read()
    source = {'buffer': audio_bytes, 'mimetype': 'audio/wav'}
    options = {'punctuate': True}
    response = await dg_client.transcription.prerecorded(source, options)
    return response['results']['channels'][0]['alternatives'][0]['transcript']


def transcribe_voice(path: str) -> str:
    """Синхронная обёртка для Deepgram SDK."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_transcribe_with_deepgram(path))
    finally:
        loop.close()


def handle_voice(update: Update, context: CallbackContext):
    """Скачивает голосовое, конвертирует, транскрибирует и переводит."""
    ogg_path = wav_path = None
    try:
        voice = update.message.voice or update.message.audio
        tg_file = context.bot.get_file(voice.file_id)

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as ogg_f:
            tg_file.download(custom_path=ogg_f.name)
            ogg_path = ogg_f.name

        wav_path = ogg_path.replace(".ogg", ".wav")
        AudioSegment.from_file(ogg_path).export(wav_path, format="wav")

        orig_text = transcribe_voice(wav_path)
        translated = translator.translate(orig_text, dest='en').text
        update.message.reply_text(translated)

    except TelegramError as te:
        logging.error(f"Telegram error: {te}")
    except Exception as e:
        logging.error(f"Error in transcription/translation: {e}")
        try:
            update.message.reply_text("Ошибка при распознавании или переводе аудио.")
        except Exception:
            pass
    finally:
        for path in (ogg_path, wav_path):
            if path and os.path.exists(path):
                os.remove(path)


def main():
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(MessageHandler(Filters.voice | Filters.audio, handle_voice))

    webhook_url = f"https://{RENDER_EXTERNAL_URL}/{TELEGRAM_TOKEN}"
    logging.info(f"Setting webhook: {webhook_url}")

    updater.start_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TELEGRAM_TOKEN,
        webhook_url=webhook_url
    )

    logging.info("Bot started via webhook")
    updater.idle()


if __name__ == "__main__":
    main()
