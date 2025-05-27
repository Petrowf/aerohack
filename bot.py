import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram import F
import config
import vosk_transcriber
import openai_analyzer
import weeek_integration

conf = config.MeetingSecretaryConfig.from_env()
vosk_tr = vosk_transcriber.VoskTranscriber(conf.vosk)
#weeek_int = weeek_integration.WeeekIntegration(conf.weeek)
openai_an = openai_analyzer.OpenAIAnalyzer(conf.openai)

print(conf.vosk.model_path)
# Включаем логирование, чтобы не пропустить важные сообщения
logging.basicConfig(level=logging.INFO)
# Объект бота
bot = Bot(token="7944216029:AAF8k7RBHJydyzeQcLUjobz0_CsZxoHMayo")
# Диспетчер
dp = Dispatcher()

# Хэндлер на команду /start
@dp.message(F.audio | F.voice)
async def cmd_start(message: types.Message):
    await message.answer("Получено голосовое сообщение")
    voice_file = await bot.get_file(message.voice.file_id)
    await bot.download_file(voice_file.file_path, "audio.mp3")
    transcribed_audio = vosk_tr.transcribe_from_file("audio.mp3")
    await message.answer(transcribed_audio)
    analyzed_text = openai_an.analyze_transcript(transcribed_audio)
   # weeek_int.create_tasks_from_analysis(analyzed_text, 1)
    print(analyzed_text)


# Запуск процесса поллинга новых апдейтов
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())