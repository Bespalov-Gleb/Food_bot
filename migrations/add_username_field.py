#!/usr/bin/env python3
import sqlite3
import os

def migrate():
    db_path = "app.db"
    if not os.path.exists(db_path):
        print("Database file not found, skipping migration")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Проверяем, существует ли уже поле username
        cursor.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if "username" not in columns:
            print("Adding username column to users table...")
            cursor.execute("ALTER TABLE users ADD COLUMN username TEXT")
            print("✅ Username column added successfully")
        else:
            print("✅ Username column already exists")
            
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("✅ Username column already exists")
        else:
            print(f"❌ Error adding username column: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
    finally:
        conn.commit()
        conn.close()

if __name__ == "__main__":
    migrate() 