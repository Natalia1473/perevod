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

# В requirements.txt:
# deepgram-sdk==2.12.0
# python-telegram-bot==13.14
# pydub==0.25.1

# Переменные окружения (Render -> Environment)
TELEGRAM_TOKEN      = os.environ["TELEGRAM_TOKEN"]
DEEPGRAM_API_KEY    = os.environ["DEEPGRAM_API_KEY"]
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "").replace("https://", "").replace("http://", "")
PORT                = int(os.environ.get("PORT", "443"))

# Логирование
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logging.info(f"Env -> URL={RENDER_EXTERNAL_URL!r}, PORT={PORT!r}")

# Инициализация Deepgram SDK v2
dg_client = Deepgram(DEEPGRAM_API_KEY)

async def _transcribe_with_deepgram(path: str) -> str:
    """Асинхронная транскрипция через Deepgram с указанием русского языка."""
    with open(path, 'rb') as f:
        audio_bytes = f.read()
    source  = {'buffer': audio_bytes, 'mimetype': 'audio/wav'}
    options = {'punctuate': True, 'language': 'ru'}
    resp = await dg_client.transcription.prerecorded(source, options)
    channels = resp.get('results', {}).get('channels', [])
    if not channels or not channels[0].get('alternatives'):
        return ""
    return channels[0]['alternatives'][0].get('transcript', "").strip()

def transcribe_voice(path: str) -> str:
    """Синхронная обёртка для асинхронного Deepgram."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_transcribe_with_deepgram(path))
    finally:
        loop.close()


def handle_voice(update: Update, context: CallbackContext):
    """Обрабатывает голосовое: транскрипция речи на русском языке."""
    ogg_path = wav_path = None
    try:
        voice   = update.message.voice or update.message.audio
        tg_file = context.bot.get_file(voice.file_id)

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as ogg_f:
            tg_file.download(custom_path=ogg_f.name)
            ogg_path = ogg_f.name

        wav_path = ogg_path.replace(".ogg", ".wav")
        AudioSegment.from_file(ogg_path).export(wav_path, format="wav")

        text = transcribe_voice(wav_path)
        if not text:
            update.message.reply_text("Не удалось распознать речь.")
        else:
            update.message.reply_text(text)

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
    dp      = updater.dispatcher
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


if __name__ == '__main__':
    main()
