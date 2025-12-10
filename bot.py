import logging
from telegram import (
    Update,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

from config import API_TOKEN, CONFIDENCE_THRESHOLD
import database
import utils
import nlp_classifier
import visualization

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

classifier = None
# Состояния для ConversationHandler (будем использовать позже)
DESCRIPTION, AMOUNT, CONFIRM_CATEGORY = range(3)
FAST_CATEGORY, FAST_AMOUNT = range(3, 5)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start - регистрация пользователя"""
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    
    # Регистрируем пользователя в БД
    is_new_user = database.add_user(user_id)
    
    if is_new_user:
        await update.message.reply_text(
            f"👋 Привет, {username}!\n"
            f"Добро пожаловать в ваш персональный Финансовый ассистент!\n\n"
            "📊 Я помогу вам:\n"
            "• Учитывать доходы и расходы\n"
            "• Автоматически определять категории трат\n"
            "• Следить за бюджетом\n"
            "• Получать полезные советы\n\n"
            "📋 Используйте /help для списка команд"
        )
    else:
        await update.message.reply_text(
            f"С возвращением, {username}! 👋\n"
            "Рад снова вас видеть!\n"
            "Используйте /help для списка команд"
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = (
        "📋 Доступные команды:\n\n"
        "• /start - Начать работу с ботом\n"
        "• /help - Показать это сообщение\n"
        "• /cancel - Отменить текущую операцию\n\n"
        "💸 Управление финансами:\n"
        "• /add - Добавить транзакцию (текстовый ввод)\n"
        "• /fast - Быстро добавить (выбор категории)\n"
        "• /report - Посмотреть отчет\n"
        "• /categories - Показать все категории\n\n"
        "📈 Аналитика и визуализация:\n"
        "• /stats [период] - Детальная статистика\n"
        "• /budget - Управление бюджетами\n"
        "• /advice - Получить рекомендации\n"
        "• /test_nlp - Протестировать NLP модель\n\n"
    )
    
    await update.message.reply_text(help_text)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /cancel"""
    await update.message.reply_text(
        "Операция отменена. Вы можете начать заново.",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

async def show_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /categories - показывает все категории"""
    categories = database.get_all_categories()
    
    if not categories:
        await update.message.reply_text("Категории еще не созданы.")
        return
    
    categories_text = "📁 *Доступные категории:*\n\n"
    for i, cat in enumerate(categories, 1):
        categories_text += f"{i}. {cat['name']}\n"
    
    await update.message.reply_text(categories_text, parse_mode='Markdown')

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Получено сообщение: {update.message.text}\n"
        f"Команда не распознана! Используйте /help для списка команд."
    )

# bot.py (обновление 1)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок с подробным логированием"""
    logger.error("Exception while handling an update:", exc_info=context.error)
    
    # Логируем детали обновления
    if update:
        if update.effective_user:
            logger.error(f"User: {update.effective_user.id}, {update.effective_user.username}")
        if update.effective_message:
            logger.error(f"Message: {update.effective_message.text}")
        if update.callback_query:
            logger.error(f"Callback: {update.callback_query.data}")
    
    # Отправляем пользователю сообщение об ошибке
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "😕 Произошла ошибка. Пожалуйста, попробуйте еще раз или используйте /help.\n"
                "Если ошибка повторяется, перезапустите бота командой /start."
            )
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение об ошибке: {e}")

async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /report - показывает отчет о транзакциях"""
    user_id = update.effective_user.id
    
    # Получаем последние 10 транзакций
    transactions = database.get_user_transactions(user_id, period='month', limit=10)
    
    if not transactions:
        await update.message.reply_text(
            "📭 *У вас еще нет транзакций.*\n\n"
            "Добавьте первую транзакцию:\n"
            "• Используйте /add для текстового ввода\n"
            "• Или /fast для быстрого добавления",
            parse_mode='Markdown'
        )
        return
    
    # Формируем отчет
    total_spent = sum(t['amount'] for t in transactions)
    
    # Получаем статистику по категориям
    stats = database.get_user_stats(user_id)
    
    report_text = (
        f"📊 *Отчет за текущий месяц*\n\n"
        f"Всего операций: *{len(transactions)}*\n"
        f"Общая сумма: *{utils.format_money(total_spent)}*\n\n"
    )
    
    # Добавляем топ категорий (только если есть статистика)
    if stats and any(stat['total_amount'] > 0 for stat in stats):
        report_text += "*Топ категорий:*\n"
        for i, stat in enumerate(stats[:3], 1):
            if stat['total_amount'] > 0:
                report_text += f"{i}. {stat['category']}: {utils.format_money(stat['total_amount'])}\n"
        report_text += "\n"
    
    report_text += "*Последние транзакции:*\n"
    
    for i, trans in enumerate(transactions[:5], 1):
        # Используем безопасное форматирование
        try:
            report_text += utils.format_transaction(trans, i) + "\n\n"
        except Exception as e:
            logger.error(f"Ошибка форматирования транзакции: {e}")
            report_text += f"{i}. Ошибка отображения транзакции\n\n"
    
    if len(transactions) > 5:
        report_text += f"*... и еще {len(transactions) - 5} операций*\n"
    
    # Добавляем кнопки для разных периодов
    keyboard = [
        [
            InlineKeyboardButton("📅 За день", callback_data="report_day"),
            InlineKeyboardButton("📅 За неделю", callback_data="report_week"),
            InlineKeyboardButton("📅 За месяц", callback_data="report_month")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        report_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def report_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка callback для выбора периода отчета"""
    query = update.callback_query
    await query.answer()
    
    period_map = {
        "report_day": "день",
        "report_week": "неделю",
        "report_month": "месяц"
    }
    
    if query.data in period_map:
        period = query.data.replace("report_", "")
        user_id = query.from_user.id
        
        try:
            transactions = database.get_user_transactions(user_id, period=period, limit=20)
            
            if not transactions:
                await query.edit_message_text(
                    f"📭 За {period_map[query.data]} транзакций нет.",
                    reply_markup=None
                )
                return
            
            total_spent = sum(t.get('amount', 0) for t in transactions)
            
            report_text = (
                f"📊 *Отчет за {period_map[query.data]}*\n\n"
                f"Всего операций: *{len(transactions)}*\n"
                f"Общая сумма: *{utils.format_money(total_spent)}*\n\n"
                f"*Транзакции:*\n"
            )
            
            for i, trans in enumerate(transactions[:10], 1):
                report_text += utils.format_transaction(trans, i) + "\n\n"
            
            if len(transactions) > 10:
                report_text += f"*... и еще {len(transactions) - 10} операций*\n"
            
            await query.edit_message_text(
                report_text,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Ошибка в report_callback: {e}")
            await query.edit_message_text(
                "❌ Произошла ошибка при формировании отчета. Попробуйте снова."
            )

# bot.py (обновление 2)

async def add_transaction_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало процесса добавления транзакции через текст"""
    await update.message.reply_text(
        "💸 *Добавление новой транзакции*\n\n"
        "Введите описание и сумму в одном сообщении:\n"
        "• *кофе 300*\n"
        "• *такси 450 руб*\n"
        "• *продукты 1500,50*\n\n"
        "Или используйте /cancel для отмены",
        parse_mode='Markdown'
    )
    return DESCRIPTION

async def add_transaction_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка введенного текста с суммой и описанием"""
    user_text = update.message.text
    user_id = update.effective_user.id

    # Парсим сумму и описание
    amount, description = utils.parse_amount(user_text)
    
    if amount is None:
        await update.message.reply_text(
            "❌ Не удалось распознать сумму в вашем сообщении.\n\n"
            "Пожалуйста, введите в формате:\n"
            "• *обед 350*\n"
            "• *билеты в кино 1200 руб*\n"
            "• *1.5к на продукты*\n\n"
            "Или используйте /cancel для отмены",
            parse_mode='Markdown'
        )
        return DESCRIPTION
    
    # Сохраняем в контексте
    context.user_data['amount'] = amount
    context.user_data['description'] = description
    
    # Порог высокой уверенности
    HIGH_CONFIDENCE_THRESHOLD = 0.85
    
    # Используем NLP для определения категории
    suggested_category = "Другое"
    confidence = 0.0
    category_id = database.get_category_id(suggested_category)
    is_high_confidence = False
    
    if classifier and description:
        # Получаем предсказание от NLP модели
        category, conf, is_confident = classifier.predict_with_threshold(description)
        
        if is_confident:
            # Модель уверена (>=60%)
            suggested_category = category
            confidence = conf
            category_id = database.get_category_id(category)
            
            # Проверяем высокую уверенность
            is_high_confidence = confidence >= HIGH_CONFIDENCE_THRESHOLD
            
            context.user_data['is_auto_category'] = True
            context.user_data['confidence'] = confidence
            context.user_data['is_high_confidence'] = is_high_confidence
        else:
            # Модель не уверена (<60%) - предложим выбор категории
            suggested_category = "❓ Требуется выбор"
            confidence = conf
            context.user_data['is_auto_category'] = False
            context.user_data['confidence'] = confidence
            context.user_data['is_high_confidence'] = False
    
    context.user_data['suggested_category'] = suggested_category
    context.user_data['category_id'] = category_id
    
    # ЕСЛИ ВЫСОКАЯ УВЕРЕННОСТЬ (>85%) - СОХРАНЯЕМ АВТОМАТИЧЕСКИ
    if is_high_confidence:
        # Автоматически сохраняем транзакцию
        transaction_id = database.insert_transaction(
            user_id=user_id,
            amount=amount,
            description=description,
            category_id=category_id
        )
        
        if transaction_id:
            await update.message.reply_text(
                f"✅ *Транзакция добавлена автоматически!*\n\n"
                f"NLP модель определила категорию с уверенностью {confidence:.1%}\n\n"
                f"ID: #{transaction_id}\n"
                f"Сумма: {utils.format_money(amount)}\n"
                f"Категория: {suggested_category}\n"
                f"Описание: {description if description else 'нет'}\n\n"
                f"_Если категория неверна, вы можете удалить транзакцию из отчета_",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "❌ Ошибка при сохранении транзакции. Попробуйте снова."
            )
        
        # Очищаем временные данные
        context.user_data.clear()
        return ConversationHandler.END
    
    # ЕСЛИ СРЕДНЯЯ УВЕРЕННОСТЬ (60-85%) - ПОДТВЕРЖДЕНИЕ
    elif context.user_data.get('is_auto_category', False):
        # Автоматическая категоризация, но требуется подтверждение
        message_text = (
            f"📝 *Проверьте данные:*\n\n"
            f"*Описание:* {description if description else '(без описания)'}\n"
            f"*Сумма:* {utils.format_money(amount)}\n"
            f"*Категория (авто):* {suggested_category} ({confidence:.1%})\n\n"
            f"Всё верно?"
        )
        
        # Кнопки для подтверждения
        keyboard = [
            [InlineKeyboardButton("✅ Да, все верно", callback_data="confirm_yes")],
            [InlineKeyboardButton("❌ Нет, изменить категорию", callback_data="change_category")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            message_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return CONFIRM_CATEGORY
    
    # ЕСЛИ НИЗКАЯ УВЕРЕННОСТЬ (<60%) - РУЧНОЙ ВЫБОР
    else:
        # Требуется выбор категории
        message_text = (
            f"📝 *Модель не уверена в категории ({confidence:.1%})*\n\n"
            f"*Описание:* {description if description else '(без описания)'}\n"
            f"*Сумма:* {utils.format_money(amount)}\n\n"
            f"Пожалуйста, выберите категорию вручную:"
        )
        
        # Кнопки для выбора категории
        categories = database.get_all_categories()
        keyboard = []
        row = []
        for i, cat in enumerate(categories, 1):
            row.append(InlineKeyboardButton(cat['name'], callback_data=f"select_cat_{cat['id']}"))
            if i % 2 == 0 or i == len(categories):
                keyboard.append(row)
                row = []
        keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel_add")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            message_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return CONFIRM_CATEGORY
    
async def confirm_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка callback от кнопок подтверждения"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "change_category":
        return await change_category_callback(update, context)
    
    if query.data == "confirm_yes":
        # Сохраняем транзакцию (средняя уверенность 60-85%)
        user_id = query.from_user.id
        amount = context.user_data.get('amount')
        description = context.user_data.get('description')
        category_id = context.user_data.get('category_id')
        category_name = context.user_data.get('suggested_category')
        confidence = context.user_data.get('confidence', 0)
        
        if amount and category_id:
            transaction_id = database.insert_transaction(
                user_id=user_id,
                amount=amount,
                description=description,
                category_id=category_id
            )
            
            if transaction_id:
                message = (
                    f"✅ *Транзакция добавлена!*\n\n"
                    f"ID: #{transaction_id}\n"
                    f"Сумма: {utils.format_money(amount)}\n"
                    f"Категория: {category_name} (уверенность: {confidence:.1%})"
                )
                
                await query.edit_message_text(message, parse_mode='Markdown')
            else:
                await query.edit_message_text(
                    "❌ Ошибка при сохранении транзакции. Попробуйте снова."
                )
        else:
            await query.edit_message_text(
                "❌ Данные транзакции потеряны. Попробуйте снова."
            )
        
        # Очищаем временные данные
        context.user_data.clear()
        return ConversationHandler.END
    
    elif query.data == "confirm_no":
        # Возвращаемся к вводу данных
        await query.edit_message_text(
            "Введите данные заново в формате:\n"
            "*описание сумма*",
            parse_mode='Markdown'
        )
        return DESCRIPTION
    
    return CONFIRM_CATEGORY

async def cancel_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена добавления транзакции"""
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Добавление транзакции отменено.",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

# bot.py (обновление 3)

async def fast_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало быстрого добавления через кнопки"""
    # Получаем все категории
    categories = database.get_all_categories()
    
    if not categories:
        await update.message.reply_text("Категории не найдены. Используйте /add для текстового ввода.")
        return ConversationHandler.END
    
    # Создаем клавиатуру с категориями (по 2 в ряд)
    keyboard = []
    row = []
    for i, cat in enumerate(categories, 1):
        row.append(InlineKeyboardButton(cat['name'], callback_data=f"fast_cat_{cat['id']}"))
        if i % 2 == 0 or i == len(categories):
            keyboard.append(row)
            row = []
    
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="fast_cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "💸 *Быстрое добавление транзакции*\n\n"
        "Выберите категорию:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return FAST_CATEGORY

async def fast_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора категории в быстром добавлении"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "fast_cancel":
        await query.edit_message_text("❌ Добавление отменено.")
        return ConversationHandler.END
    
    # Извлекаем ID категории
    if query.data.startswith("fast_cat_"):
        category_id = int(query.data.split("_")[2])
        category_name = None
        
        # Получаем название категории
        categories = database.get_all_categories()
        for cat in categories:
            if cat['id'] == category_id:
                category_name = cat['name']
                break
        
        if not category_name:
            await query.edit_message_text("❌ Категория не найдена.")
            return ConversationHandler.END
        
        # Сохраняем в контексте
        context.user_data['fast_category_id'] = category_id
        context.user_data['fast_category_name'] = category_name
        
        await query.edit_message_text(
            f"🏷 Категория: *{category_name}*\n\n"
            f"Теперь введите сумму:\n"
            f"• *500*\n"
            f"• *1.5к*\n"
            f"• *750,50 руб*\n\n"
            f"Или /cancel для отмены",
            parse_mode='Markdown'
        )
        return FAST_AMOUNT
    
    return FAST_CATEGORY

async def fast_amount_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода суммы в быстром добавлении"""
    user_text = update.message.text
    user_id = update.effective_user.id
    
    # Валидируем сумму
    success, amount, error_msg = utils.validate_amount(user_text)
    
    if not success:
        await update.message.reply_text(
            f"❌ {error_msg}\n\n"
            f"Пожалуйста, введите сумму еще раз:\n"
            f"• *500*\n"
            f"• *1.5к*\n"
            f"• *750,50 руб*",
            parse_mode='Markdown'
        )
        return FAST_AMOUNT
    
    # Получаем данные из контекста
    category_id = context.user_data.get('fast_category_id')
    category_name = context.user_data.get('fast_category_name')
    
    if not category_id:
        await update.message.reply_text("❌ Ошибка: категория не выбрана. Начните заново.")
        context.user_data.clear()
        return ConversationHandler.END
    
    # Сохраняем транзакцию
    transaction_id = database.insert_transaction(
        user_id=user_id,
        amount=amount,
        description=None,  # В быстром вводе без описания
        category_id=category_id
    )
    
    if transaction_id:
        await update.message.reply_text(
            f"✅ *Транзакция добавлена!*\n\n"
            f"ID: #{transaction_id}\n"
            f"Сумма: {utils.format_money(amount)}\n"
            f"Категория: {category_name}",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            "❌ Ошибка при сохранении транзакции. Попробуйте снова."
        )
    
    # Очищаем временные данные
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_fast_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена быстрого добавления"""
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Быстрое добавление отменено.",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

# bot.py (классификатор)

async def init_classifier():
    """Инициализация NLP классификатора"""
    global classifier
    try:
        classifier = nlp_classifier.initialize_classifier()
        logger.info("NLP классификатор инициализирован")
    except Exception as e:
        logger.error(f"Ошибка при инициализации классификатора: {e}")
        classifier = None

async def category_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора категории вручную"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel_add":
        await query.edit_message_text("❌ Добавление транзакции отменено.")
        context.user_data.clear()
        return ConversationHandler.END
    
    if query.data.startswith("select_cat_"):
        # Извлекаем ID выбранной категории
        category_id = int(query.data.split("_")[2])
        
        # Получаем название категории
        categories = database.get_all_categories()
        category_name = None
        for cat in categories:
            if cat['id'] == category_id:
                category_name = cat['name']
                break
        
        if category_name:
            # Сохраняем выбранную категорию
            context.user_data['suggested_category'] = category_name
            context.user_data['category_id'] = category_id
            context.user_data['is_auto_category'] = False
            
            # Показываем подтверждение
            amount = context.user_data.get('amount', 0)
            description = context.user_data.get('description', '')
            
            await query.edit_message_text(
                f"📝 *Подтверждение:*\n\n"
                f"*Описание:* {description if description else '(без описания)'}\n"
                f"*Сумма:* {utils.format_money(amount)}\n"
                f"*Категория (ручной выбор):* {category_name}\n\n"
                f"Сохранить транзакцию?",
                parse_mode='Markdown'
            )
            
            # Показываем кнопки подтверждения
            keyboard = [
                [InlineKeyboardButton("✅ Да, сохранить", callback_data="confirm_yes")],
                [InlineKeyboardButton("❌ Нет, отменить", callback_data="cancel_add")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.message.reply_text(
                "Выберите действие:",
                reply_markup=reply_markup
            )
            
            return CONFIRM_CATEGORY
    
    return CONFIRM_CATEGORY

async def change_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка запроса на изменение категории"""
    query = update.callback_query
    await query.answer()
    
    # Показываем список категорий для выбора
    categories = database.get_all_categories()
    
    keyboard = []
    row = []
    for i, cat in enumerate(categories, 1):
        row.append(InlineKeyboardButton(cat['name'], callback_data=f"select_cat_{cat['id']}"))
        if i % 2 == 0 or i == len(categories):
            keyboard.append(row)
            row = []
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel_add")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "Выберите категорию вручную:",
        reply_markup=reply_markup
    )
    
    return CONFIRM_CATEGORY

async def test_nlp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для тестирования NLP модели"""
    if not classifier:
        await update.message.reply_text("❌ NLP модель не инициализирована")
        return
    
    # Проверяем аргументы
    if not context.args:
        await update.message.reply_text(
            "🧪 *Тестирование NLP модели*\n\n"
            "Используйте: `/test_nlp описание`\n"
            "Пример: `/test_nlp кофе в старбакс`",
            parse_mode='Markdown'
        )
        return
    
    text = " ".join(context.args)
    
    try:
        # Получаем предсказание
        category, confidence, is_confident = classifier.predict_with_threshold(text)
        
        # Получаем все вероятности для детальной информации
        category_full, confidence_full, probabilities = classifier.predict(text, return_probability=True)
        
        # Формируем ответ
        if is_confident:
            status = "✅ УВЕРЕННО"
        else:
            status = "❓ НЕУВЕРЕННО"
        
        response = (
            f"🧪 *Результат NLP анализа:*\n\n"
            f"*Текст:* {text}\n"
            f"*Категория:* {category or 'не определена'}\n"
            f"*Уверенность:* {confidence:.2%}\n"
            f"*Статус:* {status} (порог: {CONFIDENCE_THRESHOLD:.0%})\n\n"
            f"*Все вероятности:*\n"
        )
        
        # Сортируем вероятности по убыванию
        sorted_probs = sorted(probabilities.items(), key=lambda x: x[1], reverse=True)
        for cat, prob in sorted_probs:
            if prob > 0.01:  # Показываем только >1%
                response += f"• {cat}: {prob:.2%}\n"
        
        await update.message.reply_text(response, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Ошибка в test_nlp_command: {e}")
        await update.message.reply_text(f"❌ Ошибка при анализе текста: {str(e)}")

# bot.py (аналитика и рекомендации)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для получения расширенной статистики"""
    user_id = update.effective_user.id
    
    # Определяем период (по умолчанию месяц)
    period = context.args[0] if context.args else 'month'
    valid_periods = ['day', 'week', 'month', 'year']
    
    if period not in valid_periods:
        await update.message.reply_text(
            "📊 *Использование:* `/stats [период]`\n\n"
            "Доступные периоды:\n"
            "• day - за день\n"
            "• week - за неделю\n"
            "• month - за месяц (по умолчанию)\n"
            "• year - за год",
            parse_mode='Markdown'
        )
        return
    
    period_names = {
        'day': 'день',
        'week': 'неделю',
        'month': 'месяц',
        'year': 'год'
    }
    
    # Получаем статистику
    stats = database.get_period_statistics(user_id, period)
    
    if not stats or not stats.get('overall', {}).get('transaction_count', 0):
        await update.message.reply_text(
            f"📭 За {period_names[period]} нет транзакций.",
            parse_mode='Markdown'
        )
        return
    
    # Формируем статистический отчет
    overall = stats['overall']
    
    report = (
        f"📈 *Статистика за {period_names[period]}*\n\n"
        f"*Общие показатели:*\n"
        f"• Количество операций: {overall.get('transaction_count', 0)}\n"
        f"• Общая сумма: {utils.format_money(overall.get('total_amount', 0))}\n"
        f"• Средний чек: {utils.format_money(overall.get('avg_amount', 0))}\n"
        f"• Минимальная трата: {utils.format_money(overall.get('min_amount', 0))}\n"
        f"• Максимальная трата: {utils.format_money(overall.get('max_amount', 0))}\n\n"
    )
    
    # Добавляем топ категорий
    if stats.get('by_category'):
        report += "*Топ категорий по расходам:*\n"
        for i, cat in enumerate(stats['by_category'][:5], 1):
            percentage = (cat['total'] / overall['total_amount'] * 100) if overall['total_amount'] > 0 else 0
            report += f"{i}. {cat['category']}: {utils.format_money(cat['total'])} ({percentage:.1f}%)\n"
        report += "\n"
    
    # Добавляем insights
    insights = utils.analyze_spending_patterns(stats)
    if insights:
        report += "*💡 Инсайты:*\n"
        for insight in insights:
            report += f"• {insight}\n"
        report += "\n"
    
    # Добавляем рекомендации по бюджету (только ключевые)
    recommendations = utils.generate_budget_recommendations(stats)
    if recommendations and len(recommendations) > 0:
        # Берем только первую рекомендацию для краткости
        first_rec = recommendations[0]
        if len(first_rec) < 100:  # Если не слишком длинная
            report += f"*🎯 Рекомендация:*\n• {first_rec}\n\n"
        report += f"_Используйте /advice для полных рекомендаций_\n"
    
    # Создаем клавиатуру с действиями
    keyboard = [
        [
            InlineKeyboardButton("📊 Круговая диаграмма", callback_data=f"chart_pie_{period}"),
            InlineKeyboardButton("📈 Столбчатая диаграмма", callback_data=f"chart_bar_{period}")
        ],
        [
            InlineKeyboardButton("📅 За другой период", callback_data="change_period"),
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        report,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def budget_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для управления бюджетами"""
    user_id = update.effective_user.id
    
    if not context.args:
        # Показываем текущие бюджеты
        budgets = database.get_budget_status(user_id)
        
        if not budgets:
            await update.message.reply_text(
                "💰 *Управление бюджетами*\n\n"
                "У вас пока не установлены бюджеты.\n\n"
                "*Использование:*\n"
                "• `/budget set Категория 5000` - установить бюджет\n"
                "• `/budget list` - показать текущие бюджеты\n"
                "• `/budget delete Категория` - удалить бюджет\n\n"
                "*Пример:* `/budget set Еда 10000`",
                parse_mode='Markdown'
            )
            return
        
        # Формируем список бюджетов
        budget_text = "💰 *Ваши бюджеты:*\n\n"
        total_limit = 0
        total_spent = 0
        
        for budget in budgets:
            budget_text += utils.format_budget_status(budget) + "\n\n"
            total_limit += budget.get('amount_limit', 0)
            total_spent += budget.get('current_spent', 0)
        
        # Общая статистика
        total_percentage = (total_spent / total_limit * 100) if total_limit > 0 else 0
        budget_text += f"*Итого:*\n"
        budget_text += f"Лимит: {utils.format_money(total_limit)}\n"
        budget_text += f"Потрачено: {utils.format_money(total_spent)}\n"
        budget_text += f"Использовано: {total_percentage:.1f}%\n\n"
        
        # Уведомления о превышениях
        exceeded = [b for b in budgets if b.get('is_exceeded', False)]
        if exceeded:
            budget_text += "⚠️  *Превышены лимиты:*\n"
            for budget in exceeded:
                exceeded_by = budget.get('current_spent', 0) - budget.get('amount_limit', 0)
                budget_text += f"• {budget['category']}: +{utils.format_money(exceeded_by)}\n"
        
        await update.message.reply_text(budget_text, parse_mode='Markdown')
        return
    
    action = context.args[0].lower()
    
    if action == 'set' and len(context.args) >= 3:
        # Установка бюджета: /budget set Категория Сумма
        category_name = context.args[1]
        try:
            amount = float(context.args[2].replace(',', '.'))
            
            # Находим ID категории
            category_id = database.get_category_id(category_name)
            if not category_id:
                await update.message.reply_text(
                    f"❌ Категория '{category_name}' не найдена.\n"
                    f"Используйте /categories чтобы увидеть все категории."
                )
                return
            
            # Устанавливаем бюджет
            success = database.set_budget(user_id, category_id, amount, 'monthly')
            
            if success:
                await update.message.reply_text(
                    f"✅ Бюджет установлен!\n"
                    f"Категория: {category_name}\n"
                    f"Лимит: {utils.format_money(amount)} в месяц"
                )
            else:
                await update.message.reply_text("❌ Ошибка при установке бюджета.")
                
        except ValueError:
            await update.message.reply_text(
                "❌ Неверная сумма. Пример: `/budget set Еда 10000`",
                parse_mode='Markdown'
            )
    
    elif action == 'delete' and len(context.args) >= 2:
        # Удаление бюджета: /budget delete Категория
        category_name = context.args[1]
        category_id = database.get_category_id(category_name)
        
        if not category_id:
            await update.message.reply_text(f"❌ Категория '{category_name}' не найдена.")
            return
        
        success = database.delete_budget(user_id, category_id)
        
        if success:
            await update.message.reply_text(f"✅ Бюджет для категории '{category_name}' удален.")
        else:
            await update.message.reply_text(f"❌ Бюджет для категории '{category_name}' не найден.")
    
    elif action == 'list':
        # Показываем бюджеты (уже обработано выше)
        budgets = database.get_budget_status(user_id)
        
        if not budgets:
            await update.message.reply_text("📭 У вас нет установленных бюджетов.")
            return
        
        budget_text = "💰 *Ваши бюджеты:*\n\n"
        for budget in budgets:
            budget_text += utils.format_budget_status(budget) + "\n\n"
        
        await update.message.reply_text(budget_text, parse_mode='Markdown')
    
    else:
        await update.message.reply_text(
            "❌ Неверная команда. Используйте:\n"
            "• `/budget set Категория Сумма`\n"
            "• `/budget delete Категория`\n"
            "• `/budget list`\n"
            "• `/budget` - показать эту справку",
            parse_mode='Markdown'
        )

async def advice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для получения рекомендаций"""
    user_id = update.effective_user.id
    
    # Получаем статистику за месяц
    stats = database.get_period_statistics(user_id, 'month')
    
    if not stats or not stats.get('overall', {}).get('transaction_count', 0):
        await update.message.reply_text(
            "📭 Недостаточно данных для рекомендаций.\n"
            "Добавьте несколько транзакций с помощью /add"
        )
        return
    
    # Генерируем рекомендации
    recommendations = utils.generate_budget_recommendations(stats)
    
    if not recommendations:
        await update.message.reply_text("❌ Не удалось сгенерировать рекомендации.")
        return
    
    advice_text = "💡 *Персональные рекомендации*\n\n"
    
    for i, rec in enumerate(recommendations, 1):
        advice_text += f"{rec}\n"
        if i < len(recommendations):
            advice_text += "\n"
    
    # Добавляем общие советы
    overall = stats['overall']
    total = overall.get('total_amount', 0)
    
    if total > 50000:
        advice_text += "\n💪 *Вы тратите более 50,000 руб в месяц.*\n"
        advice_text += "Рассмотрите возможность ведения детального учета."
    elif total < 10000:
        advice_text += "\n🎯 *Ваши траты ниже 10,000 руб в месяц.*\n"
        advice_text += "Отличный результат по экономии!"
    
    # Проверяем бюджеты
    budgets = database.get_budget_status(user_id)
    if budgets:
        exceeded = [b for b in budgets if b.get('is_exceeded', False)]
        if exceeded:
            advice_text += "\n⚠️  *Обратите внимание:*\n"
            for budget in exceeded[:3]:  # Показываем только 3 самых превышенных
                exceeded_by = budget.get('current_spent', 0) - budget.get('amount_limit', 0)
                advice_text += f"• Превышен бюджет '{budget['category']}' на {utils.format_money(exceeded_by)}\n"
    
    await update.message.reply_text(advice_text, parse_mode='Markdown')

async def chart_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка callback для графиков"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if data.startswith("chart_"):
        # chart_pie_month или chart_bar_week
        parts = data.split("_")
        
        if len(parts) < 3:
            await query.edit_message_text("❌ Ошибка в данных запроса.")
            return
            
        chart_type = parts[1]  # pie или bar
        period = parts[2] if len(parts) > 2 else 'month'
        
        # Получаем статистику
        stats = database.get_period_statistics(user_id, period)
        
        if not stats or not stats.get('by_category'):
            await query.edit_message_text("❌ Нет данных для построения графика.")
            return
        
        # Периоды для отображения
        period_names = {'day': 'день', 'week': 'неделю', 'month': 'месяц', 'year': 'год'}
        period_name = period_names.get(period, 'месяц')
        
        # Создаем график
        try:
            if chart_type == 'pie':
                buf = visualization.create_pie_chart(stats['by_category'], user_id)
                chart_name = "Круговая диаграмма"
            elif chart_type == 'bar':
                buf = visualization.create_bar_chart(stats['by_category'], user_id, period_name)
                chart_name = "Столбчатая диаграмма"
            else:
                await query.edit_message_text("❌ Неизвестный тип графика.")
                return
            
            if buf:
                # Отправляем фото
                await query.message.reply_photo(
                    photo=buf,
                    caption=f"📊 {chart_name} за {period_name}"
                )
                await query.delete_message()
            else:
                await query.edit_message_text("❌ Не удалось создать график.")
                
        except Exception as e:
            logger.error(f"Ошибка при создании графика: {e}")
            await query.edit_message_text("❌ Произошла ошибка при создании графика.")
    
    elif data == "change_period":
        # Кнопки выбора периода
        keyboard = [
            [
                InlineKeyboardButton("📅 День", callback_data="stats_day"),
                InlineKeyboardButton("📅 Неделя", callback_data="stats_week")
            ],
            [
                InlineKeyboardButton("📅 Месяц", callback_data="stats_month"),
                InlineKeyboardButton("📅 Год", callback_data="stats_year")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "Выберите период для статистики:",
            reply_markup=reply_markup
        )
    
    elif data.startswith("stats_"):
        # Показываем статистику для выбранного периода
        period = data.split("_")[1]
        
        # Закрываем текущее сообщение
        await query.delete_message()
        
        # Создаем fake context для вызова stats_command
        from copy import copy
        fake_context = copy(context)
        fake_context.args = [period]
        
        # Создаем fake update
        class FakeUpdate:
            def __init__(self, user, message):
                self.effective_user = user
                self.effective_message = message
                self.message = message
        
        fake_update = FakeUpdate(query.from_user, query.message)
        
        try:
            await stats_command(fake_update, fake_context)
        except Exception as e:
            logger.error(f"Ошибка при показе статистики: {e}")
            await query.message.reply_text("❌ Ошибка при получении статистики.")

async def stats_command_with_period(update: Update, context: ContextTypes.DEFAULT_TYPE, period: str):
    """Вспомогательная функция для показа статистики по периоду"""
    # Создаем fake update для вызова stats_command
    from copy import copy
    fake_context = copy(context)
    fake_context.args = [period]
    
    user = update.effective_user
    if hasattr(update, 'callback_query'):
        message = update.callback_query.message
    else:
        message = update.message
    
    # Создаем fake update
    class FakeUpdate:
        def __init__(self, user, message):
            self.effective_user = user
            self.message = message
    
    fake_update = FakeUpdate(user, message)
    await stats_command(fake_update, fake_context)

async def check_budget_notifications(context: ContextTypes.DEFAULT_TYPE):
    """Проверяет и отправляет уведомления о приближении к лимиту"""
    try:
        # Здесь можно реализовать периодическую проверку
        # Для простоты будем проверять при каждой команде /budget
        pass
    except Exception as e:
        logger.error(f"Ошибка в check_budget_notifications: {e}")

def main():
    """Основная функция запуска бота"""
    # Инициализируем базу данных
    database.init_db()
    logger.info("База данных готова к работе")
    
    # Инициализируем NLP классификатор
    import asyncio
    try:
        asyncio.run(init_classifier())
    except RuntimeError:
        # Если event loop уже запущен
        loop = asyncio.get_event_loop()
        loop.run_until_complete(init_classifier())

    # Создаем приложение
    application = Application.builder().token(API_TOKEN).build()
    
    # ConversationHandler для текстового добавления транзакции
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("add", add_transaction_start)],
        states={
            DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_transaction_text),
                CommandHandler("cancel", cancel_add)
            ],
            CONFIRM_CATEGORY: [
                CallbackQueryHandler(confirm_category_callback, pattern="^confirm_"),
                CallbackQueryHandler(change_category_callback, pattern="^change_category"),
                CallbackQueryHandler(category_selection_callback, pattern="^select_cat_"),
                CallbackQueryHandler(category_selection_callback, pattern="^cancel_add"),
                CommandHandler("cancel", cancel_add)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel_add)],
        allow_reentry=True,
    )
    
    # ConversationHandler для быстрого добавления
    fast_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("fast", fast_add_start)],
        states={
            FAST_CATEGORY: [
                CallbackQueryHandler(fast_category_callback, pattern="^fast_"),
                CommandHandler("cancel", cancel_fast_add)
            ],
            FAST_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, fast_amount_input),
                CommandHandler("cancel", cancel_fast_add)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel_fast_add)],
        allow_reentry=True,
    )
    
    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CommandHandler("categories", show_categories))
    application.add_handler(CommandHandler("report", report_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("budget", budget_command))
    application.add_handler(CommandHandler("advice", advice_command))
    application.add_handler(CommandHandler("test_nlp", test_nlp_command))

    # Регистрируем ConversationHandler'ы
    application.add_handler(conv_handler)
    application.add_handler(fast_conv_handler)

    # Регистрируем callback обработчики
    application.add_handler(CallbackQueryHandler(report_callback, pattern="^report_"))
    application.add_handler(CallbackQueryHandler(chart_callback, pattern="^(chart_|stats_|change_period)"))
    
    # Обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Запускаем бота
    logger.info("Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()