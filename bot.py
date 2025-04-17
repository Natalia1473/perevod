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
from telegram.error import TelegramError

# Требуется установить зависимость: pip install deepgram-sdk

# Переменные окружения (Render -> Environment, Web Service)
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY")  # ключ Deepgram
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")  # без https://, напр.: my-bot.onrender.com
PORT = int(os.environ.get("PORT", "443"))

# Удаляем префиксы из URL, если есть
if RENDER_EXTERNAL_URL:
    RENDER_EXTERNAL_URL = RENDER_EXTERNAL_URL.replace("https://", "").replace("http://", "")

# Логирование
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.info(f"Env vars -> RENDER_EXTERNAL_URL={RENDER_EXTERNAL_URL!r}, PORT={PORT!r}, TELEGRAM_TOKEN set={bool(TELEGRAM_TOKEN)}, DEEPGRAM_API_KEY set={bool(DEEPGRAM_API_KEY)}")

# Инициализация Deepgram SDK
dg_client = Deepgram(DEEPGRAM_API_KEY)

async def _transcribe_with_deepgram(path: str) -> str:
    # Читаем файл и готовим источник для API
    audio_bytes = open(path, 'rb').read()
    source = {'buffer': audio_bytes, 'mimetype': 'audio/wav'}
    # Опции: автоматическая пунктуация и распознавание языка (auto)
    options = {'punctuate': True}
    response = await dg_client.transcription.prerecorded(source, options)
    # Текст в первом канале, первой альтернативе
    return response['results']['channels'][0]['alternatives'][0]['transcript']


def transcribe_voice(path: str) -> str:
    """Синхронная обёртка для асинхронного вызова Deepgram."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_transcribe_with_deepgram(path))
    finally:
        loop.close()


def handle_voice(update: Update, context: CallbackContext):
    """Скачивает голосовое, конвертирует, транскрибирует и отвечает текстом."""
    try:
        voice = update.message.voice or update.message.audio
        tg_file = context.bot.get_file(voice.file_id)

        # Сохраняем ogg во временный файл
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as ogg_f:
            tg_file.download(custom_path=ogg_f.name)
            ogg_path = ogg_f.name

        # Конвертируем в wav
        wav_path = ogg_path.replace(".ogg", ".wav")
        AudioSegment.from_file(ogg_path).export(wav_path, format="wav")

        # Транскрибируем через Deepgram
        text = transcribe_voice(wav_path)
        update.message.reply_text(text)

    except TelegramError as te:
        logging.error(f"Telegram error: {te}")
    except Exception as e:
        logging.error(f"Error in transcription: {e}")
        try:
            update.message.reply_text("Ошибка при распознавании аудио.")
        except Exception:
            pass
    finally:
        # Удаляем временные файлы
        for path in (locals().get('ogg_path'), locals().get('wav_path')):
            if path and os.path.exists(path):
                os.remove(path)


def main():
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(MessageHandler(Filters.voice | Filters.audio, handle_voice))

    # Полный URL webhook
    webhook_url = f"https://{RENDER_EXTERNAL_URL}/{TELEGRAM_TOKEN}"
    logging.info(f"Setting webhook: {webhook_url}")

    # Запуск webhook
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
