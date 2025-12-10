# nlp_classifier.py
import pandas as pd
import numpy as np
import re
import logging
import pickle
from typing import Tuple, Optional, List, Dict

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import f1_score, classification_report
from sklearn.preprocessing import LabelEncoder

import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from nltk.stem import SnowballStemmer

from config import TRAIN_DATA_PATH, MODEL_PATH, DEFAULT_CATEGORIES, CONFIDENCE_THRESHOLD

# Настройка логирования
logger = logging.getLogger(__name__)

# Загрузка ресурсов NLTK (только при первом запуске)
def download_nltk_resources():
    """Скачивает необходимые ресурсы NLTK"""
    try:
        nltk.data.find('tokenizers/punkt')
        nltk.data.find('corpora/stopwords')
    except LookupError:
        print("Скачивание ресурсов NLTK...")
        nltk.download('punkt')
        nltk.download('stopwords')
        print("Ресурсы NLTK загружены")

# Загружаем ресурсы при импорте
download_nltk_resources()

# Инициализация NLTK компонентов
STOPWORDS_RU = set(stopwords.words('russian'))
STEMmer = SnowballStemmer('russian')

class TextPreprocessor:
    """Класс для предобработки текста"""
    
    @staticmethod
    def clean_text(text: str) -> str:
        """Очистка текста: нижний регистр, удаление лишних символов"""
        if not isinstance(text, str):
            return ""
        
        # Приведение к нижнему регистру
        text = text.lower()
        
        # Удаление специальных символов, кроме букв и цифр
        text = re.sub(r'[^\w\s]', ' ', text)
        
        # Удаление лишних пробелов
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    @staticmethod
    def tokenize(text: str) -> List[str]:
        """Токенизация текста"""
        return word_tokenize(text, language='russian')
    
    @staticmethod
    def remove_stopwords(tokens: List[str]) -> List[str]:
        """Удаление стоп-слов"""
        return [token for token in tokens if token not in STOPWORDS_RU]
    
    @staticmethod
    def stem_tokens(tokens: List[str]) -> List[str]:
        """Стемминг токенов"""
        return [STEMmer.stem(token) for token in tokens]
    
    @staticmethod
    def preprocess(text: str) -> str:
        """Полный пайплайн предобработки текста"""
        # Очистка
        cleaned = TextPreprocessor.clean_text(text)
        
        # Токенизация
        tokens = TextPreprocessor.tokenize(cleaned)
        
        # Удаление стоп-слов
        tokens = TextPreprocessor.remove_stopwords(tokens)
        
        # Стемминг
        tokens = TextPreprocessor.stem_tokens(tokens)
        
        # Возвращаем строку
        return ' '.join(tokens)

class FinancialClassifier:
    """Классификатор финансовых транзакций"""
    
    def __init__(self):
        self.pipeline = None
        self.label_encoder = LabelEncoder()
        self.is_trained = False
        
    def load_data(self) -> Tuple[pd.DataFrame, pd.Series]:
        """Загрузка тренировочных данных"""
        try:
            df = pd.read_csv(TRAIN_DATA_PATH)
            logger.info(f"Загружено {len(df)} примеров из {TRAIN_DATA_PATH}")
            
            # Проверяем наличие необходимых колонок
            if 'description' not in df.columns or 'category' not in df.columns:
                raise ValueError("CSV файл должен содержать колонки 'description' и 'category'")
            
            # Удаляем пустые строки
            df = df.dropna(subset=['description', 'category'])
            
            # Преобразуем тексты
            df['description'] = df['description'].astype(str)
            df['category'] = df['category'].astype(str)
            
            return df['description'], df['category']
            
        except FileNotFoundError:
            logger.error(f"Файл {TRAIN_DATA_PATH} не найден")
            raise
        except Exception as e:
            logger.error(f"Ошибка при загрузке данных: {e}")
            raise
    
    def create_pipeline(self) -> Pipeline:
        """Создание пайплайна для классификации"""
        pipeline = Pipeline([
            ('tfidf', TfidfVectorizer(
                preprocessor=TextPreprocessor.preprocess,
                ngram_range=(1, 2),  # учитываем одиночные слова и биграммы
                max_features=1000,    # максимальное количество фич
                min_df=2,             # слово должно встречаться минимум в 2 документах
                max_df=0.8            # слово должно встречаться максимум в 80% документов
            )),
            ('classifier', LogisticRegression(
                max_iter=1000,
                random_state=42,
                multi_class='multinomial',
                solver='lbfgs',
                C=1.0
            ))
        ])
        return pipeline
    
    def train(self, test_size: float = 0.2) -> Dict[str, float]:
        """Обучение модели"""
        try:
            # Загрузка данных
            X, y = self.load_data()
            
            # Кодируем метки категорий
            y_encoded = self.label_encoder.fit_transform(y)
            
            # Разделение на train/test
            X_train, X_test, y_train, y_test = train_test_split(
                X, y_encoded, test_size=test_size, random_state=42, stratify=y_encoded
            )
            
            # Создание и обучение пайплайна
            self.pipeline = self.create_pipeline()
            self.pipeline.fit(X_train, y_train)
            
            # Оценка модели
            train_accuracy = self.pipeline.score(X_train, y_train)
            test_accuracy = self.pipeline.score(X_test, y_test)
            
            # Прогноз на тестовых данных
            y_pred = self.pipeline.predict(X_test)
            
            # Вычисление метрик
            f1 = f1_score(y_test, y_pred, average='weighted')
            
            # Декодируем метки для отчета
            y_test_decoded = self.label_encoder.inverse_transform(y_test)
            y_pred_decoded = self.label_encoder.inverse_transform(y_pred)
            
            # Генерируем отчет
            report = classification_report(y_test_decoded, y_pred_decoded)
            
            logger.info(f"Обучение завершено:")
            logger.info(f"  Train accuracy: {train_accuracy:.4f}")
            logger.info(f"  Test accuracy: {test_accuracy:.4f}")
            logger.info(f"  F1-score: {f1:.4f}")
            logger.info(f"\nClassification Report:\n{report}")
            
            self.is_trained = True
            
            return {
                'train_accuracy': train_accuracy,
                'test_accuracy': test_accuracy,
                'f1_score': f1,
                'classification_report': report
            }
            
        except Exception as e:
            logger.error(f"Ошибка при обучении модели: {e}")
            raise
    
    def predict(self, text: str, return_probability: bool = False) -> Tuple[Optional[str], Optional[float]]:
        """
        Предсказание категории для текста.
        
        Args:
            text: Текст описания транзакции
            return_probability: Возвращать ли вероятность
            
        Returns:
            Если return_probability=False: (категория, уверенность)
            Если return_probability=True: (категория, уверенность, все_вероятности)
        """
        if not self.is_trained or self.pipeline is None:
            raise ValueError("Модель не обучена. Сначала вызовите train()")
        
        if not text or not isinstance(text, str):
            return (None, 0.0) if not return_probability else (None, 0.0, {})
        
        try:
            # Предсказание вероятностей
            proba = self.pipeline.predict_proba([text])[0]
            
            # Индекс максимальной вероятности
            max_idx = np.argmax(proba)
            confidence = proba[max_idx]
            
            # Декодируем категорию
            category = self.label_encoder.inverse_transform([max_idx])[0]
            
            if not return_probability:
                return category, confidence
            else:
                # Получаем все категории с вероятностями
                all_categories = self.label_encoder.classes_
                probabilities = {cat: prob for cat, prob in zip(all_categories, proba)}
                return category, confidence, probabilities
                
        except Exception as e:
            logger.error(f"Ошибка при предсказании для текста '{text}': {e}")
            return (None, 0.0) if not return_probability else (None, 0.0, {})
    
    def predict_with_threshold(self, text: str, threshold: float = CONFIDENCE_THRESHOLD) -> Tuple[Optional[str], float, bool]:
        """
        Предсказание с порогом уверенности.
        
        Returns:
            (категория, уверенность, уверенное_предсказание)
            Если уверенность < threshold, возвращает (None, уверенность, False)
        """
        category, confidence = self.predict(text)
        
        if confidence >= threshold:
            return category, confidence, True
        else:
            return None, confidence, False
    
    def save_model(self, filepath: str = MODEL_PATH):
        """Сохранение модели в файл"""
        try:
            with open(filepath, 'wb') as f:
                pickle.dump({
                    'pipeline': self.pipeline,
                    'label_encoder': self.label_encoder,
                    'is_trained': self.is_trained
                }, f)
            logger.info(f"Модель сохранена в {filepath}")
        except Exception as e:
            logger.error(f"Ошибка при сохранении модели: {e}")
            raise
    
    def load_model(self, filepath: str = MODEL_PATH):
        """Загрузка модели из файла"""
        try:
            with open(filepath, 'rb') as f:
                data = pickle.load(f)
            
            self.pipeline = data['pipeline']
            self.label_encoder = data['label_encoder']
            self.is_trained = data['is_trained']
            
            logger.info(f"Модель загружена из {filepath}")
            logger.info(f"Категории: {list(self.label_encoder.classes_)}")
            
        except FileNotFoundError:
            logger.warning(f"Файл модели {filepath} не найден. Нужно обучить модель.")
            self.is_trained = False
        except Exception as e:
            logger.error(f"Ошибка при загрузке модели: {e}")
            self.is_trained = False

# Глобальный экземпляр классификатора
classifier = FinancialClassifier()

def initialize_classifier() -> FinancialClassifier:
    """Инициализация классификатора (обучение или загрузка)"""
    global classifier
    
    # Пытаемся загрузить сохраненную модель
    classifier.load_model()
    
    if not classifier.is_trained:
        print("Модель не найдена. Начинаю обучение...")
        metrics = classifier.train()
        classifier.save_model()
        
        print(f"\n✅ Модель обучена!")
        print(f"   Точность на тесте: {metrics['test_accuracy']:.2%}")
        print(f"   F1-score: {metrics['f1_score']:.2%}")
        if metrics['test_accuracy'] > 0.85:
            print("   🎯 Цель >85% достигнута!")
        else:
            print("   ⚠️  Точность ниже 85%. Рассмотрите добавление больше данных.")
    else:
        print("✅ Модель загружена из файла")
    
    return classifier

def test_classifier_examples():
    """Тестирование классификатора на примерах"""
    clf = initialize_classifier()
    
    test_cases = [
        "кофе в старбакс",
        "такси до работы",
        "продукты в магазине",
        "кино с друзьями",
        "обед в столовой",
        "лекарства в аптеке",
        "курсы английского",
        "подарок на день рождения",
        "бензин на заправке",
        "стоматолог зубной",
    ]
    
    print("\n🧪 Тестирование классификатора:")
    print("-" * 50)
    
    for text in test_cases:
        category, confidence, is_confident = clf.predict_with_threshold(text)
        
        if is_confident:
            print(f"✅ '{text}' → {category} ({confidence:.2%})")
        else:
            print(f"❓ '{text}' → НЕУВЕРЕННО ({confidence:.2%})")
    
    print("-" * 50)