# File: db_handler.py
import sqlite3
from datetime import datetime

DB_NAME = "ibadah_bot.db"
CHECKLIST_ITEMS = ["Subuh", "Dzuhur", "Ashar", "Maghrib", "Isya", "Tahajud", "Dhuha", "Rawatib", "Tilawah", "Dzikir", "Sedekah", "Puasa Senin", "Puasa Kamis", "Puasa Ayyamul Bidh", "Puasa Arafah", "Puasa Tasu'a/Asyura"]
WAJIB_ITEMS = ["Subuh", "Dzuhur", "Ashar", "Maghrib", "Isya"]
SUNNAH_ITEMS = ["Tahajud", "Dhuha", "Rawatib"]
LAINNYA_ITEMS = ["Tilawah", "Dzikir", "Sedekah"]

def set_user_notification(user_id: int, notif_type: str, status: int):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    # Tambahkan tipe notifikasi baru ke daftar aman
    if notif_type in ['notif_sholat', 'notif_rangkuman', 'notif_dzikir', 'notif_dhuha', 'notif_jumat', 'notif_motivasi']:
        query = f"UPDATE users SET {notif_type} = ? WHERE user_id = ?"
        cursor.execute(query, (status, user_id))
        conn.commit()
    conn.close()
    
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, full_name TEXT, username TEXT, status TEXT DEFAULT 'Pending',
        agreed_terms INTEGER DEFAULT 0, location TEXT, registration_date TEXT,
        notif_sholat INTEGER DEFAULT 1,
        notif_rangkuman INTEGER DEFAULT 1,
        notif_dzikir INTEGER DEFAULT 1,
        notif_dhuha INTEGER DEFAULT 1,
        notif_jumat INTEGER DEFAULT 1,
        notif_motivasi INTEGER DEFAULT 1
    )""")
    
    checklist_columns = ", ".join([f'"{item}" TEXT DEFAULT "Belum"' for item in CHECKLIST_ITEMS])
    cursor.execute(f"CREATE TABLE IF NOT EXISTS daily_logs (log_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, date TEXT, {checklist_columns}, UNIQUE(user_id, date))")
    cursor.execute("""CREATE TABLE IF NOT EXISTS feedback (feedback_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, timestamp TEXT, feedback_text TEXT)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS discussions (message_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, role TEXT, content TEXT, timestamp TEXT)""")
    conn.commit()
    conn.close()
    print("Database SQLite berhasil diinisialisasi dengan notifikasi default.")

def dict_factory(cursor, row):
    fields = [column[0] for column in cursor.description]
    return {key: value for key, value in zip(fields, row)}

def find_user_by_id(user_id: int):
    conn = sqlite3.connect(DB_NAME); conn.row_factory = dict_factory; cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)); user = cursor.fetchone(); conn.close(); return user

def add_new_user_for_verification(user_id: int, username: str, full_name: str):
    user = find_user_by_id(user_id); conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    if user:
        cursor.execute("UPDATE users SET status = 'Pending', agreed_terms = 0, full_name = ?, username = ? WHERE user_id = ?", (full_name, username, user_id))
        result = "already_exists"
    else:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO users (user_id, full_name, username, registration_date) VALUES (?, ?, ?, ?)", (user_id, full_name, username, timestamp))
        result = "success"
    conn.commit(); conn.close(); return result

def update_user_status(user_id: int, new_status: str):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    cursor.execute("UPDATE users SET status = ? WHERE user_id = ?", (new_status, user_id)); conn.commit(); conn.close(); return True

def update_user_terms_agreement(user_id: int):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    cursor.execute("UPDATE users SET agreed_terms = 1 WHERE user_id = ?", (user_id,)); conn.commit(); conn.close(); return True

def update_user_location(user_id: int, new_location: str):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    cursor.execute("UPDATE users SET location = ? WHERE user_id = ?", (new_location, user_id)); conn.commit(); conn.close(); return True

def get_or_create_daily_log(user_id: int, today_date: str):
    conn = sqlite3.connect(DB_NAME); conn.row_factory = dict_factory; cursor = conn.cursor()
    cursor.execute("SELECT * FROM daily_logs WHERE user_id = ? AND date = ?", (user_id, today_date)); log = cursor.fetchone()
    if not log:
        cursor.execute("INSERT INTO daily_logs (user_id, date) VALUES (?, ?)", (user_id, today_date)); conn.commit()
        cursor.execute("SELECT * FROM daily_logs WHERE user_id = ? AND date = ?", (user_id, today_date)); log = cursor.fetchone()
    conn.close(); return log

def update_daily_log_item(user_id: int, today_date: str, item_name: str, new_status: str):
    if item_name not in CHECKLIST_ITEMS: return False
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    cursor.execute(f'UPDATE daily_logs SET "{item_name}" = ? WHERE user_id = ? AND date = ?', (new_status, user_id, today_date))
    conn.commit(); conn.close(); return True

def get_user_logs_for_period(user_id: int, start_date: str, end_date: str):
    conn = sqlite3.connect(DB_NAME); conn.row_factory = dict_factory; cursor = conn.cursor()
    cursor.execute("SELECT * FROM daily_logs WHERE user_id = ? AND date BETWEEN ? AND ?", (user_id, start_date, end_date))
    logs = cursor.fetchall(); conn.close(); return logs

def add_feedback(user_id: int, username: str, text: str):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO feedback (user_id, timestamp, feedback_text) VALUES (?, ?, ?)", (user_id, timestamp, text))
    conn.commit(); conn.close(); return True

def get_discussion_history(user_id: int):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    cursor.execute("SELECT role, content FROM discussions WHERE user_id = ? ORDER BY timestamp ASC", (user_id,))
    history = [{'role': row[0], 'content': row[1]} for row in cursor.fetchall()]; conn.close(); return history

def add_discussion_message(user_id: int, role: str, content: str):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO discussions (user_id, role, content, timestamp) VALUES (?, ?, ?, ?)", (user_id, role, content, timestamp))
    conn.commit(); conn.close()

def clear_discussion_history(user_id: int):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    cursor.execute("DELETE FROM discussions WHERE user_id = ?", (user_id,)); conn.commit(); conn.close()