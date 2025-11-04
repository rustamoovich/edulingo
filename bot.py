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

# Список областей Узбекистана
UZBEKISTAN_REGIONS = [
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
]

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация базы данных
db = Database(DATABASE_PATH)


# Тексты сообщений (можно расширить для мультиязычности)
TEXTS = {
    'ru': {
        'choose_language': 'Выберите язык интерфейса:',
        'send_contact': 'Отправьте, пожалуйста, ваш номер телефона кнопкой ниже.',
        'share_contact': 'Поделиться контактом',
        'enter_first_name': 'Введите ваше имя (как в документе):',
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
        'enter_first_name': 'Enter your first name (as in your document):',
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
        'enter_first_name': 'Ismingizni kiriting (hujjatdagidek):',
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


async def delete_previous_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удалить предыдущие сообщения бота из чата"""
    if 'bot_messages' not in context.user_data:
        context.user_data['bot_messages'] = []
        return
    
    chat_id = update.effective_chat.id if update.effective_chat else None
    if not chat_id:
        return
    
    messages_to_delete = context.user_data['bot_messages'].copy()
    for msg_id in messages_to_delete:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception as e:
            logger.debug(f"Не удалось удалить сообщение {msg_id}: {e}")
    
    context.user_data['bot_messages'] = []


async def save_message_id(message, context: ContextTypes.DEFAULT_TYPE):
    """Сохранить ID сообщения для последующего удаления"""
    if 'bot_messages' not in context.user_data:
        context.user_data['bot_messages'] = []
    context.user_data['bot_messages'].append(message.message_id)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик команды /start"""
    user_id = update.effective_user.id
    
    # Удаляем предыдущие сообщения
    await delete_previous_messages(update, context)
    
    # Удаляем сообщение пользователя /start
    try:
        await update.message.delete()
    except Exception as e:
        logger.debug(f"Не удалось удалить сообщение пользователя: {e}")
    
    # Проверяем, зарегистрирован ли пользователь
    user = await db.get_user(user_id)
    
    if user:
        # Пользователь уже зарегистрирован - перенаправляем на сайт
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
        await save_message_id(msg, context)
        return ConversationHandler.END
    
    # Новый пользователь - начинаем регистрацию
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
    await save_message_id(msg, context)
    
    # Сохраняем состояние регистрации
    context.user_data['registration'] = {
        'telegram_id': user_id,
        'step': 'choosing_language'
    }
    
    return CHOOSING_LANGUAGE


async def language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик выбора языка"""
    query = update.callback_query
    await query.answer()
    
    # Удаляем предыдущие сообщения
    await delete_previous_messages(update, context)
    
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
    
    # Удаляем предыдущее сообщение с выбором языка
    try:
        await query.message.delete()
    except Exception as e:
        logger.debug(f"Не удалось удалить сообщение: {e}")
    
    # Отправляем новое сообщение с кнопкой контакта
    msg = await query.message.reply_text(
        text,
        reply_markup=reply_markup
    )
    await save_message_id(msg, context)
    
    return WAITING_CONTACT


async def receive_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик получения контакта"""
    contact = update.message.contact
    language = context.user_data['registration'].get('language', 'ru')
    
    # Удаляем предыдущие сообщения
    await delete_previous_messages(update, context)
    
    # Удаляем сообщение пользователя с контактом
    try:
        await update.message.delete()
    except Exception as e:
        logger.debug(f"Не удалось удалить сообщение пользователя: {e}")
    
    # Сохраняем номер телефона
    context.user_data['registration']['phone'] = contact.phone_number
    context.user_data['registration']['step'] = 'waiting_first_name'
    
    # Запрашиваем имя
    text = get_text(language, 'enter_first_name')
    
    msg = await update.message.reply_text(
        text,
        reply_markup=ReplyKeyboardRemove()
    )
    await save_message_id(msg, context)
    
    return WAITING_FIRST_NAME


async def receive_first_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик получения имени"""
    first_name = update.message.text.strip()
    language = context.user_data['registration'].get('language', 'ru')
    
    # Удаляем предыдущие сообщения
    await delete_previous_messages(update, context)
    
    # Удаляем сообщение пользователя с именем
    try:
        await update.message.delete()
    except Exception as e:
        logger.debug(f"Не удалось удалить сообщение пользователя: {e}")
    
    # Сохраняем имя
    context.user_data['registration']['first_name'] = first_name
    context.user_data['registration']['step'] = 'waiting_last_name'
    
    # Запрашиваем фамилию
    text = get_text(language, 'enter_last_name')
    
    msg = await update.message.reply_text(text)
    await save_message_id(msg, context)
    
    return WAITING_LAST_NAME


async def receive_last_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик получения фамилии"""
    last_name = update.message.text.strip()
    language = context.user_data['registration'].get('language', 'ru')
    
    # Удаляем предыдущие сообщения
    await delete_previous_messages(update, context)
    
    # Удаляем сообщение пользователя с фамилией
    try:
        await update.message.delete()
    except Exception as e:
        logger.debug(f"Не удалось удалить сообщение пользователя: {e}")
    
    # Сохраняем фамилию
    context.user_data['registration']['last_name'] = last_name
    context.user_data['registration']['step'] = 'waiting_region'
    
    # Запрашиваем выбор области
    text = get_text(language, 'choose_region')
    
    # Создаем inline-клавиатуру с областями Узбекистана
    keyboard = []
    for i in range(0, len(UZBEKISTAN_REGIONS), 2):
        row = []
        row.append(InlineKeyboardButton(UZBEKISTAN_REGIONS[i], callback_data=f"region_{i}"))
        if i + 1 < len(UZBEKISTAN_REGIONS):
            row.append(InlineKeyboardButton(UZBEKISTAN_REGIONS[i + 1], callback_data=f"region_{i + 1}"))
        keyboard.append(row)
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    msg = await update.message.reply_text(text, reply_markup=reply_markup)
    await save_message_id(msg, context)
    
    return WAITING_REGION


async def region_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик выбора области"""
    query = update.callback_query
    await query.answer()
    
    # Удаляем предыдущие сообщения
    await delete_previous_messages(update, context)
    
    region_index = int(query.data.split('_')[1])
    region = UZBEKISTAN_REGIONS[region_index]
    language = context.user_data['registration'].get('language', 'ru')
    
    # Сохраняем область
    context.user_data['registration']['region'] = region
    context.user_data['registration']['step'] = 'waiting_address'
    
    # Удаляем предыдущее сообщение с выбором области
    try:
        await query.message.delete()
    except Exception as e:
        logger.debug(f"Не удалось удалить сообщение: {e}")
    
    # Запрашиваем адрес
    text = get_text(language, 'enter_address')
    
    msg = await query.message.reply_text(text)
    await save_message_id(msg, context)
    
    return WAITING_ADDRESS


async def receive_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик получения адреса и завершение регистрации"""
    address = update.message.text.strip()
    language = context.user_data['registration'].get('language', 'ru')
    region = context.user_data['registration'].get('region', '')
    
    # Удаляем предыдущие сообщения
    await delete_previous_messages(update, context)
    
    # Удаляем сообщение пользователя с адресом
    try:
        await update.message.delete()
    except Exception as e:
        logger.debug(f"Не удалось удалить сообщение пользователя: {e}")
    
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
        await save_message_id(msg, context)
        return ConversationHandler.END
    
    # Уведомляем о завершении регистрации
    complete_text = get_text(language, 'registration_complete')
    website_text = get_text(language, 'go_to_website')
    
    keyboard = [
        [InlineKeyboardButton(website_text, url=BOOK_WEBSITE_URL)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    msg = await update.message.reply_text(complete_text, reply_markup=reply_markup)
    await save_message_id(msg, context)
    
    # Очищаем данные регистрации
    context.user_data.pop('registration', None)
    context.user_data.pop('bot_messages', None)
    
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
    await db.init_db()
    logger.info("База данных инициализирована")


def main():
    """Главная функция запуска бота"""
    # Создание приложения
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
    
    # Запуск бота
    logger.info("Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()

