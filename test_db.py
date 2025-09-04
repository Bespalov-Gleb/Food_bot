#!/usr/bin/env python3
"""
Тестовый скрипт для проверки базы данных
"""

import sqlite3
import os

def test_database():
    """Проверяет структуру базы данных и данные"""
    
    # Путь к базе данных
    db_path = "data.db"
    
    if not os.path.exists(db_path):
        print(f"❌ База данных не найдена: {db_path}")
        return
    
    print(f"📁 База данных найдена: {db_path}")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Получаем список таблиц
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        print(f"\n📋 Таблицы в базе данных:")
        for table in tables:
            print(f"  - {table[0]}")
        
        # Проверяем таблицу restaurant_admins
        print(f"\n🔍 Проверяем таблицу restaurant_admins:")
        try:
            cursor.execute("SELECT * FROM restaurant_admins LIMIT 10;")
            rows = cursor.fetchall()
            
            if rows:
                print(f"  ✅ Найдено {len(rows)} записей:")
                for row in rows:
                    print(f"    - user_id: {row[0]}, restaurant_id: {row[1]}")
            else:
                print(f"  ⚠️  Записей не найдено")
                
        except sqlite3.OperationalError as e:
            print(f"  ❌ Ошибка при чтении таблицы restaurant_admins: {e}")
        
        # Проверяем таблицу restaurants
        print(f"\n🏪 Проверяем таблицу restaurants:")
        try:
            cursor.execute("SELECT id, name, is_enabled FROM restaurants LIMIT 10;")
            rows = cursor.fetchall()
            
            if rows:
                print(f"  ✅ Найдено {len(rows)} ресторанов:")
                for row in rows:
                    print(f"    - ID: {row[0]}, Название: {row[1]}, Включен: {row[2]}")
            else:
                print(f"  ⚠️  Ресторанов не найдено")
                
        except sqlite3.OperationalError as e:
            print(f"  ❌ Ошибка при чтении таблицы restaurants: {e}")
        
        # Проверяем таблицу orders
        print(f"\n📦 Проверяем таблицу orders:")
        try:
            cursor.execute("SELECT id, restaurant_id, status, created_at FROM orders LIMIT 10;")
            rows = cursor.fetchall()
            
            if rows:
                print(f"  ✅ Найдено {len(rows)} заказов:")
                for row in rows:
                    print(f"    - ID: {row[0]}, Ресторан: {row[1]}, Статус: {row[2]}, Дата: {row[3]}")
            else:
                print(f"  ⚠️  Заказов не найдено")
                
        except sqlite3.OperationalError as e:
            print(f"  ❌ Ошибка при чтении таблицы orders: {e}")
        
        # Проверяем таблицу users
        print(f"\n👤 Проверяем таблицу users:")
        try:
            cursor.execute("SELECT id, username, is_blocked FROM users LIMIT 10;")
            rows = cursor.fetchall()
            
            if rows:
                print(f"  ✅ Найдено {len(rows)} пользователей:")
                for row in rows:
                    print(f"    - ID: {row[0]}, Username: {row[1]}, Заблокирован: {row[2]}")
            else:
                print(f"  ⚠️  Пользователей не найдено")
                
        except sqlite3.OperationalError as e:
            print(f"  ❌ Ошибка при чтении таблицы users: {e}")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Ошибка при работе с базой данных: {e}")

if __name__ == "__main__":
    test_database() 