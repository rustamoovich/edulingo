"""
Telegram-бот для регистрации пользователей Edulingo
"""
import logging
from typing import Dict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    ConversationHandler
)
from database import Database
from config import BOT_TOKEN, BOOK_WEBSITE_URL, DATABASE_PATH

# Состояния разговора
CHOOSING_LANGUAGE, WAITING_CONTACT, WAITING_FIRST_NAME, WAITING_LAST_NAME, WAITING_REGION, WAITING_ADDRESS = range(6)

# Список областей Узбекистана на разных языках
UZBEKISTAN_REGIONS = {
    'ru': [
        "Андижанская область",
        "Бухарская область",
        "Джизакская область",
        "Кашкадарьинская область",
        "Навоийская область",
        "Наманганская область",
        "Самаркандская область",
        "Сурхандарьинская область",
        "Сырдарьинская область",
        "Ташкентская область",
        "Ферганская область",
        "Хорезмская область",
        "Республика Каракалпакстан",
        "г. Ташкент"
    ],
    'en': [
        "Andijan Region",
        "Bukhara Region",
        "Jizzakh Region",
        "Kashkadarya Region",
        "Navoiy Region",
        "Namangan Region",
        "Samarkand Region",
        "Surkhandarya Region",
        "Sirdarya Region",
        "Tashkent Region",
        "Fergana Region",
        "Khorezm Region",
        "Republic of Karakalpakstan",
        "Tashkent City"
    ],
    'uz': [
        "Andijon viloyati",
        "Buxoro viloyati",
        "Jizzax viloyati",
        "Qashqadaryo viloyati",
        "Navoiy viloyati",
        "Namangan viloyati",
        "Samarqand viloyati",
        "Surxondaryo viloyati",
        "Sirdaryo viloyati",
        "Toshkent viloyati",
        "Farg'ona viloyati",
        "Xorazm viloyati",
        "Qoraqalpog'iston Respublikasi",
        "Toshkent shahri"
    ]
}

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация базы данных
db = Database(DATABASE_PATH)

# Словари для хранения ID сообщений и команд пользователей
user_last_message_ids = {}  # {user_id: [message_ids]}
user_last_command_ids = {}  # {user_id: [command_ids]}


# Тексты сообщений (можно расширить для мультиязычности)
TEXTS = {
    'ru': {
        'choose_language': 'Выберите язык интерфейса:',
        'send_contact': 'Отправьте, пожалуйста, ваш номер телефона кнопкой ниже.',
        'share_contact': 'Поделиться контактом',
        'enter_first_name': 'Введите ваше имя:',
        'enter_last_name': 'Введите вашу фамилию:',
        'choose_region': 'Выберите область/регион Узбекистана:',
        'enter_address': 'Введите адрес проживания:',
        'registration_complete': 'Регистрация завершена. Спасибо!',
        'go_to_website': 'Открыть сайт книги',
        'welcome_back': 'Добро пожаловать обратно! Вы уже зарегистрированы.',
        'start_again': 'Нажмите /start для начала регистрации.'
    },
    'en': {
        'choose_language': 'Choose interface language:',
        'send_contact': 'Please send your phone number using the button below.',
        'share_contact': 'Share contact',
        'enter_first_name': 'Enter your first name:',
        'enter_last_name': 'Enter your last name:',
        'choose_region': 'Choose region of Uzbekistan:',
        'enter_address': 'Enter your address:',
        'registration_complete': 'Registration completed. Thank you!',
        'go_to_website': 'Go to book website',
        'welcome_back': 'Welcome back! You are already registered.',
        'start_again': 'Press /start to begin registration.'
    },
    'uz': {
        'choose_language': 'Interfeys tilini tanlang:',
        'send_contact': 'Iltimos, telefon raqamingizni quyidagi tugma orqali yuboring.',
        'share_contact': 'Kontaktni ulashish',
        'enter_first_name': 'Ismingizni kiriting:',
        'enter_last_name': 'Familiyangizni kiriting:',
        'choose_region': 'O\'zbekiston viloyatini tanlang:',
        'enter_address': 'Yashash manzilingizni kiriting:',
        'registration_complete': 'Ro\'yxatdan o\'tish yakunlandi. Rahmat!',
        'go_to_website': 'Kitob veb-saytiga o\'tish',
        'welcome_back': 'Xush kelibsiz! Siz allaqachon ro\'yxatdan o\'tgansiz.',
        'start_again': 'Ro\'yxatdan o\'tishni boshlash uchun /start ni bosing.'
    }
}


def get_text(language: str, key: str) -> str:
    """Получить текст на выбранном языке"""
    lang = language if language in TEXTS else 'ru'
    return TEXTS[lang].get(key, TEXTS['ru'][key])


def format_phone_number(phone: str) -> str:
    """Форматировать номер телефона: всегда добавлять '+' в начале, если его нет"""
    if not phone:
        return phone
    
    # Убираем все пробелы и дефисы для чистоты
    phone = phone.strip().replace(' ', '').replace('-', '')
    
    # Если номер не начинается с '+', добавляем его
    if not phone.startswith('+'):
        phone = '+' + phone
    
    return phone


async def delete_previous_messages(update: Update, context: ContextTypes.DEFAULT_TYPE, delete_current: bool = False):
    """Удалить предыдущие сообщения бота из чата (асинхронно в фоне)
    
    Args:
        update: Update объект
        context: Context объект
        delete_current: Если True, удаляет также последнее сообщение бота
    """
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id if update.effective_chat else None
    
    if not chat_id:
        return
    
    # Получаем список ID сообщений бота для удаления
    message_ids_to_delete = user_last_message_ids.get(user_id, [])
    
    # Получаем список ID команд пользователя для удаления (кроме последней)
    command_ids_to_delete = user_last_command_ids.get(user_id, [])
    
    # Удаляем сообщения бота в фоне (не блокируя основной поток)
    if message_ids_to_delete:
        if delete_current:
            # Удаляем все сообщения, включая последнее
            messages_to_delete = message_ids_to_delete.copy()
            # Очищаем список
            if user_id in user_last_message_ids:
                user_last_message_ids[user_id] = []
            
            # Также удаляем последнюю команду пользователя (если есть)
            command_to_delete = None
            if command_ids_to_delete:
                command_to_delete = command_ids_to_delete[-1]
                # Оставляем только последнюю команду в списке (она будет удалена)
                if user_id in user_last_command_ids:
                    user_last_command_ids[user_id] = command_ids_to_delete[:-1] if len(command_ids_to_delete) > 1 else []
        else:
            # Удаляем все, кроме последнего сообщения (оставляем текущее)
            if len(message_ids_to_delete) > 1:
                messages_to_delete = message_ids_to_delete[:-1]  # Все кроме последнего
                # Оставляем только последнее сообщение в списке
                if user_id in user_last_message_ids:
                    user_last_message_ids[user_id] = [message_ids_to_delete[-1]]
            else:
                # Если только одно сообщение и не нужно удалять текущее, не удаляем ничего
                messages_to_delete = []
            command_to_delete = None
        
        if messages_to_delete or command_to_delete:
            async def delete_messages_and_command():
                # Удаляем сообщения бота
                for message_id in messages_to_delete:
                    try:
                        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                    except Exception as e:
                        logger.debug(f"Не удалось удалить сообщение бота {message_id}: {e}")
                
                # Удаляем последнюю команду пользователя (если нужно)
                if command_to_delete:
                    try:
                        await context.bot.delete_message(chat_id=chat_id, message_id=command_to_delete)
                    except Exception as e:
                        logger.debug(f"Не удалось удалить команду пользователя {command_to_delete}: {e}")
            
            # Запускаем удаление в фоне
            import asyncio
            asyncio.create_task(delete_messages_and_command())
    
    # Удаляем предыдущие команды пользователя (кроме последней) в фоне
    # Это делается только если delete_current=False
    if not delete_current and len(command_ids_to_delete) > 1:
        commands_to_delete = command_ids_to_delete[:-1]
        
        async def delete_commands():
            for command_id in commands_to_delete:
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=command_id)
                except Exception as e:
                    logger.debug(f"Не удалось удалить команду пользователя {command_id}: {e}")
            # Оставляем только последнюю команду в списке
            if user_id in user_last_command_ids:
                user_last_command_ids[user_id] = [command_ids_to_delete[-1]]
        
        # Запускаем удаление в фоне
        import asyncio
        asyncio.create_task(delete_commands())


def save_message_id(message, user_id: int):
    """Сохранить ID сообщения бота для последующего удаления"""
    if not user_id:
        return
    
    if user_id not in user_last_message_ids:
        user_last_message_ids[user_id] = []
    
    # Ограничиваем количество сохраняемых сообщений (последние 10)
    if len(user_last_message_ids[user_id]) >= 10:
        user_last_message_ids[user_id] = user_last_message_ids[user_id][-9:]
    
    user_last_message_ids[user_id].append(message.message_id)


def save_command_id(update: Update, message_id: int):
    """Сохранить ID команды пользователя для последующего удаления"""
    user_id = update.effective_user.id
    
    if user_id not in user_last_command_ids:
        user_last_command_ids[user_id] = []
    
    # Ограничиваем количество сохраняемых команд (последние 10)
    if len(user_last_command_ids[user_id]) >= 10:
        user_last_command_ids[user_id] = user_last_command_ids[user_id][-9:]
    
    user_last_command_ids[user_id].append(message_id)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик команды /start"""
    user_id = update.effective_user.id
    
    # Сохраняем ID команды пользователя
    save_command_id(update, update.message.message_id)
    
    # Проверяем, зарегистрирован ли пользователь
    user = await db.get_user(user_id)
    
    if user:
        # Пользователь уже зарегистрирован - перенаправляем на сайт
        # Удаляем предыдущие сообщения (асинхронно в фоне)
        await delete_previous_messages(update, context)
        
        language = user.get('language', 'ru')
        text = get_text(language, 'welcome_back')
        
        keyboard = [
            [InlineKeyboardButton(
                get_text(language, 'go_to_website'),
                url=BOOK_WEBSITE_URL
            )]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        msg = await update.message.reply_text(text, reply_markup=reply_markup)
        save_message_id(msg, user_id)
        return ConversationHandler.END
    
    # Новый пользователь - начинаем регистрацию
    # НЕ удаляем сообщения до получения контакта
    keyboard = [
        [
            InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
            InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")
        ],
        [InlineKeyboardButton("🇺🇿 Oʻzbekcha", callback_data="lang_uz")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    msg = await update.message.reply_text(
        "Выберите язык интерфейса:\nChoose interface language:\nInterfeys tilini tanlang:",
        reply_markup=reply_markup
    )
    save_message_id(msg, user_id)
    
    # Сохраняем состояние регистрации
    username = update.effective_user.username
    context.user_data['registration'] = {
        'telegram_id': user_id,
        'username': username,
        'step': 'choosing_language'
    }
    
    return CHOOSING_LANGUAGE


async def language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик выбора языка"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    # Сообщение с выбором языка уже было сохранено в start()
    # Удаляем предыдущие сообщения + текущее сообщение с выбором языка + команду /start
    await delete_previous_messages(update, context, delete_current=True)
    
    language = query.data.split('_')[1]  # lang_ru -> ru
    
    # Сохраняем выбранный язык
    if 'registration' not in context.user_data:
        context.user_data['registration'] = {}
    
    context.user_data['registration']['language'] = language
    context.user_data['registration']['step'] = 'waiting_contact'
    
    # Запрашиваем контакт
    text = get_text(language, 'send_contact')
    share_text = get_text(language, 'share_contact')
    
    keyboard = [[KeyboardButton(share_text, request_contact=True)]]
    reply_markup = ReplyKeyboardMarkup(
        keyboard,
        one_time_keyboard=True,
        resize_keyboard=True
    )
    
    # Отправляем новое сообщение с кнопкой контакта
    msg = await query.message.reply_text(
        text,
        reply_markup=reply_markup
    )
    save_message_id(msg, user_id)
    
    return WAITING_CONTACT


async def receive_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик получения контакта"""
    contact = update.message.contact
    language = context.user_data['registration'].get('language', 'ru')
    
    # Сохраняем ID сообщения пользователя с контактом
    user_id = update.effective_user.id
    save_command_id(update, update.message.message_id)
    
    # Удаляем предыдущие сообщения + последнее сообщение бота с запросом контакта
    await delete_previous_messages(update, context, delete_current=True)
    
    # Сохраняем номер телефона с форматированием (всегда со знаком '+')
    phone_number = format_phone_number(contact.phone_number)
    context.user_data['registration']['phone'] = phone_number
    context.user_data['registration']['step'] = 'waiting_first_name'
    
    # Запрашиваем имя
    text = get_text(language, 'enter_first_name')
    
    msg = await update.message.reply_text(
        text,
        reply_markup=ReplyKeyboardRemove()
    )
    save_message_id(msg, user_id)
    
    return WAITING_FIRST_NAME


async def receive_first_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик получения имени"""
    first_name = update.message.text.strip()
    language = context.user_data['registration'].get('language', 'ru')
    
    # Сохраняем ID сообщения пользователя с именем
    user_id = update.effective_user.id
    save_command_id(update, update.message.message_id)
    
    # Удаляем предыдущие сообщения + последнее сообщение бота
    await delete_previous_messages(update, context, delete_current=True)
    
    # Сохраняем имя
    context.user_data['registration']['first_name'] = first_name
    context.user_data['registration']['step'] = 'waiting_last_name'
    
    # Запрашиваем фамилию
    text = get_text(language, 'enter_last_name')
    
    msg = await update.message.reply_text(text)
    save_message_id(msg, user_id)
    
    return WAITING_LAST_NAME


async def receive_last_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик получения фамилии"""
    last_name = update.message.text.strip()
    language = context.user_data['registration'].get('language', 'ru')
    
    # Сохраняем ID сообщения пользователя с фамилией
    user_id = update.effective_user.id
    save_command_id(update, update.message.message_id)
    
    # Удаляем предыдущие сообщения + последнее сообщение бота
    await delete_previous_messages(update, context, delete_current=True)
    
    # Сохраняем фамилию
    context.user_data['registration']['last_name'] = last_name
    context.user_data['registration']['step'] = 'waiting_region'
    
    # Запрашиваем выбор области
    text = get_text(language, 'choose_region')
    
    # Получаем список областей на выбранном языке
    regions = UZBEKISTAN_REGIONS.get(language, UZBEKISTAN_REGIONS['ru'])
    
    # Создаем inline-клавиатуру с областями Узбекистана
    keyboard = []
    for i in range(0, len(regions), 2):
        row = []
        row.append(InlineKeyboardButton(regions[i], callback_data=f"region_{i}"))
        if i + 1 < len(regions):
            row.append(InlineKeyboardButton(regions[i + 1], callback_data=f"region_{i + 1}"))
        keyboard.append(row)
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    msg = await update.message.reply_text(text, reply_markup=reply_markup)
    save_message_id(msg, user_id)
    
    return WAITING_REGION


async def region_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик выбора области"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    # Сохраняем ID текущего сообщения с выбором области для удаления
    save_message_id(query.message, user_id)
    
    # Удаляем предыдущие сообщения + текущее сообщение с выбором области
    await delete_previous_messages(update, context, delete_current=True)
    
    region_index = int(query.data.split('_')[1])
    language = context.user_data['registration'].get('language', 'ru')
    
    # Получаем область на выбранном языке
    regions = UZBEKISTAN_REGIONS.get(language, UZBEKISTAN_REGIONS['ru'])
    region = regions[region_index]
    
    # Сохраняем область
    context.user_data['registration']['region'] = region
    context.user_data['registration']['step'] = 'waiting_address'
    
    # Запрашиваем адрес
    text = get_text(language, 'enter_address')
    
    msg = await query.message.reply_text(text)
    save_message_id(msg, user_id)
    
    return WAITING_ADDRESS


async def receive_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик получения адреса и завершение регистрации"""
    address = update.message.text.strip()
    language = context.user_data['registration'].get('language', 'ru')
    region = context.user_data['registration'].get('region', '')
    
    # Сохраняем ID сообщения пользователя с адресом
    user_id = update.effective_user.id
    save_command_id(update, update.message.message_id)
    
    # Удаляем предыдущие сообщения + последнее сообщение бота
    await delete_previous_messages(update, context, delete_current=True)
    
    # Сохраняем адрес (включая область)
    full_address = f"{region}, {address}" if region else address
    context.user_data['registration']['address'] = full_address
    
    # Сохраняем пользователя в базу данных
    user_data = context.user_data['registration']
    
    try:
        await db.create_user(user_data)
        logger.info(f"New user registered: {user_data['telegram_id']}")
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        msg = await update.message.reply_text("Произошла ошибка при сохранении данных. Попробуйте позже.")
        save_message_id(msg, user_id)
        return ConversationHandler.END
    
    # Уведомляем о завершении регистрации
    complete_text = get_text(language, 'registration_complete')
    website_text = get_text(language, 'go_to_website')
    
    keyboard = [
        [InlineKeyboardButton(website_text, url=BOOK_WEBSITE_URL)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    msg = await update.message.reply_text(complete_text, reply_markup=reply_markup)
    save_message_id(msg, user_id)
    
    # Очищаем данные регистрации
    context.user_data.pop('registration', None)
    
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена регистрации"""
    context.user_data.pop('registration', None)
    await update.message.reply_text(
        "Регистрация отменена.",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений для незарегистрированных пользователей"""
    user_id = update.effective_user.id
    user = await db.get_user(user_id)
    
    if user:
        # Пользователь зарегистрирован - перенаправляем на сайт
        language = user.get('language', 'ru')
        text = get_text(language, 'welcome_back')
        
        keyboard = [
            [InlineKeyboardButton(
                get_text(language, 'go_to_website'),
                url=BOOK_WEBSITE_URL
            )]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(text, reply_markup=reply_markup)
    else:
        # Не зарегистрирован - предлагаем начать
        await update.message.reply_text(get_text('ru', 'start_again'))


async def post_init(application: Application) -> None:
    """Инициализация базы данных после создания приложения"""
    # Создаем экземпляр базы данных для инициализации
    db = Database(DATABASE_PATH)
    await db.init_db()
    logger.info("База данных инициализирована")


def get_bot_application():
    """Создать и настроить приложение бота"""
    # Создание приложения без Updater (для webhook)
    # Используем update_queue=None чтобы не создавать Updater
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    
    # Создание ConversationHandler для регистрации
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING_LANGUAGE: [CallbackQueryHandler(language_callback, pattern="^lang_")],
            WAITING_CONTACT: [MessageHandler(filters.CONTACT, receive_contact)],
            WAITING_FIRST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_first_name)],
            WAITING_LAST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_last_name)],
            WAITING_REGION: [CallbackQueryHandler(region_callback, pattern="^region_")],
            WAITING_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_address)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_chat=True,
        per_user=True,
    )
    
    # Добавление обработчиков
    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    return application


def main():
    """Главная функция запуска бота (polling для локальной разработки)"""
    application = get_bot_application()
    
    # Запуск бота через polling
    logger.info("Бот запущен через polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()

