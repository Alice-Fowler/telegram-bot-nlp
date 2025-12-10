from pathlib import Path

# Базовые пути
BASE_DIR = Path(__file__).parent

# Токен бота
API_TOKEN = "8387244610:AAGEiy7yheIgZvUYAhLSRFenUpeQLZ6ZMuI"

# Настройки базы данных
DB_PATH = BASE_DIR / "finance_bot.db"
MODEL_PATH = BASE_DIR / "category_model.pkl"
TRAIN_DATA_PATH = BASE_DIR / "data" / "train_data.csv"

# Предустановленные категории расходов
DEFAULT_CATEGORIES = [
    "Еда",
    "Транспорт",
    "Развлечения",
    "Кафе",
    "Продукты",
    "Здоровье",
    "Образование",
    "Другое"
]

CONFIDENCE_THRESHOLD = 0.8

# Лимиты для рекомендаций (метод 50/30/20)
BUDGET_RATIOS = {
    "essentials": 0.5,      # 50% - обязательные расходы
    "wants": 0.3,           # 30% - желания
    "savings": 0.2          # 20% - накопления
}

# Категории по умолчанию для группировки в рекомендациях
CATEGORY_GROUPS = {
    "essentials": ["Продукты", "Транспорт", "Здоровье", "Образование"],
    "wants": ["Еда", "Кафе", "Развлечения"],
    "savings": ["Другое"]  # Сюда можно отнести накопления
}