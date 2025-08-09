#!/usr/bin/env python3
"""
Главный файл NFT Gift Bot
Модульная архитектура для Telegram бота работы с NFT-подарками
"""

import asyncio
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# Импорты модулей
from config import TOKEN, validate_config
from handlers.business import router as business_router
from handlers.admin import router as admin_router
from handlers.user import router as user_router
from handlers.mailing import router as mailing_router
from handlers.inline import router as inline_router
from handlers.callbacks import router as callbacks_router

# Утилиты
from utils.file_utils import load_settings, save_settings, migrate_from_json_files
from utils.automation import start_automation_tasks
from utils.logging import setup_logging

def setup_bot() -> tuple[Bot, Dispatcher]:
    """Настройка бота и диспетчера"""
    bot = Bot(
        token=TOKEN, 
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()
    
    # Регистрируем роутеры
    dp.include_router(business_router)
    dp.include_router(admin_router)
    dp.include_router(user_router)
    dp.include_router(mailing_router)
    dp.include_router(inline_router)
    dp.include_router(callbacks_router)
    
    return bot, dp

async def startup(bot: Bot):
    """Действия при запуске бота"""
    logging.info("🚀 Запуск NFT Gift Bot...")
    
    # Инициализируем базу данных и выполняем миграцию
    try:
        migrate_from_json_files()
        logging.info("✅ Миграция данных завершена")
    except Exception as e:
        logging.error(f"❌ Ошибка миграции данных: {e}")
    
    # Загружаем настройки
    load_settings()
    
    # Отправляем уведомление админу о запуске
    try:
        from config import get_main_admin_id
        await bot.send_message(
            get_main_admin_id(),
            "🤖 <b>NFT Gift Bot запущен!</b>\n\n"
            f"📅 Время запуска: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            "✅ Все модули загружены\n"
            "🔄 Автоматизация активна\n"
            "💾 База данных инициализирована",
            parse_mode="HTML"
        )
    except Exception as e:
        logging.error(f"Ошибка отправки уведомления о запуске: {e}")

async def shutdown(bot: Bot):
    """Действия при остановке бота"""
    logging.info("🛑 Остановка NFT Gift Bot...")
    
    # Сохраняем настройки
    save_settings()
    
    # Отправляем уведомление админу об остановке
    try:
        from config import get_main_admin_id
        await bot.send_message(
            get_main_admin_id(),
            "🛑 <b>NFT Gift Bot остановлен!</b>\n\n"
            f"📅 Время остановки: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            "💾 Настройки сохранены",
            parse_mode="HTML"
        )
    except Exception as e:
        logging.error(f"Ошибка отправки уведомления об остановке: {e}")

async def main():
    """Главная функция"""
    # Проверяем конфигурацию
    if not validate_config():
        logging.error("❌ Ошибка конфигурации. Завершение работы.")
        return
    
    # Настраиваем логирование
    setup_logging()
    
    # Создаем бота и диспетчер
    bot, dp = setup_bot()
    
    # Настраиваем обработчики запуска и остановки
    dp.startup.register(startup)
    dp.shutdown.register(shutdown)
    
    try:
        # Запускаем автоматизацию
        automation_task = asyncio.create_task(start_automation_tasks(bot))
        
        # Запускаем бота
        logging.info("🎯 Запуск поллинга бота...")
        await dp.start_polling(bot)
        
    except KeyboardInterrupt:
        logging.info("📱 Получен сигнал остановки (Ctrl+C)")
    except Exception as e:
        logging.error(f"❌ Критическая ошибка: {e}")
    finally:
        # Останавливаем автоматизацию
        automation_task.cancel()
        try:
            await automation_task
        except asyncio.CancelledError:
            pass
        
        # Закрываем сессию бота
        await bot.session.close()
        logging.info("✅ Бот остановлен")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен пользователем")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}") 