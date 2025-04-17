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

# Загрузка переменных окружения
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY")
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "")  # без протокола
PORT = int(os.environ.get("PORT", "443"))

# Чистим префиксы
RENDER_EXTERNAL_URL = RENDER_EXTERNAL_URL.replace("https://", "").replace("http://", "")

# Логирование
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logging.info(f"Env -> RENDER_EXTERNAL_URL={RENDER_EXTERNAL_URL!r}, PORT={PORT!r}, TOKEN set={bool(TELEGRAM_TOKEN)}, DEEPGRAM_API_KEY set={bool(DEEPGRAM_API_KEY)}")

# Инициализация клиентов
dg_client = Deepgram(DEEPGRAM_API_KEY)
translator = Translator()

async def _transcribe_with_deepgram(path: str) -> str:
    """Асинхронная транскрипция через Deepgram с автоопределением языка."""
    try:
        with open(path, 'rb') as f:
            audio_bytes = f.read()
        source = {'buffer': audio_bytes, 'mimetype': 'audio/wav'}
        options = {'punctuate': True, 'language': 'auto'}
        response = await dg_client.transcription.prerecorded(source, options)
        # безопасно пробуем извлечь текст
        chan = response.get('results', {}).get('channels', [])
        if not chan:
            return ''
        alt = chan[0].get('alternatives', [])
        if not alt:
            return ''
        text = alt[0].get('transcript') or ''
        return text
    except Exception as e:
        logging.error(f"Deepgram error: {e}")
        return ''

def transcribe_voice(path: str) -> str:
    """Синхронная обертка для асинхронного вызова Deepgram."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_transcribe_with_deepgram(path))
    finally:
        loop.close()

def handle_voice(update: Update, context: CallbackContext):
    """Обрабатывает голосовое сообщение: транскрипция и перевод."""
    ogg_path = wav_path = None
    try:
        voice = update.message.voice or update.message.audio
        tg_file = context.bot.get_file(voice.file_id)

        # сохраняем ogg
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as ogg_f:
            tg_file.download(custom_path=ogg_f.name)
            ogg_path = ogg_f.name

        # конвертируем в wav
        wav_path = ogg_path.replace(".ogg", ".wav")
        AudioSegment.from_file(ogg_path).export(wav_path, format="wav")

        # транскрибируем
        orig_text = transcribe_voice(wav_path).strip()
        if not orig_text:
            update.message.reply_text("Не удалось распознать речь.")
            return
        logging.info(f"Transcript: {orig_text}")

        # переводим на английский
        translated = translator.translate(orig_text, dest='en').text.strip()
        update.message.reply_text(translated)

    except TelegramError as te:
        logging.error(f"Telegram error: {te}")
    except Exception as e:
        logging.error(f"Error in handle_voice: {e}")
        try:
            update.message.reply_text("Ошибка при обработке аудио.")
        except Exception:
            pass
    finally:
        # удаляем файлы
        for path in (ogg_path, wav_path):
            if path and os.path.exists(path):
                os.remove(path)


def main():
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(MessageHandler(Filters.voice | Filters.audio, handle_voice))

    # формируем и устанавливаем webhook
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
