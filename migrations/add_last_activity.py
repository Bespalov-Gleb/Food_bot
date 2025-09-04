#!/usr/bin/env python3
"""
Миграция для добавления поля last_activity в таблицу users
"""
import os
import sys
from datetime import datetime

# Добавляем корневую директорию в путь
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from app.db import DATABASE_URL

def run_migration():
    """Выполняет миграцию для добавления поля last_activity"""
    engine = create_engine(DATABASE_URL)
    
    with engine.connect() as conn:
        try:
            # Пробуем добавить поле last_activity
            print("🔄 Добавляем поле last_activity в таблицу users...")
            conn.execute(text("""
                ALTER TABLE users 
                ADD COLUMN last_activity TIMESTAMP
            """))
            
            # Обновляем существующие записи
            print("🔄 Обновляем существующие записи...")
            conn.execute(text("""
                UPDATE users 
                SET last_activity = created_at 
                WHERE last_activity IS NULL
            """))
            
            conn.commit()
            print("✅ Миграция успешно выполнена!")
            
        except Exception as e:
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                print("✅ Поле last_activity уже существует в таблице users")
            else:
                print(f"❌ Ошибка при выполнении миграции: {e}")
                raise

if __name__ == "__main__":
    run_migration() 