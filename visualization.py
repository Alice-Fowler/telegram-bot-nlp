import matplotlib.pyplot as plt
import matplotlib
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import io

# Используем бэкенд, который не требует GUI
matplotlib.use('Agg')  # Важно для работы на сервере

from config import BASE_DIR

logger = logging.getLogger(__name__)

def create_pie_chart(category_stats: List[Dict[str, Any]], user_id: int) -> Optional[io.BytesIO]:
    """
    Создает круговую диаграмму расходов по категориям.
    Возвращает BytesIO объект с изображением.
    """
    try:
        if not category_stats:
            logger.warning("Нет данных для создания диаграммы")
            return None
        
        # Подготавливаем данные
        categories = []
        amounts = []
        colors = plt.cm.Set3.colors  # Цветовая палитра
        
        for stat in category_stats:
            if stat.get('total', 0) > 0:
                categories.append(stat.get('category', 'Без категории'))
                amounts.append(stat.get('total', 0))
        
        if not amounts:
            return None
        
        # Создаем диаграмму
        fig, ax = plt.subplots(figsize=(10, 8))
        
        # Круговая диаграмма с выносками
        wedges, texts, autotexts = ax.pie(
            amounts,
            labels=categories,
            autopct=lambda pct: f'{pct:.1f}%' if pct > 3 else '',
            startangle=90,
            colors=colors[:len(amounts)],
            explode=[0.05] * len(amounts),  # Немного раздвигаем сектора
            shadow=True
        )
        
        # Настройка текста
        plt.setp(autotexts, size=10, weight="bold", color='black')
        plt.setp(texts, size=9)
        
        # Заголовок
        ax.set_title('📊 Распределение расходов по категориям', fontsize=14, fontweight='bold', pad=20)
        
        # Легенда
        ax.legend(
            wedges,
            [f"{cat}: {amt:,.0f} руб" for cat, amt in zip(categories, amounts)],
            title="Категории",
            loc="center left",
            bbox_to_anchor=(1, 0, 0.5, 1),
            fontsize=9
        )
        
        # Сохраняем в буфер
        buf = io.BytesIO()
        plt.tight_layout()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)
        
        logger.info(f"Создана круговая диаграмма для пользователя {user_id}")
        return buf
        
    except Exception as e:
        logger.error(f"Ошибка при создании круговой диаграммы: {e}")
        return None

def create_bar_chart(category_stats: List[Dict[str, Any]], user_id: int, period: str = 'месяц') -> Optional[io.BytesIO]:
    """
    Создает столбчатую диаграмму расходов по категориям.
    """
    try:
        if not category_stats:
            return None
        
        # Подготавливаем данные
        categories = []
        amounts = []
        
        for stat in category_stats:
            if stat.get('total', 0) > 0:
                categories.append(stat.get('category', 'Без категории'))
                amounts.append(stat.get('total', 0))
        
        if not amounts:
            return None
        
        # Создаем диаграмму
        fig, ax = plt.subplots(figsize=(12, 7))
        
        # Столбцы
        bars = ax.bar(categories, amounts, color=plt.cm.tab20c.colors[:len(categories)])
        
        # Подписи значений на столбцах
        for bar, amount in zip(bars, amounts):
            height = bar.get_height()
            ax.text(
                bar.get_x() + bar.get_width() / 2.,
                height + max(amounts) * 0.01,
                f'{amount:,.0f}',
                ha='center',
                va='bottom',
                fontsize=9
            )
        
        # Настройка осей
        ax.set_ylabel('Сумма (руб)', fontsize=12)
        ax.set_xlabel('Категории', fontsize=12)
        ax.set_title(f'📈 Расходы по категориям за {period}', fontsize=14, fontweight='bold', pad=20)
        
        # Поворачиваем подписи категорий
        plt.setp(ax.get_xticklabels(), rotation=45, ha='right', fontsize=9)
        
        # Сетка
        ax.yaxis.grid(True, linestyle='--', alpha=0.7)
        ax.set_axisbelow(True)
        
        # Автоматический подбор масштаба
        plt.tight_layout()
        
        # Сохраняем в буфер
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)
        
        logger.info(f"Создана столбчатая диаграмма для пользователя {user_id}")
        return buf
        
    except Exception as e:
        logger.error(f"Ошибка при создании столбчатой диаграммы: {e}")
        return None

def create_timeline_chart(transactions: List[Dict[str, Any]], user_id: int) -> Optional[io.BytesIO]:
    """
    Создает график трат по времени.
    """
    try:
        if not transactions or len(transactions) < 3:
            return None
        
        # Группируем по дате
        from collections import defaultdict
        import pandas as pd
        
        # Преобразуем даты
        date_amounts = defaultdict(float)
        for trans in transactions:
            date_str = trans.get('transaction_date')
            if isinstance(date_str, str):
                try:
                    # Пробуем разные форматы дат
                    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d.%m.%Y %H:%M']:
                        try:
                            date = datetime.strptime(date_str[:10], '%Y-%m-%d')
                            break
                        except:
                            continue
                    else:
                        continue
                except:
                    continue
            else:
                date = trans.get('transaction_date')
                if not isinstance(date, datetime):
                    continue
            
            date_key = date.strftime('%Y-%m-%d')
            date_amounts[date_key] += trans.get('amount', 0)
        
        if not date_amounts:
            return None
        
        # Сортируем по дате
        sorted_dates = sorted(date_amounts.items())
        dates = [item[0] for item in sorted_dates]
        amounts = [item[1] for item in sorted_dates]
        
        # Создаем график
        fig, ax = plt.subplots(figsize=(12, 6))
        
        # Линейный график
        ax.plot(dates, amounts, marker='o', linewidth=2, markersize=6, color='#2E86AB')
        
        # Заполнение под графиком
        ax.fill_between(dates, amounts, alpha=0.3, color='#2E86AB')
        
        # Настройки
        ax.set_title('📅 Динамика трат по дням', fontsize=14, fontweight='bold', pad=20)
        ax.set_ylabel('Сумма (руб)', fontsize=12)
        ax.set_xlabel('Дата', fontsize=12)
        
        # Поворачиваем даты
        plt.setp(ax.get_xticklabels(), rotation=45, ha='right', fontsize=8)
        
        # Сетка
        ax.grid(True, linestyle='--', alpha=0.7)
        ax.set_axisbelow(True)
        
        # Автоматический подбор масштаба
        plt.tight_layout()
        
        # Сохраняем в буфер
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)
        
        logger.info(f"Создан график динамики для пользователя {user_id}")
        return buf
        
    except Exception as e:
        logger.error(f"Ошибка при создании графика динамики: {e}")
        return None

def save_chart_to_file(buf: io.BytesIO, user_id: int, chart_type: str = 'pie') -> Optional[str]:
    """Сохраняет график в файл и возвращает путь"""
    try:
        # Создаем папку для графиков
        charts_dir = BASE_DIR / 'charts'
        charts_dir.mkdir(exist_ok=True)
        
        # Генерируем имя файла
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"chart_{user_id}_{chart_type}_{timestamp}.png"
        filepath = charts_dir / filename
        
        # Сохраняем
        with open(filepath, 'wb') as f:
            f.write(buf.getvalue())
        
        logger.info(f"График сохранен: {filepath}")
        return str(filepath)
        
    except Exception as e:
        logger.error(f"Ошибка при сохранении графика: {e}")
        return None