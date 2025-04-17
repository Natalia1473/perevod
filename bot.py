#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import tempfile
import logging

from pydub import AudioSegment
from telegram import Update
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext
import openai

# Переменные окружения (задать в Render -> Environment)
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
RENDER_EXTERNAL_URL = os.environ["RENDER_EXTERNAL_URL"]  # например, your-bot.onrender.com
PORT = int(os.environ.get("PORT", 8443))

# Инициализируем OpenAI
openai.api_key = OPENAI_API_KEY

# Логирование
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)


def transcribe_voice(path: str) -> str:
    """Отправляет аудио на Whisper и возвращает текст."""
    with open(path, "rb") as audio_file:
        resp = openai.Audio.transcribe(model="whisper-1", file=audio_file)
    return resp["text"]


def handle_voice(update: Update, context: CallbackContext):
    """Скачивает голосовое или аудио, конвертирует, расшифровывает и отправляет текст."""
    voice = update.message.voice or update.message.audio
    file_id = voice.file_id
    tg_file = context.bot.get_file(file_id)

    # Сохраняем во временный ogg-файл
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as ogg_f:
        tg_file.download(custom_path=ogg_f.name)
        ogg_path = ogg_f.name

    # Конвертируем в wav (требуется ffmpeg)
    wav_path = ogg_path.replace(".ogg", ".wav")
    AudioSegment.from_file(ogg_path).export(wav_path, format="wav")

    # Расшифровка и отправка
    text = transcribe_voice(wav_path)
    update.message.reply_text(text)

    # Чистим временные файлы
    os.remove(ogg_path)
    os.remove(wav_path)


def main():
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(MessageHandler(Filters.voice | Filters.audio, handle_voice))

    # Запускаем webhook
    updater.start_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TELEGRAM_TOKEN,
        webhook_url=f"https://{RENDER_EXTERNAL_URL}/{TELEGRAM_TOKEN}"
    )

    logging.info("Bot started via webhook")
    updater.idle()


if __name__ == "__main__":
    main()
