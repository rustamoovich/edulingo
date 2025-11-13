"""
Telegram-бот для регистрации пользователей Edulingo
"""
import logging
import os
import math
import asyncio
from typing import Dict, List, Optional, Tuple
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

# Настройки уроков
PAGE_SIZE = 12

# Индекс аудио: { lang: { category: [ {order:int, title:str, path:str} ] } }
AUDIO_INDEX: Dict[str, Dict[str, List[Dict]]] = {"ru": {}, "en": {}, "uz": {}}
SUPPORTED_LANGS = {"ru", "en", "uz"}
CATEGORY_ALIASES = {
    "lessons": ["1-30-darslar", "1-30-darslar/", "1-30-darslar\\"],
    "dialogs": ["Dialoglar"],
    "mini_dialogs": ["Mini dialoglar"],
}
LANG_DIR_ALIASES = {
    "ru": ["Rus tili"],
    "en": ["Ingliz tili"],
    # Если появится узбекская озвучка, добавим алиас
    "uz": ["O'zbek tili", "Uzbek tili"]
}

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
user_last_audio_id = {}  # {user_id: message_id} - ID последнего отправленного аудио

def _is_numbered_filename(filename: str) -> Optional[Tuple[int, str]]:
    """
    Попытаться извлечь порядковый номер и короткий заголовок из имени файла:
    '12. Text.mp3' -> (12, 'Text')
    """
    try:
        name = os.path.splitext(os.path.basename(filename))[0]
        parts = name.split('.', 1)
        if len(parts) == 2:
            order = int(parts[0].strip())
            title = parts[1].strip().replace('_', ' ')
            return order, title
        # Альтернатива: '12 - Title'
        parts = name.split('-', 1)
        if len(parts) == 2:
            order = int(parts[0].strip())
            title = parts[1].strip().replace('_', ' ')
            return order, title
    except Exception:
        return None
    return None

def _match_lang_dir(dirname: str) -> Optional[str]:
    for lang, aliases in LANG_DIR_ALIASES.items():
        if dirname in aliases:
            return lang
    return None

def _match_category(path_parts: List[str]) -> Optional[str]:
    # Ищем по последнему сегменту пути
    last = path_parts[-1]
    for cat, aliases in CATEGORY_ALIASES.items():
        for a in aliases:
            if last == a or last.endswith(a):
                return cat
    # Спец-случай: путь типа '.../Audio darslar/1-30-darslar'
    for p in path_parts:
        for cat, aliases in CATEGORY_ALIASES.items():
            if any(p == a for a in aliases):
                return cat
    return None

def build_audio_index(audios_root: str = "audios") -> None:
    """
    Построить индекс аудиофайлов из папки audios.
    Ожидаем структуру с языковыми папками и категориями внутри.
    """
    global AUDIO_INDEX
    AUDIO_INDEX = { "ru": {}, "en": {}, "uz": {} }
    if not os.path.isdir(audios_root):
        logger.info(f"Папка с аудио не найдена: {audios_root}")
        return

    for top in os.listdir(audios_root):
        top_path = os.path.join(audios_root, top)
        if not os.path.isdir(top_path):
            continue
        lang = _match_lang_dir(top)
        if not lang:
            continue
        # Обходим подкаталоги категорий
        for root, dirs, files in os.walk(top_path):
            # Определяем категорию по пути
            rel = os.path.relpath(root, top_path).replace('\\', '/')
            if rel in ("", ".", "./"):
                continue
            cat = _match_category(rel.split('/'))
            if not cat:
                continue
            if cat not in AUDIO_INDEX[lang]:
                AUDIO_INDEX[lang][cat] = []
            for f in files:
                if not f.lower().endswith(".mp3"):
                    continue
                full_path = os.path.join(root, f)
                parsed = _is_numbered_filename(f)
                if parsed:
                    order, title = parsed
                else:
                    order, title = 9999, os.path.splitext(f)[0]
                AUDIO_INDEX[lang][cat].append({
                    "order": order,
                    "title": title,
                    "path": full_path.replace("\\", "/"),
                })
            # Сортировка по order, затем по имени
            AUDIO_INDEX[lang][cat].sort(key=lambda x: (x["order"], x["title"]))

def paginate(items: List[Dict], page: int, page_size: int = PAGE_SIZE) -> Tuple[List[Dict], int, int]:
    total = len(items)
    total_pages = max(1, math.ceil(total / page_size))
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    end = start + page_size
    return items[start:end], page, total_pages

async def show_lessons_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, language: str, category: str = "lessons", page: int = 1, audio_lang: str = None):
    """Показать список уроков с пагинацией.
    
    Args:
        language: Язык интерфейса пользователя (ru/en/uz)
        category: Категория уроков (lessons/dialogs/mini_dialogs)
        page: Номер страницы
        audio_lang: Язык разговорника (ru/en). Если None, определяется автоматически из language
    """
    interface_lang = language if language in SUPPORTED_LANGS else "ru"
    
    # Определяем язык разговорника
    if audio_lang is None:
        # Проверяем, есть ли сохраненный язык в context
        audio_lang = context.user_data.get('audio_lang')
        if audio_lang is None:
            # Если язык интерфейса английский, показываем английский разговорник
            # Если русский или узбекский - показываем русский разговорник
            if interface_lang == 'en':
                audio_lang = 'en'
            else:
                audio_lang = 'ru'
    
    # Сохраняем выбранный язык разговорника в context
    context.user_data['audio_lang'] = audio_lang
    
    if not AUDIO_INDEX or not AUDIO_INDEX.get(audio_lang):
        build_audio_index()
    lessons_by_cat = AUDIO_INDEX.get(audio_lang, {})
    if category not in lessons_by_cat or not lessons_by_cat[category]:
        # Если нет такой категории, попробуем другую
        if lessons_by_cat:
            category = next(iter(lessons_by_cat))
        else:
            if update.callback_query:
                await update.callback_query.answer("Аудио-уроки пока недоступны.")
            else:
                await update.effective_message.reply_text("Аудио-уроки пока недоступны.")
            return
    items = lessons_by_cat[category]
    page_items, cur_page, total_pages = paginate(items, page, PAGE_SIZE)

    # Кнопки уроков
    rows = []
    for it in page_items:
        label = f"{it['order']:02d}. {it['title']}"
        rows.append([InlineKeyboardButton(label, callback_data=f"play_{category}_{it['order']}")])
    # Пагинация
    nav = []
    if cur_page > 1:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"list_{category}_{cur_page-1}"))
    nav.append(InlineKeyboardButton(f"{cur_page}/{total_pages}", callback_data="noop"))
    if cur_page < total_pages:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"list_{category}_{cur_page+1}"))
    if nav:
        rows.append(nav)
    # Переключение категорий (если есть несколько)
    cats = list(lessons_by_cat.keys())
    if len(cats) > 1:
        cat_row = []
        for c in cats[:3]:  # не перегружаем интерфейс
            emoji = "📘" if c == "lessons" else ("💬" if c == "dialogs" else "🗣️")
            # Получаем читаемое название категории на выбранном языке интерфейса
            category_name = CATEGORY_NAMES.get(interface_lang, CATEGORY_NAMES['ru']).get(c, c)
            cat_row.append(InlineKeyboardButton(f"{emoji} {category_name}", callback_data=f"list_{c}_1"))
        rows.append(cat_row)

    # Добавляем кнопки переключения языка разговорника вверху списка
    # Проверяем, какие языки доступны в аудио-индексе
    available_langs = []
    if AUDIO_INDEX:
        if 'ru' in AUDIO_INDEX and AUDIO_INDEX['ru']:
            available_langs.append('ru')
        if 'en' in AUDIO_INDEX and AUDIO_INDEX['en']:
            available_langs.append('en')
    
    # Если доступны оба языка, добавляем кнопки переключения
    if len(available_langs) > 1:
        lang_buttons = []
        for lang_option in available_langs:
            if lang_option == 'ru':
                label = "🇷🇺 Русский разговорник"
            elif lang_option == 'en':
                label = "🇺🇸 English phrasebook"
            else:
                label = lang_option
            
            # Если это текущий язык разговорника, выделяем галочкой
            if lang_option == audio_lang:
                lang_buttons.append(InlineKeyboardButton(f"✓ {label}", callback_data=f"switch_lang_{lang_option}_{category}_{page}"))
            else:
                lang_buttons.append(InlineKeyboardButton(label, callback_data=f"switch_lang_{lang_option}_{category}_{page}"))
        
        # Вставляем кнопки языка в начало списка
        rows.insert(0, lang_buttons)
    
    reply_markup = InlineKeyboardMarkup(rows)
    text_map = {
        "ru": "Выберите язык разговорника и аудио-урок:",
        "en": "Choose phrasebook language and audio lesson:",
        "uz": "So'zlashgich tilini va audio darsni tanlang:"
    }
    text = text_map.get(interface_lang, text_map["ru"])
    
    # Если это callback_query (пагинация), редактируем существующее сообщение
    if update.callback_query:
        query = update.callback_query
        await query.answer()  # Убираем индикатор загрузки
        try:
            await query.edit_message_text(text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Ошибка редактирования сообщения: {e}")
            # Если не удалось отредактировать (например, сообщение не изменилось), отправляем новое
            await query.message.reply_text(text, reply_markup=reply_markup)
    else:
        # Первый вызов - отправляем новое сообщение
        await update.effective_message.reply_text(text, reply_markup=reply_markup)

async def play_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE, language: str, category: str, order: int):
    """Отправить аудио-урок пользователю."""
    query = update.callback_query
    if query:
        await query.answer()  # Убираем индикатор загрузки
    
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id if update.effective_chat else None
    
    # Удаляем сообщение "Регистрация завершена", если это первое прослушивание
    registration_complete_msg_id = context.user_data.get('registration_complete_message_id')
    if registration_complete_msg_id and chat_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=registration_complete_msg_id)
            logger.debug(f"Удалено сообщение о завершении регистрации {registration_complete_msg_id} для пользователя {user_id}")
            # Очищаем сохраненный ID
            context.user_data.pop('registration_complete_message_id', None)
        except Exception as e:
            logger.debug(f"Не удалось удалить сообщение о завершении регистрации {registration_complete_msg_id}: {e}")
            # Очищаем ID даже если не удалось удалить (сообщение могло быть уже удалено)
            context.user_data.pop('registration_complete_message_id', None)
    
    # Удаляем предыдущее аудио, если оно есть
    if user_id in user_last_audio_id and chat_id:
        previous_audio_id = user_last_audio_id[user_id]
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=previous_audio_id)
            logger.debug(f"Удалено предыдущее аудио {previous_audio_id} для пользователя {user_id}")
        except Exception as e:
            logger.debug(f"Не удалось удалить предыдущее аудио {previous_audio_id}: {e}")
    
    # Определяем язык разговорника из context или автоматически
    audio_lang = context.user_data.get('audio_lang')
    if audio_lang is None:
        # Если язык интерфейса английский, используем английский разговорник
        # Иначе - русский
        if language == 'en':
            audio_lang = 'en'
        else:
            audio_lang = 'ru'
    
    lessons = AUDIO_INDEX.get(audio_lang, {}).get(category, [])
    target = None
    for it in lessons:
        if it["order"] == order:
            target = it
            break
    if not target:
        msg_target = query.message if query else update.effective_message
        await msg_target.reply_text("Урок не найден.")
        return
    path = target["path"]
    title = target["title"]
    # Добавляем номер урока в формате, как в списке (например, "01. Text")
    order = target["order"]
    formatted_title = f"{order:02d}. {title}"
    
    try:
        msg_target = query.message if query else update.effective_message
        with open(path, "rb") as f:
            audio_msg = await msg_target.reply_audio(audio=f, title=formatted_title, caption=formatted_title)
            # Сохраняем ID нового аудио-сообщения
            if audio_msg:
                user_last_audio_id[user_id] = audio_msg.message_id
    except FileNotFoundError:
        msg_target = query.message if query else update.effective_message
        await msg_target.reply_text("Файл урока не найден на сервере.")
    except Exception as e:
        logger.error(f"Ошибка отправки аудио: {e}")
        msg_target = query.message if query else update.effective_message
        await msg_target.reply_text("Не удалось отправить аудио.")

# Названия категорий на разных языках
CATEGORY_NAMES = {
    'ru': {
        'lessons': 'Уроки',
        'dialogs': 'Диалоги',
        'mini_dialogs': 'Мини-диалоги'
    },
    'en': {
        'lessons': 'Lessons',
        'dialogs': 'Dialogs',
        'mini_dialogs': 'Mini Dialogs'
    },
    'uz': {
        'lessons': 'Darslar',
        'dialogs': 'Dialoglar',
        'mini_dialogs': 'Mini dialoglar'
    }
}

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


# Хранилище ID сообщений для удаления (только для регистрации)
# Структура: {user_id: [message_ids]}
user_registration_message_ids: Dict[int, List[int]] = {}


async def delete_previous_messages(update: Update, context: ContextTypes.DEFAULT_TYPE, delete_current: bool = False, exclude_message_id: int = None):
    """Удалить предыдущие сообщения регистрации (вопрос бота и ответ пользователя)
    
    Args:
        update: Обновление от Telegram
        context: Контекст бота
        delete_current: Удалить ли текущее сообщение
        exclude_message_id: ID сообщения, которое НЕ нужно удалять (например, только что отправленное)
    """
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id if update.effective_chat else None
    
    if not chat_id:
        return
    
    # Получаем список сообщений для удаления
    message_ids_to_delete = user_registration_message_ids.get(user_id, []).copy()
    
    # Если нужно удалить текущее сообщение, добавляем его
    if delete_current:
        if update.message:
            current_id = update.message.message_id
            if current_id not in message_ids_to_delete:
                message_ids_to_delete.append(current_id)
        elif update.callback_query and update.callback_query.message:
            current_id = update.callback_query.message.message_id
            if current_id not in message_ids_to_delete:
                message_ids_to_delete.append(current_id)
    
    # Исключаем сообщение, которое не нужно удалять
    if exclude_message_id:
        message_ids_to_delete = [msg_id for msg_id in message_ids_to_delete if msg_id != exclude_message_id]
    
    if not message_ids_to_delete:
        return
    
    # Удаляем сообщения асинхронно, чтобы не блокировать интерфейс
    async def delete_messages():
        for msg_id in message_ids_to_delete:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception as e:
                logger.debug(f"Не удалось удалить сообщение {msg_id}: {e}")
        
        # Очищаем список после удаления (только те, которые были удалены)
        if user_id in user_registration_message_ids:
            # Удаляем только те ID, которые были успешно удалены
            remaining = [msg_id for msg_id in user_registration_message_ids[user_id] if msg_id not in message_ids_to_delete]
            user_registration_message_ids[user_id] = remaining
    
    # Запускаем удаление в фоне
    asyncio.create_task(delete_messages())


def save_message_id(message, user_id: int):
    """Сохранить ID сообщения бота для последующего удаления (только для регистрации)"""
    if not message:
        return
    
    if user_id not in user_registration_message_ids:
        user_registration_message_ids[user_id] = []
    
    user_registration_message_ids[user_id].append(message.message_id)


def save_command_id(update: Update, message_id: int):
    """Сохранить ID сообщения пользователя для последующего удаления (только для регистрации)"""
    user_id = update.effective_user.id
    
    if user_id not in user_registration_message_ids:
        user_registration_message_ids[user_id] = []
    
    user_registration_message_ids[user_id].append(message_id)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик команды /start"""
    user_id = update.effective_user.id
    
    # Проверяем, зарегистрирован ли пользователь
    user = await db.get_user(user_id)
    
    if user:
        # Пользователь уже зарегистрирован - показываем список уроков
        language = user.get('language', 'ru') or 'ru'
        await show_lessons_menu(update, context, language=language, category="lessons", page=1)
        return ConversationHandler.END
    
    # Новый пользователь - начинаем регистрацию
    # Очищаем предыдущие сообщения регистрации, если они есть
    if user_id in user_registration_message_ids:
        user_registration_message_ids[user_id] = []
    
    # Сохраняем ID команды пользователя
    save_command_id(update, update.message.message_id)
    
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
    
    # Удаляем предыдущие сообщения (вопрос бота о выборе языка и команду /start)
    # Также удаляем текущее сообщение с выбором языка (callback_query)
    # Исключаем только что отправленное сообщение с запросом контакта
    await delete_previous_messages(update, context, delete_current=True, exclude_message_id=msg.message_id)
    
    return WAITING_CONTACT


async def receive_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик получения контакта"""
    contact = update.message.contact
    language = context.user_data['registration'].get('language', 'ru')
    
    user_id = update.effective_user.id
    
    # Сохраняем ID сообщения пользователя с контактом
    save_command_id(update, update.message.message_id)
    
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
    
    # Удаляем предыдущие сообщения (вопрос бота о контакте и ответ пользователя)
    # Исключаем только что отправленное сообщение с запросом имени
    await delete_previous_messages(update, context, delete_current=True, exclude_message_id=msg.message_id)
    
    return WAITING_FIRST_NAME


async def receive_first_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик получения имени"""
    first_name = update.message.text.strip()
    language = context.user_data['registration'].get('language', 'ru')
    
    user_id = update.effective_user.id
    
    # Сохраняем ID сообщения пользователя с именем
    save_command_id(update, update.message.message_id)
    
    # Сохраняем имя
    context.user_data['registration']['first_name'] = first_name
    context.user_data['registration']['step'] = 'waiting_last_name'
    
    # Запрашиваем фамилию
    text = get_text(language, 'enter_last_name')
    
    msg = await update.message.reply_text(text)
    save_message_id(msg, user_id)
    
    # Удаляем предыдущие сообщения (вопрос бота об имени и ответ пользователя)
    # Исключаем только что отправленное сообщение с запросом фамилии
    await delete_previous_messages(update, context, delete_current=True, exclude_message_id=msg.message_id)
    
    return WAITING_LAST_NAME


async def receive_last_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик получения фамилии"""
    last_name = update.message.text.strip()
    language = context.user_data['registration'].get('language', 'ru')
    
    user_id = update.effective_user.id
    
    # Сохраняем ID сообщения пользователя с фамилией
    save_command_id(update, update.message.message_id)
    
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
    
    # Удаляем предыдущие сообщения (вопрос бота о фамилии и ответ пользователя)
    # Исключаем только что отправленное сообщение с выбором области
    await delete_previous_messages(update, context, delete_current=True, exclude_message_id=msg.message_id)
    
    return WAITING_REGION


async def region_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик выбора области"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
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
    
    # Удаляем предыдущие сообщения (вопрос бота о выборе области и выбор пользователя)
    # Исключаем только что отправленное сообщение с запросом адреса
    await delete_previous_messages(update, context, delete_current=True, exclude_message_id=msg.message_id)
    
    return WAITING_ADDRESS


async def receive_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик получения адреса и завершение регистрации"""
    address = update.message.text.strip()
    language = context.user_data['registration'].get('language', 'ru')
    region = context.user_data['registration'].get('region', '')
    
    user_id = update.effective_user.id
    
    # Сохраняем ID сообщения пользователя с адресом
    save_command_id(update, update.message.message_id)
    
    # Сохраняем адрес (включая область)
    full_address = f"{region}, {address}" if region else address
    context.user_data['registration']['address'] = full_address
    
    # Удаляем предыдущие сообщения (вопрос бота об адресе и ответ пользователя)
    await delete_previous_messages(update, context, delete_current=True)
    
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
    
    # Очищаем данные регистрации и сообщения
    context.user_data.pop('registration', None)
    if user_id in user_registration_message_ids:
        user_registration_message_ids.pop(user_id)
    
    # Завершение регистрации и показ уроков
    complete_text = get_text(language, 'registration_complete')
    complete_msg = await update.message.reply_text(complete_text)
    
    # Сохраняем ID сообщения о завершении регистрации для последующего удаления
    # при первом прослушивании аудио
    context.user_data['registration_complete_message_id'] = complete_msg.message_id
    
    await show_lessons_menu(update, context, language=language, category="lessons", page=1)
    
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
        # Пользователь зарегистрирован - показать меню уроков
        language = user.get('language', 'ru') or 'ru'
        # Очищаем сохраненный язык разговорника при новом входе
        context.user_data.pop('audio_lang', None)
        await show_lessons_menu(update, context, language=language, category="lessons", page=1)
    else:
        # Не зарегистрирован - предлагаем начать
        await update.message.reply_text(get_text('ru', 'start_again'))


async def post_init(application: Application) -> None:
    """Инициализация базы данных после создания приложения"""
    # Создаем экземпляр базы данных для инициализации
    db = Database(DATABASE_PATH)
    await db.init_db()
    logger.info("База данных инициализирована")
    # Строим индекс аудио
    build_audio_index()


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

    # Хендлеры списков и проигрывания
    async def handle_noop(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик для кнопки без действия (номер страницы)"""
        query = update.callback_query
        if query:
            await query.answer()
    
    async def handle_list_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик пагинации списка уроков"""
        query = update.callback_query
        if not query:
            return
        parts = query.data.split('_')
        if len(parts) < 3:
            await query.answer("Ошибка")
            return
        # Формат: list_{category}_{page}
        # Категория может содержать подчеркивания (например, mini_dialogs)
        # Поэтому берем все части кроме первой (list) и последней (page)
        category = '_'.join(parts[1:-1])  # Все части между 'list' и номером страницы
        try:
            page = int(parts[-1])  # Последняя часть - номер страницы
        except ValueError:
            await query.answer("Ошибка: неверный формат")
            return
        # Получаем язык интерфейса пользователя из базы данных
        user_id = update.effective_user.id
        user = await db.get_user(user_id)
        interface_lang = user.get('language', 'ru') if user else 'ru'
        # Получаем текущий язык разговорника из context (если был выбран ранее)
        audio_lang = context.user_data.get('audio_lang')
        await show_lessons_menu(update, context, language=interface_lang, category=category, page=page, audio_lang=audio_lang)
    
    async def handle_play_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик проигрывания урока"""
        query = update.callback_query
        if not query:
            return
        parts = query.data.split('_')
        if len(parts) < 3:
            await query.answer("Ошибка")
            return
        # Формат: play_{category}_{order}
        # Категория может содержать подчеркивания (например, mini_dialogs)
        # Поэтому берем все части кроме первой (play) и последней (order)
        category = '_'.join(parts[1:-1])  # Все части между 'play' и номером урока
        try:
            order = int(parts[-1])  # Последняя часть - номер урока
        except ValueError:
            await query.answer("Ошибка: неверный формат")
            return
        # Получаем язык пользователя из базы данных
        user_id = update.effective_user.id
        user = await db.get_user(user_id)
        language = user.get('language', 'ru') if user else 'ru'
        await play_lesson(update, context, language=language, category=category, order=order)
    
    async def handle_switch_lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик переключения языка разговорника"""
        query = update.callback_query
        if not query:
            return
        parts = query.data.split('_')
        if len(parts) < 5:
            await query.answer("Ошибка")
            return
        # Формат: switch_lang_{audio_lang}_{category}_{page}
        audio_lang = parts[2]  # ru или en
        category = '_'.join(parts[3:-1])  # Категория может содержать подчеркивания
        try:
            page = int(parts[-1])  # Последняя часть - номер страницы
        except ValueError:
            await query.answer("Ошибка: неверный формат")
            return
        
        # Сохраняем выбранный язык разговорника в context
        context.user_data['audio_lang'] = audio_lang
        
        # Получаем язык интерфейса пользователя из базы данных
        user_id = update.effective_user.id
        user = await db.get_user(user_id)
        interface_lang = user.get('language', 'ru') if user else 'ru'
        
        # Показываем список уроков на выбранном языке разговорника
        await show_lessons_menu(update, context, language=interface_lang, category=category, page=page, audio_lang=audio_lang)
    
    application.add_handler(CallbackQueryHandler(handle_noop, pattern="^noop$"))
    application.add_handler(CallbackQueryHandler(handle_switch_lang, pattern=r"^switch_lang_"))
    application.add_handler(CallbackQueryHandler(handle_list_page, pattern=r"^list_"))
    application.add_handler(CallbackQueryHandler(handle_play_lesson, pattern=r"^play_"))
    
    return application


def main():
    """Главная функция запуска бота (polling для локальной разработки)"""
    application = get_bot_application()
    
    # Запуск бота через polling
    logger.info("Бот запущен через polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()

