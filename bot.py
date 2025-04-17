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
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")  # без протокола, напр.: my-bot.onrender.com
PORT = int(os.environ.get("PORT", "443"))

# Обрезаем префиксы из URL
if RENDER_EXTERNAL_URL:
    RENDER_EXTERNAL_URL = RENDER_EXTERNAL_URL.replace("https://", "").replace("http://", "")

# Логирование
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logging.info(
    f"Env -> RENDER_EXTERNAL_URL={RENDER_EXTERNAL_URL!r}, PORT={PORT!r}, "
    f"TOKEN set={bool(TELEGRAM_TOKEN)}, DEEPGRAM_API_KEY set={bool(DEEPGRAM_API_KEY)}"
)

# Инициализация Deepgram и Translator
# Deepgram SDK v2:
dg_client = Deepgram(DEEPGRAM_API_KEY)
# Google Translate:
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
    """Скачивает голосовое, конвертирует, транскрибирует и переводит. Возвращает и оригинал, и перевод."""
    ogg_path = wav_path = None
    try:
        voice = update.message.voice or update.message.audio
        tg_file = context.bot.get_file(voice.file_id)

        # Сохраняем ogg
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as ogg_f:
            tg_file.download(custom_path=ogg_f.name)
            ogg_path = ogg_f.name

        # Конвертируем в wav
        wav_path = ogg_path.replace(".ogg", ".wav")
        AudioSegment.from_file(ogg_path).export(wav_path, format="wav")

       orig_text = transcribe_voice(wav_path)
if not orig_text:
    update.message.reply_text("Не удалось распознать речь в этом аудио.")
    return

orig_text = orig_text.strip()
logging.info(f"Original transcript: {orig_text}")

translated = translator.translate(orig_text, src='ru', dest='en').text
logging.info(f"Translated text: {translated}")

response = f"Original: {orig_text}\nTranslation: {translated}"
update.message.reply_text(response)

        # Отправляем оба текста
        response = f"Original: {orig_text}\nTranslation: {translated}"
        update.message.reply_text(response)

    except TelegramError as te:
        logging.error(f"Telegram error: {te}")
    except Exception as e:
        logging.error(f"Error during transcription/translation: {e}")
        try:
            update.message.reply_text("Ошибка при обработке аудио.")
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

    # Формируем webhook URL
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
