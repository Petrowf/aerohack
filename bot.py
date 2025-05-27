import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters.command import Command
from aiogram import F

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


# Запуск процесса поллинга новых апдейтов
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())