#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import tempfile
import logging

from pydub import AudioSegment
from telegram import Update
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext
import openai

# Переменные окружения (Render -> Environment)
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
# Только домен, без протокола, напр.: your-bot.onrender.com
RENDER_EXTERNAL_URL = os.environ["RENDER_EXTERNAL_URL"]
PORT = int(os.environ.get("PORT", "8443"))

# Удаляем возможные префиксы
RENDER_EXTERNAL_URL = RENDER_EXTERNAL_URL.replace("https://", "").replace("http://", "")

openai.api_key = OPENAI_API_KEY

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)

def transcribe_voice(path: str) -> str:
    """Отправляет аудио в Whisper и возвращает текст."""
    with open(path, "rb") as audio_file:
        resp = openai.Audio.transcribe(model="whisper-1", file=audio_file)
    return resp["text"]

def handle_voice(update: Update, context: CallbackContext):
    """Скачивает голосовое, конвертирует и отправляет расшифровку."""
    voice = update.message.voice or update.message.audio
    tg_file = context.bot.get_file(voice.file_id)

    # сохраняем ogg
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as ogg_f:
        tg_file.download(custom_path=ogg_f.name)
        ogg_path = ogg_f.name

    # конвертируем в wav
    wav_path = ogg_path.replace(".ogg", ".wav")
    AudioSegment.from_file(ogg_path).export(wav_path, format="wav")

    # расшифровка
    text = transcribe_voice(wav_path)
    update.message.reply_text(text)

    # удаляем временные файлы
    os.remove(ogg_path)
    os.remove(wav_path)

def main():
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(MessageHandler(Filters.voice | Filters.audio, handle_voice))

    # запускаем локальный webhook-сервер
    updater.start_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TELEGRAM_TOKEN
    )

    # вручную настраиваем webhook
    webhook_url = f"https://{RENDER_EXTERNAL_URL}/{TELEGRAM_TOKEN}"
    logging.info(f"Setting webhook: {webhook_url}")
    updater.bot.set_webhook(webhook_url)

    logging.info("Bot started via webhook")
    updater.idle()

if __name__ == "__main__":
    main()
