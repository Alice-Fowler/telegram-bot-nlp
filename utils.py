import re
import logging
from datetime import datetime, timedelta
from typing import Tuple, Optional, List, Dict, Any

logger = logging.getLogger(__name__)

def parse_amount(text: str) -> Tuple[Optional[float], Optional[str]]:
    """
    Парсит сумму из текста.
    Возвращает (сумма, оставшийся_текст) или (None, None) при ошибке.
    
    Примеры:
    "кофе 300" → (300.0, "кофе")
    "такси 450 руб" → (450.0, "такси")
    "1.5к" → (1500.0, "")
    "5000,50" → (5000.5, "")
    """
    if not text or not text.strip():
        return None, None
    
    text = text.strip()
    
    # Паттерн для чисел с "к" в конце (1.5к, 2к рублей, 1.5k)
    k_pattern = r'^(-?\d+(?:[\.,]\d+)?)\s*[кkK](?:\s*(?:руб\b|рублей\b|рубля\b|р\b|₽\b))?\s*(.*)$'
    k_match = re.search(k_pattern, text, re.IGNORECASE)
    
    if k_match:
        try:
            num_str = k_match.group(1).replace(',', '.')
            num = float(num_str)
            amount = num * 1000
            description = k_match.group(2).strip()
            # Проверяем, что сумма положительная
            if amount <= 0:
                return None, None
            return amount, description if description else ""
        except ValueError:
            pass
    
    # Основные паттерны для обычных чисел
    patterns = [
        # Число с валютой в конце (100 руб, 500 рублей)
        r'^(.+?)\s+(-?\d+(?:[\.,]\d+)?)\s*(руб\b|рублей\b|рубля\b|р\b|₽\b)?$',
        # Просто число с описанием (кофе 300)
        r'^(.+?)\s+(-?\d+(?:[\.,]\d+)?)$',
        # Только число с возможной валютой (500, 750.25)
        r'^(-?\d+(?:[\.,]\d+)?)\s*(руб\b|рублей\b|рубля\b|р\b|₽)?$',
    ]
    

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            groups = match.groups()
            
            if len(groups) == 3:
                # Паттерн 1: описание сумма валюта
                description = groups[0].strip()
                amount_str = groups[1]
            elif len(groups) == 2:
                # Паттерн 2: описание сумма или сумма валюта
                if re.match(r'^-?\d', str(groups[0])):
                    # Только число с валютой
                    amount_str = groups[0]
                    description = ""
                else:
                    # Описание и число
                    description = groups[0].strip()
                    amount_str = groups[1]
            else:
                continue
            
            # Обрабатываем отрицательные числа
            is_negative = amount_str.startswith('-')
            amount_str_clean = amount_str.replace(',', '.').replace('-', '')
            
            try:
                amount = float(amount_str_clean)
                if is_negative:
                    amount = -amount
                
                # Проверяем, что сумма не ноль
                if amount == 0:
                    return None, None
                
                return amount, description
            except ValueError:
                continue
    
    return None, None

def format_money(amount: float) -> str:
    """Форматирует сумму денег для красивого вывода"""
    if amount.is_integer():
        return f"{int(amount):,}".replace(',', ' ')
    else:
        return f"{amount:,.2f}".replace(',', ' ').replace('.', ',')

def format_date(date: datetime) -> str:
    """Форматирует дату для вывода"""
    today = datetime.now().date()
    date_date = date.date()
    
    if date_date == today:
        return f"сегодня в {date.strftime('%H:%M')}"
    elif date_date == today - timedelta(days=1):
        return f"вчера в {date.strftime('%H:%M')}"
    elif date_date.year == today.year:
        return date.strftime("%d.%m в %H:%M")
    else:
        return date.strftime("%d.%m.%Y в %H:%M")

def format_transaction(transaction: Dict[str, Any], index: int = None) -> str:
    """Форматирует транзакцию для вывода в списке"""
    try:
        prefix = f"{index}. " if index is not None else ""
        
        # Безопасное получение даты
        date_obj = transaction.get('transaction_date')
        if isinstance(date_obj, str):
            try:
                date_obj = datetime.fromisoformat(date_obj.replace('Z', '+00:00'))
            except:
                date_obj = datetime.now()
        elif not isinstance(date_obj, datetime):
            date_obj = datetime.now()
        
        date_str = format_date(date_obj)
        
        # Безопасное получение категории
        category = transaction.get('category_name') or 'Без категории'
        
        # Безопасное получение описания
        description = transaction.get('description', '')
        if description and len(description) > 50:
            description = description[:47] + "..."
        
        if description:
            desc_text = f" - {description}"
        else:
            desc_text = ""
        
        # Безопасное получение суммы
        amount = transaction.get('amount', 0)
        try:
            amount_float = float(amount)
        except (ValueError, TypeError):
            amount_float = 0
        
        return (
            f"{prefix}*{date_str}*{desc_text}\n"
            f"   💰 {format_money(amount_float)} | 🏷 {category}"
        )
    except Exception as e:
        logger.error(f"Ошибка в format_transaction: {e}")
        return f"{prefix if index else ''}Ошибка отображения транзакции"

def validate_amount(amount_str: str) -> Tuple[bool, Optional[float], str]:
    """
    Валидация введенной суммы.
    Возвращает (успех, сумма_числом, сообщение_об_ошибке)
    """
    if not amount_str or not amount_str.strip():
        return False, None, "Введите сумму"
    
    # Парсим сумму
    amount, _ = parse_amount(amount_str)
    
    if amount is None:
        return False, None, (
            "Не могу распознать сумму. Примеры:\n"
            "• 500\n"
            "• 1.5к\n"
            "• 250,50\n"
            "• 1000 руб"
        )
    
    # Ключевое исправление: проверяем, что сумма положительная
    # Отрицательные числа должны приводить к ошибке валидации
    if amount <= 0:
        return False, None, "Сумма должна быть положительной"
    
    if amount > 1000000000:  # 1 миллиард
        return False, None, "Слишком большая сумма. Проверьте ввод."
    
    return True, amount, ""

def get_period_dates(period: str) -> Tuple[datetime, datetime]:
    """Возвращает даты начала и конца периода"""
    now = datetime.now()
    
    if period == 'day':
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
    elif period == 'week':
        start = now - timedelta(days=now.weekday())
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
    elif period == 'month':
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = now
    elif period == 'year':
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end = now
    else:  # all
        start = datetime(2000, 1, 1)
        end = now
    
    return start, end

# utils.py (Аналитика и рекомендации)

def analyze_spending_patterns(stats: Dict[str, Any]) -> List[str]:
    """Анализирует паттерны трат и возвращает insights"""
    insights = []
    
    overall = stats.get('overall', {})
    by_category = stats.get('by_category', [])
    most_expensive = stats.get('most_expensive')
    
    if not overall.get('transaction_count', 0):
        insights.append("📭 У вас еще нет транзакций за этот период.")
        return insights
    
    total_amount = overall.get('total_amount', 0)
    transaction_count = overall.get('transaction_count', 0)
    
    # Insight 1: Общая сумма
    if total_amount > 0:
        insights.append(f"💰 Общая сумма трат: {format_money(total_amount)}")
    
    # Insight 2: Средний чек
    avg_amount = overall.get('avg_amount', 0)
    if avg_amount > 0:
        insights.append(f"📊 Средний чек: {format_money(avg_amount)}")
    
    # Insight 3: Самые затратные категории
    if by_category:
        top_categories = by_category[:3]
        if len(top_categories) > 0:
            cat_insight = "🏆 Топ категории: "
            for i, cat in enumerate(top_categories, 1):
                percentage = (cat['total'] / total_amount * 100) if total_amount > 0 else 0
                cat_insight += f"{cat['category']} ({percentage:.1f}%)"
                if i < len(top_categories):
                    cat_insight += ", "
            insights.append(cat_insight)
    
    # Insight 4: Самая дорогая покупка
    if most_expensive:
        insights.append(
            f"👑 Самая дорогая покупка: {most_expensive.get('description', 'Без описания')} "
            f"за {format_money(most_expensive.get('amount', 0))}"
        )
    
    # Insight 5: Частота транзакций
    days_in_period = stats.get('days_in_period', 30)
    avg_transactions_per_day = transaction_count / days_in_period if days_in_period > 0 else 0
    
    if avg_transactions_per_day > 2:
        insights.append(f"⚡ Вы активный пользователь: {avg_transactions_per_day:.1f} транзакций в день")
    elif avg_transactions_per_day < 0.5:
        insights.append(f"🐌 Вы экономный пользователь: {avg_transactions_per_day:.1f} транзакций в день")
    
    return insights

def generate_budget_recommendations(stats: Dict[str, Any]) -> List[str]:
    """Генерирует рекомендации по бюджету на основе метода 50/30/20"""
    from config import BUDGET_RATIOS, CATEGORY_GROUPS
    
    recommendations = []
    total_amount = stats.get('overall', {}).get('total_amount', 0)
    
    if total_amount <= 0:
        recommendations.append("📭 Недостаточно данных для рекомендаций по бюджету.")
        return recommendations
    
    # Группируем расходы по категориям
    category_expenses = {cat['category']: cat['total'] for cat in stats.get('by_category', [])}
    
    # Суммируем расходы по группам
    group_expenses = {'essentials': 0, 'wants': 0, 'savings': 0}
    
    for group, categories in CATEGORY_GROUPS.items():
        for category in categories:
            group_expenses[group] += category_expenses.get(category, 0)
    
    # Расчет процентов
    group_percentages = {}
    for group, amount in group_expenses.items():
        percentage = (amount / total_amount * 100) if total_amount > 0 else 0
        group_percentages[group] = percentage
    
    # Анализ отклонений от идеала
    for group, ideal_percentage in BUDGET_RATIOS.items():
        actual_percentage = group_percentages.get(group, 0)
        deviation = actual_percentage - (ideal_percentage * 100)
        
        group_names = {
            'essentials': 'Обязательные расходы',
            'wants': 'Желания',
            'savings': 'Накопления'
        }
        if deviation > 10:  # Превышение более чем на 10%
            recommendations.append(
                f"⚠️  **{group_names[group]}** превышают норму: "
                f"{actual_percentage:.1f}% вместо {ideal_percentage*100:.0f}% "
                f"(+{deviation:.1f}%)"
            )
        elif deviation < -10:  # Недостаток более чем на 10%
            recommendations.append(
                f"⚠️  **{group_names[group]}** ниже нормы: "
                f"{actual_percentage:.1f}% вместо {ideal_percentage*100:.0f}% "
                f"({deviation:.1f}%) "
            )
        else:
            recommendations.append(
                f"🎯  **{group_names[group]}** в норме: "
                f"{actual_percentage:.1f}% при норме {ideal_percentage*100:.0f}% - Отличный резуль"
            )
    
    # Общая рекомендация
    essentials_ok = abs(group_percentages['essentials'] - (BUDGET_RATIOS['essentials'] * 100)) <= 10
    wants_ok = abs(group_percentages['wants'] - (BUDGET_RATIOS['wants'] * 100)) <= 10
    
    if essentials_ok and wants_ok:
        recommendations.append("\n💪 **Отличное распределение бюджета!** Вы следуете правилу 50/30/20.")
    elif not essentials_ok:
        recommendations.append("\n🔧 **Совет:** Попробуйте сократить обязательные расходы.")
    elif not wants_ok:
        recommendations.append("\n🎯 **Совет:** Сократите траты на развлечения и желания.")
    
    return recommendations

def format_budget_status(budget: Dict[str, Any]) -> str:
    """Форматирует статус бюджета для отображения"""
    category = budget.get('category', 'Неизвестно')
    limit = budget.get('amount_limit', 0)
    spent = budget.get('current_spent', 0)
    remaining = budget.get('remaining', 0)
    percentage = budget.get('percentage', 0)
    
    # Создаем прогресс-бар
    bar_length = 10
    filled = int(percentage / 100 * bar_length)
    progress_bar = "█" * filled + "░" * (bar_length - filled)
    
    status = "✅" if percentage <= 90 else "⚠️" if percentage <= 100 else "❌"
    
    if percentage > 100:
        exceeded_by = spent - limit
        return (
            f"{status} *{category}*\n"
            f"{progress_bar} {percentage:.1f}%\n"
            f"Лимит: {format_money(limit)}\n"
            f"Потрачено: {format_money(spent)}\n"
            f"**Превышение:** {format_money(exceeded_by)}"
        )
    else:
        return (
            f"{status} *{category}*\n"
            f"{progress_bar} {percentage:.1f}%\n"
            f"Лимит: {format_money(limit)}\n"
            f"Потрачено: {format_money(spent)}\n"
            f"Осталось: {format_money(remaining)}"
        )