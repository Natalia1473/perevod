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
import openai
from telegram.error import TelegramError

# В requirements.txt:
# deepgram-sdk==2.12.0
# openai==0.27.0
# python-telegram-bot==13.14
# pydub==0.25.1

# Переменные окружения
TELEGRAM_TOKEN      = os.environ["TELEGRAM_TOKEN"]
DEEPGRAM_API_KEY    = os.environ["DEEPGRAM_API_KEY"]
OPENAI_API_KEY      = os.environ.get("OPENAI_API_KEY")  # для восстановления пунктуации через GPT
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "").replace("https://", "").replace("http://", "")
PORT                = int(os.environ.get("PORT", "443"))

# Логирование
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logging.info(f"Env -> URL={RENDER_EXTERNAL_URL!r}, PORT={PORT!r}")

# Инициализация Deepgram и OpenAI
dg_client = Deepgram(DEEPGRAM_API_KEY)
if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY
else:
    logging.warning("OPENAI_API_KEY not set: punctuation restoration will be skipped.")

async def _transcribe_with_deepgram(path: str) -> str:
    with open(path, 'rb') as f:
        data = f.read()
    source  = {'buffer': data, 'mimetype': 'audio/wav'}
    options = {'punctuate': True, 'language': 'ru'}
    resp = await dg_client.transcription.prerecorded(source, options)
    channels = resp.get('results', {}).get('channels', [])
    if channels and channels[0].get('alternatives'):
        return channels[0]['alternatives'][0].get('transcript', '').strip()
    return ""

def transcribe_voice(path: str) -> str:
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_transcribe_with_deepgram(path))
    finally:
        loop.close()

def punctuate_text(text: str) -> str:
    if not OPENAI_API_KEY:
        return text
    prompt = (
        "Расставь, пожалуйста, знаки препинания и исправь регистр в этом тексте на русском языке: "
        f"{text}"
    )
    resp = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are an expert punctuation restorer for Russian text."},
            {"role": "user", "content": prompt}
        ],
        temperature=0
    )
    return resp.choices[0].message.content.strip()

def handle_voice(update: Update, context: CallbackContext):
    ogg_path = wav_path = None
    try:
        tg_file = context.bot.get_file((update.message.voice or update.message.audio).file_id)
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as ogg:
            tg_file.download(custom_path=ogg.name)
            ogg_path = ogg.name
        wav_path = ogg_path.replace('.ogg', '.wav')
        AudioSegment.from_file(ogg_path).export(wav_path, format='wav')

        text = transcribe_voice(wav_path)
        if not text:
            return update.message.reply_text("Не удалось распознать речь.")

        # Восстанавливаем пунктуацию через OpenAI (если ключ задан)
        punctuated = punctuate_text(text)
        update.message.reply_text(punctuated)

    except TelegramError as te:
        logging.error(f"Telegram error: {te}")
    except Exception as e:
        logging.error(f"Error in handle_voice: {e}")
        update.message.reply_text("Ошибка при обработке аудио.")
    finally:
        for p in (ogg_path, wav_path):
            if p and os.path.exists(p):
                os.remove(p)

if __name__ == '__main__':
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(MessageHandler(Filters.voice | Filters.audio, handle_voice))

    webhook = f"https://{RENDER_EXTERNAL_URL}/{TELEGRAM_TOKEN}"
    logging.info(f"Setting webhook: {webhook}")
    updater.start_webhook(listen='0.0.0.0', port=PORT, url_path=TELEGRAM_TOKEN, webhook_url=webhook)
    logging.info("Bot started via webhook")
    updater.idle()
