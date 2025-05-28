import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile

import config
# import vosk_transcriber
# import openai_analyzer
# import weeek_integration
from dotenv import load_dotenv
import os
# import openai_transcriber3
import requests
from aiogram.fsm.state import State
from aiogram.utils.keyboard import InlineKeyboardBuilder
from urllib.parse import urlencode
from meeting_secretary import TechnicalMeetingSecretary

load_dotenv()

conf = config.MeetingSecretaryConfig.from_env()
secretary = TechnicalMeetingSecretary(conf)
# vosk_tr = vosk_transcriber.VoskTranscriber(conf.vosk)
# weeek_int = weeek_integration.WeeekIntegration(conf.weeek)
# openai_an = openai_analyzer.OpenAIAnalyzer(conf.openai)
# openai_tr = openai_transcriber.OpenAITranscriber(conf.openai)


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
# Объект бота
bot = Bot(token=os.getenv("BOT_TOKEN"))
# Диспетчер
dp = Dispatcher()

wait_url = State()

# Хэндлер на команду /start
@dp.message(F.audio | F.voice)
async def cmd_start(message: types.Message):
    await message.answer("Получено голосовое сообщение")
    if message.voice:
        voice_file = await bot.get_file(message.voice.file_id)
        await bot.download_file(voice_file.file_path, "audio.mp3")
    elif message.audio:
        try:
            audio_file = await bot.get_file(message.audio.file_id)
            await bot.download_file(audio_file.file_path, "audio.mp3")
        except:
            builder = InlineKeyboardBuilder()
            builder.add(types.InlineKeyboardButton(
                text="Отправить ссылку",
                callback_data="wait_url")
            )
            await message.answer("Файл слишком большой, допускаются файлы размером менее 20МБ, попробуйте сжать его или отправьте ссылку на файл на Яндекс диске", reply_markup=builder.as_markup())
            return
    try:
        processing_time = secretary.process_meeting_audio("audio.mp3")
        await message.answer(f"Обработка завершена, затраченное время: {processing_time}")
        protocol = FSInputFile("Протокол_совещания.docx")
        await message.answer_document(protocol)
    except Exception as e:
        await message.answer(f"Произошла ошибка: {e}")
    # transcribed_audio = openai_tr.transcribe_from_file("audio.mp3")
    # analyzed_text = openai_an.analyze_transcript(transcribed_audio)
    # weeek_int.create_tasks_from_analysis(analyzed_text)

@dp.message(wait_url)
async def get_url(message: types.Message):
    try:
        base_url = 'https://cloud-api.yandex.net/v1/disk/public/resources/download?'
        url = message.text
        final_url = base_url + urlencode(dict(public_key=url))
        response = requests.get(final_url)
        download_url = response.json()['href']
        await message.answer("Началась загрузка")
        download_response = requests.get(download_url)
        with open('downloaded_audio.mp3', 'wb') as f:
            f.write(download_response.content)
        await message.answer("Загрузка завершена, началась обработка")
        try:
            processing_time = secretary.process_meeting_audio("downloaded_audio.mp3")
            await message.answer(f"Обработка завершена, затраченное время: {processing_time} секунд")
            protocol = FSInputFile("Протокол_совещания.docx")
            await message.answer_document(protocol)
        except Exception as e:
            await message.answer(f"Произошла ошибка: {e}")
    except:
        await message.answer("Что-то пошло не так")

@dp.callback_query(F.data == "wait_url")
async def wait_button_response(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Ожидаю ссылку")
    await state.set_state(wait_url)
    await state.clear()


# Запуск процесса поллинга новых апдейтов
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())