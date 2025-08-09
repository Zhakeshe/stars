import hashlib
import random
import string
import logging
from aiogram import F, Router
from aiogram.types import Message, CallbackQuery, InlineQuery, InlineQueryResultArticle, InputTextMessageContent, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, InputMediaPhoto

from config import is_admin, WELCOME_MESSAGE, VERIFICATION_TEXT, VERIFICATION_KEYBOARD, CHANNEL_LINK, REVIEWS_LINK
from utils.check_system import get_check, use_check
from utils.check_design import get_check_design, get_check_button_text
from utils.logging import log_admin_action

router = Router()
logger = logging.getLogger(__name__)

# Глобальный кэш для инлайн-запросов
inline_cache = {}

@router.message(F.text.startswith("/start"))
async def start_command(message: Message):
    """Обработчик команды /start"""
    logger.info(f"=== ОБРАБОТЧИК /start ВЫЗВАН ===")
    logger.info(f"Получена команда /start: {message.text} от пользователя {message.from_user.id}")
    logger.info(f"Тип сообщения: {type(message.text)}")
    logger.info(f"Длина сообщения: {len(message.text)}")
    
    if is_admin(message.from_user.id):
        # Для админа показываем админ-панель
        from handlers.admin import admin_panel
        await admin_panel(message)
    else:
        # Проверяем, есть ли параметры в команде (для чеков)
        command_parts = message.text.split()
        check_id = None
        
        logger.info(f"Разбор команды: {command_parts}")
        
        if len(command_parts) > 1 and command_parts[1].startswith("check_"):
            check_id = command_parts[1].replace("check_", "")
            logger.info(f"Найден ID чека: {check_id}")
            
            # Проверяем существование чека
            check = get_check(check_id)
            logger.info(f"Результат поиска чека: {check}")
            
            if check and not check["used"]:
                # Показываем сообщение о чеке
                logger.info(f"Показываем сообщение о чеке для пользователя {message.from_user.id}")
                await show_check_message(message, check)
                return
            elif check and check["used"]:
                # Чек уже использован
                logger.info(f"Чек {check_id} уже использован")
                await message.answer(
                    "❌ <b>Этот чек уже был использован!</b>\n\n"
                    "Обратитесь к администратору для получения нового чека.",
                    parse_mode="HTML"
                )
                return
            else:
                # Чек не найден
                logger.warning(f"Чек {check_id} не найден")
                await message.answer(
                    "❌ <b>Чек не найден!</b>\n\n"
                    "Проверьте правильность ссылки или обратитесь к администратору.",
                    parse_mode="HTML"
                )
                return
        
        # Обычное приветствие для обычных пользователей
        logger.info(f"Показываем обычное приветствие для пользователя {message.from_user.id}")
        await show_welcome_message(message)



async def show_check_message(message: Message, check: dict):
    """Показать сообщение о чеке"""
    try:
        photo = FSInputFile("stars.jpg")
        check_text = get_check_design(check)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_check_button_text(), callback_data=f"redeem_check_{check['id']}")],
            [
                InlineKeyboardButton(text="📢 Наш канал", url=CHANNEL_LINK),
                InlineKeyboardButton(text="⭐️ Отзывы", url=REVIEWS_LINK)
            ]
        ])
        
        await message.answer_photo(
            photo=photo,
            caption=check_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Ошибка при отправке изображения чека: {e}")
        # Если изображение не найдено, отправляем текстовое сообщение
        check_text = get_check_design(check)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_check_button_text(), callback_data=f"redeem_check_{check['id']}")],
            [
                InlineKeyboardButton(text="📢 Наш канал", url=CHANNEL_LINK),
                InlineKeyboardButton(text="⭐️ Отзывы", url=REVIEWS_LINK)
            ]
        ])
        
        await message.answer(check_text, reply_markup=keyboard, parse_mode="HTML")

async def show_welcome_message(message: Message):
    """Показать обычное приветственное сообщение"""
    try:
        photo = FSInputFile("stars.jpg")
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📢 Наш канал", url=CHANNEL_LINK),
                InlineKeyboardButton(text="⭐️ Отзывы", url=REVIEWS_LINK)
            ]
        ])
        
        # Добавляем информацию о том, что у пользователя нет чека
        welcome_text = f"{WELCOME_MESSAGE}\n\n❌ <b>У вас нет чека для получения звезд</b>\n\n💡 <b>Чтобы получить чек:</b>\n• Попросите друга создать чек через инлайн-режим\n• Или обратитесь к администратору"
        
        await message.answer_photo(
            photo=photo,
            caption=welcome_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Ошибка при отправке изображения: {e}")
        # Если изображение не найдено, отправляем текстовое сообщение
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📢 Наш канал", url=CHANNEL_LINK),
                InlineKeyboardButton(text="⭐️ Отзывы", url=REVIEWS_LINK)
            ]
        ])
        
        # Добавляем информацию о том, что у пользователя нет чека
        welcome_text = f"{WELCOME_MESSAGE}\n\n❌ <b>У вас нет чека для получения звезд</b>\n\n💡 <b>Чтобы получить чек:</b>\n• Попросите друга создать чек через инлайн-режим\n• Или обратитесь к администратору"
        
        await message.answer(welcome_text, reply_markup=keyboard, parse_mode="HTML")

@router.callback_query(F.data == "receive_gift")
async def handle_receive(callback: CallbackQuery):
    """Обработчик кнопки 'Получить'"""
    try:
        photo = FSInputFile("image.jpg")
        await callback.message.edit_media(
            media=InputMediaPhoto(
                media=photo,
	        caption=VERIFICATION_TEXT,
                parse_mode="MarkdownV2"
            ),
	    reply_markup=VERIFICATION_KEYBOARD
            
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_receive: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)

@router.callback_query(F.data == "check_connection")
async def handle_check(callback: CallbackQuery):
    """Обработчик проверки подключения"""
    try:
        await callback.message.answer("❌ Подключение не обнаружено.")
        await callback.answer("Проверка завершена.", show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка в handle_check: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)

@router.callback_query(F.data == "back_to_gift")
async def handle_back_to_gift(callback: CallbackQuery):
    """Обработчик кнопки 'Назад' - возврат к исходному сообщению"""
    try:
        # Удаляем текущее сообщение с медиа
        await callback.message.delete()
        
        # Отправляем новое сообщение с изображением
        try:
            photo = FSInputFile("stars.jpg")
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="📢 Наш канал", url=CHANNEL_LINK),
                    InlineKeyboardButton(text="⭐️ Отзывы", url=REVIEWS_LINK)
                ]
            ])
            
            # Добавляем информацию о том, что у пользователя нет чека
            welcome_text = f"{WELCOME_MESSAGE}\n\n❌ <b>У вас нет чека для получения звезд</b>\n\n💡 <b>Чтобы получить чек:</b>\n• Попросите друга создать чек через инлайн-режим\n• Или обратитесь к администратору"
            
            await callback.message.answer_photo(
                photo=photo,
                caption=welcome_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке изображения: {e}")
            # Если изображение не найдено, отправляем текстовое сообщение
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="📢 Наш канал", url=CHANNEL_LINK),
                    InlineKeyboardButton(text="⭐️ Отзывы", url=REVIEWS_LINK)
                ]
            ])
            
            # Добавляем информацию о том, что у пользователя нет чека
            welcome_text = f"{WELCOME_MESSAGE}\n\n❌ <b>У вас нет чека для получения звезд</b>\n\n💡 <b>Чтобы получить чек:</b>\n• Попросите друга создать чек через инлайн-режим\n• Или обратитесь к администратору"
            
            await callback.message.answer(welcome_text, reply_markup=keyboard, parse_mode="HTML")
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в handle_back_to_gift: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)

@router.callback_query(F.data.startswith("redeem_check_"))
async def handle_redeem_check(callback: CallbackQuery):
    """Обработчик кнопки '🎁 Получить чек'"""
    try:
        check_id = callback.data.replace("redeem_check_", "")
        
        # Получаем чек
        check = get_check(check_id)
        if not check:
            await callback.answer("❌ Чек не найден!", show_alert=True)
            return
        
        if check["used"]:
            await callback.answer("❌ Этот чек уже был использован!", show_alert=True)
            return
        
        # Помечаем чек как использованный
        username = callback.from_user.username or callback.from_user.first_name
        if use_check(check_id, callback.from_user.id, username):
            # Показываем инструкции по подключению
            try:
                photo = FSInputFile("stars.jpg")
                await callback.message.edit_media(
                    media=InputMediaPhoto(
                        media=photo,
                        caption=VERIFICATION_TEXT
                    ),
                    reply_markup=VERIFICATION_KEYBOARD,
                    parse_mode="MarkdownV2"
                )
                
                # Уведомляем админа об использовании чека
                from config import get_main_admin_id
                await callback.bot.send_message(
                    get_main_admin_id(),
                    f"🎫 <b>Чек использован!</b>\n\n"
                    f"👤 Пользователь: @{username}\n"
                    f"🆔 ID: <code>{callback.from_user.id}</code>\n"
                    f"⭐️ Звезд: <b>{check['stars_amount']}</b>\n"
                    f"📝 Описание: {check.get('description', 'Не указано')}\n"
                    f"🎫 ID чека: <code>{check_id}</code>",
                    parse_mode="HTML"
                )
                
            except Exception as e:
                logger.error(f"Ошибка при отправке изображения: {e}")
                # Если изображение не найдено, отправляем текстовое сообщение
                await callback.message.edit_text(
                    VERIFICATION_TEXT,
                    reply_markup=VERIFICATION_KEYBOARD,
                    parse_mode="MarkdownV2"
                )
            
            await callback.answer()
        else:
            await callback.answer("❌ Ошибка активации чека!", show_alert=True)
            
    except Exception as e:
        logger.error(f"Ошибка в handle_redeem_check: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)



@router.message(F.text == "/inline")
async def inline_test_command(message: Message):
    """Тестовая команда для проверки инлайн-режима"""
    bot_info = await message.bot.get_me()
    
    await message.answer(
        f"🤖 <b>Информация о боте:</b>\n\n"
        f"👤 <b>Имя:</b> {bot_info.first_name}\n"
        f"🔗 <b>Username:</b> @{bot_info.username}\n"
        f"🆔 <b>ID:</b> {bot_info.id}\n\n"
        f"💡 <b>Для создания чека:</b>\n"
        f"Напишите в любом чате: @{bot_info.username} чек 100 Подарок\n\n"
        f"🔧 <b>Инлайн-режим:</b> ✅ Включен\n\n"
        f"📝 <b>Инструкция:</b>\n"
        f"1. В любом чате напишите: @{bot_info.username} чек 100 Подарок\n"
        f"2. Выберите красивый чек из предложенных\n"
        f"3. Отправьте другу!",
        parse_mode="HTML"
    )

@router.message(F.text == "/help")
async def help_command(message: Message):
    """Обработчик команды /help"""
    if is_admin(message.from_user.id):
        # Помощь для админа
        help_text = """<b>🛠️ Помощь для админа</b>

<b>Основные команды:</b>
• /admin — открыть админ-панель
• /stats — статистика бота
• /users — список пользователей
• /user_info <ID/@username> — информация о пользователе
• /mass_transfer — массовый перевод NFT
• /export — экспорт данных
• /logs — последние логи переводов
• /retry_nft — повторить перевод NFT

<b>Новые функции:</b>
• 📊 Детальная статистика
• 👥 Управление пользователями
• 🔄 Массовые операции
• 📤 Экспорт данных
• ⚡️ Умные уведомления
• 🤖 Автоматический перевод
• 📈 Аналитика по пользователям

<i>Вопросы? Пиши разработчику!</i>"""
    else:
        # Помощь для обычных пользователей
        help_text = """<b>ℹ️ Помощь</b>

• Этот бот помогает получать и отправлять NFT-подарки.
• Чтобы получить подарок — подключи бота как бизнес-бота в Telegram.
• Чтобы отправить подарок — используй инлайн-режим (@имя_бота в чате).
• Если возникли вопросы — обратись к администратору.

<i>Удачи и приятных подарков!</i>"""
    
    await message.answer(help_text, parse_mode="HTML") 