import sqlite3
import logging
from datetime import datetime
from typing import Any, Dict, List
from config import DB_PATH, DEFAULT_CATEGORIES

logger = logging.getLogger(__name__)

def get_db_connection():
    """Создает и возвращает соединение с базой данных"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Чтобы получать данные как словарь
    return conn

def init_db():
    """Инициализация базы данных: создание таблиц и заполнение категорий"""
    
    # SQL-запросы для создания таблиц (точно как в ТЗ)
    create_tables_sql = [
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            description TEXT,
            category_id INTEGER,
            transaction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id),
            FOREIGN KEY (category_id) REFERENCES categories (id)
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            category_id INTEGER NOT NULL,
            amount_limit REAL NOT NULL,
            period TEXT DEFAULT 'monthly',
            FOREIGN KEY (user_id) REFERENCES users (user_id),
            FOREIGN KEY (category_id) REFERENCES categories (id),
            UNIQUE(user_id, category_id, period)
        );
        """
    ]
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Создаем таблицы
        for sql in create_tables_sql:
            cursor.execute(sql)
        
        # Заполняем таблицу категорий предустановленными значениями
        for category_name in DEFAULT_CATEGORIES:
            try:
                cursor.execute(
                    "INSERT OR IGNORE INTO categories (name) VALUES (?)",
                    (category_name,)
                )
            except sqlite3.IntegrityError:
                pass  # Категория уже существует
        
        conn.commit()
        logger.info("База данных успешно инициализирована")
        
    except sqlite3.Error as e:
        logger.error(f"Ошибка при инициализации БД: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

def add_user(user_id):
    """Добавляет нового пользователя в базу данных"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "INSERT OR IGNORE INTO users (user_id) VALUES (?)",
            (user_id,)
        )
        conn.commit()
        
        if cursor.rowcount > 0:
            logger.info(f"Добавлен новый пользователь: {user_id}")
            return True
        return False
        
    except sqlite3.Error as e:
        logger.error(f"Ошибка при добавлении пользователя {user_id}: {e}")
        return False
    finally:
        conn.close()

def get_category_id(category_name):
    """Возвращает ID категории по названию"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT id FROM categories WHERE name = ?",
        (category_name,)
    )
    result = cursor.fetchone()
    conn.close()
    
    return result['id'] if result else None

def get_all_categories():
    """Возвращает список всех категорий"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, name FROM categories ORDER BY name")
    categories = cursor.fetchall()
    conn.close()
    
    return [dict(cat) for cat in categories]

# database.py (основные)

def insert_transaction(user_id, amount, description=None, category_id=None):
    """Добавляет новую транзакцию в базу данных"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            """
            INSERT INTO transactions 
            (user_id, amount, description, category_id, transaction_date)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, amount, description, category_id, datetime.now())
        )
        
        transaction_id = cursor.lastrowid
        conn.commit()
        logger.info(f"Добавлена транзакция {transaction_id} для пользователя {user_id}")
        
        return transaction_id
        
    except sqlite3.Error as e:
        logger.error(f"Ошибка при добавлении транзакции: {e}")
        conn.rollback()
        return None
    finally:
        conn.close()

def get_user_transactions(user_id, period='month', limit=50):
    """Возвращает транзакции пользователя за указанный период"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Определяем дату начала периода
    from datetime import datetime, timedelta
    now = datetime.now()
    
    if period == 'day':
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == 'week':
        start_date = now - timedelta(days=now.weekday())
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == 'month':
        start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == 'year':
        start_date = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        # Все транзакции
        start_date = datetime(2000, 1, 1)
    
    try:
        cursor.execute(
            """
            SELECT t.id, t.amount, t.description, c.name as category_name,
                   t.transaction_date, t.category_id
            FROM transactions t
            LEFT JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = ? AND t.transaction_date >= ?
            ORDER BY t.transaction_date DESC
            LIMIT ?
            """,
            (user_id, start_date, limit)
        )
        
        transactions = cursor.fetchall()
        return [dict(trans) for trans in transactions]
        
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении транзакций: {e}")
        return []
    finally:
        conn.close()

def get_user_stats(user_id, start_date=None, end_date=None):
    """Возвращает статистику по категориям для пользователя"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        query = """
            SELECT 
                COALESCE(c.name, 'Без категории') as category, 
                SUM(t.amount) as total_amount,
                COUNT(t.id) as transaction_count
            FROM transactions t
            LEFT JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = ?
        """
        params = [user_id]
        
        if start_date:
            query += " AND t.transaction_date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND t.transaction_date <= ?"
            params.append(end_date)
        
        query += " GROUP BY c.name ORDER BY total_amount DESC"
        
        cursor.execute(query, params)
        stats = cursor.fetchall()
        
        # Преобразуем в список словарей
        result = []
        for row in stats:
            result.append({
                'category': row['category'],
                'total_amount': row['total_amount'] or 0,
                'transaction_count': row['transaction_count'] or 0
            })
        
        return result
        
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении статистики: {e}")
        return []
    finally:
        conn.close()

# database.py (аналитика)

def get_period_statistics(user_id: int, period: str = 'month') -> Dict[str, Any]:
    """Получает статистику за период"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Определяем даты периода
    from datetime import datetime, timedelta
    now = datetime.now()
    
    if period == 'day':
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == 'week':
        start_date = now - timedelta(days=now.weekday())
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == 'month':
        start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == 'year':
        start_date = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        start_date = datetime(2000, 1, 1)  # Все время
    
    end_date = now
    
    try:
        # Общая статистика
        cursor.execute("""
            SELECT 
                COUNT(*) as transaction_count,
                SUM(amount) as total_amount,
                AVG(amount) as avg_amount,
                MIN(amount) as min_amount,
                MAX(amount) as max_amount
            FROM transactions 
            WHERE user_id = ? 
            AND transaction_date >= ?
            AND transaction_date <= ?
        """, (user_id, start_date, end_date))
        
        overall_stats = dict(cursor.fetchone() or {})
        
        # Статистика по категориям
        cursor.execute("""
            SELECT 
                c.name as category,
                COUNT(t.id) as count,
                SUM(t.amount) as total,
                AVG(t.amount) as avg_amount
            FROM transactions t
            LEFT JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = ? 
            AND t.transaction_date >= ?
            AND t.transaction_date <= ?
            GROUP BY c.name
            ORDER BY total DESC
        """, (user_id, start_date, end_date))
        
        category_stats = []
        for row in cursor.fetchall():
            category_stats.append(dict(row))
        
        # Самая дорогая транзакция
        cursor.execute("""
            SELECT 
                t.description,
                t.amount,
                c.name as category,
                t.transaction_date
            FROM transactions t
            LEFT JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = ? 
            AND t.transaction_date >= ?
            AND t.transaction_date <= ?
            ORDER BY t.amount DESC
            LIMIT 1
        """, (user_id, start_date, end_date))
        
        most_expensive = dict(cursor.fetchone()) if cursor.rowcount > 0 else None
        
        # Самая частая категория
        cursor.execute("""
            SELECT 
                c.name as category,
                COUNT(t.id) as count
            FROM transactions t
            LEFT JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = ? 
            AND t.transaction_date >= ?
            AND t.transaction_date <= ?
            GROUP BY c.name
            ORDER BY count DESC
            LIMIT 1
        """, (user_id, start_date, end_date))
        
        most_frequent = dict(cursor.fetchone()) if cursor.rowcount > 0 else None
        
        conn.close()
        
        return {
            'period': period,
            'start_date': start_date,
            'end_date': end_date,
            'overall': overall_stats,
            'by_category': category_stats,
            'most_expensive': most_expensive,
            'most_frequent': most_frequent,
            'days_in_period': (end_date - start_date).days + 1
        }
        
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении статистики: {e}")
        conn.close()
        return {}

def get_budget_status(user_id: int) -> List[Dict[str, Any]]:
    """Получает статус бюджетов по категориям"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Получаем все бюджеты пользователя
        cursor.execute("""
            SELECT 
                b.id,
                c.name as category,
                b.amount_limit,
                b.period,
                COALESCE(SUM(t.amount), 0) as current_spent
            FROM budgets b
            JOIN categories c ON b.category_id = c.id
            LEFT JOIN transactions t ON b.category_id = t.category_id 
                AND t.user_id = b.user_id
                AND (
                    (b.period = 'monthly' AND strftime('%Y-%m', t.transaction_date) = strftime('%Y-%m', 'now'))
                    OR (b.period = 'weekly' AND strftime('%Y-%W', t.transaction_date) = strftime('%Y-%W', 'now'))
                )
            WHERE b.user_id = ?
            GROUP BY b.id, c.name, b.amount_limit, b.period
        """, (user_id,))
        
        budgets = []
        for row in cursor.fetchall():
            budget = dict(row)
            budget['percentage'] = (budget['current_spent'] / budget['amount_limit'] * 100) if budget['amount_limit'] > 0 else 0
            budget['remaining'] = budget['amount_limit'] - budget['current_spent']
            budget['is_exceeded'] = budget['current_spent'] > budget['amount_limit']
            budgets.append(budget)
        
        conn.close()
        return budgets
        
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении статуса бюджетов: {e}")
        conn.close()
        return []

def set_budget(user_id: int, category_id: int, amount_limit: float, period: str = 'monthly'):
    """Устанавливает бюджет для категории"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT OR REPLACE INTO budgets (user_id, category_id, amount_limit, period)
            VALUES (?, ?, ?, ?)
        """, (user_id, category_id, amount_limit, period))
        
        conn.commit()
        conn.close()
        return True
        
    except sqlite3.Error as e:
        logger.error(f"Ошибка при установке бюджета: {e}")
        conn.rollback()
        conn.close()
        return False

def delete_budget(user_id: int, category_id: int):
    """Удаляет бюджет для категории"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            DELETE FROM budgets 
            WHERE user_id = ? AND category_id = ?
        """, (user_id, category_id))
        
        conn.commit()
        conn.close()
        return cursor.rowcount > 0
        
    except sqlite3.Error as e:
        logger.error(f"Ошибка при удалении бюджета: {e}")
        conn.rollback()
        conn.close()
        return False