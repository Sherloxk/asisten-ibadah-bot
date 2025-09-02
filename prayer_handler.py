# File: prayer_handler.py (Versi Upgrade API MyQuran)

import requests
from datetime import datetime
import pytz
from utils import escape_markdown_v2

WIB = pytz.timezone('Asia/Jakarta')
BASE_URL = "https://api.myquran.com/v2"

def get_city_id(city: str):
    """Mencari ID kota di API MyQuran."""
    try:
        response = requests.get(f"{BASE_URL}/sholat/kota/cari/{city}")
        response.raise_for_status()
        data = response.json()
        if data['status'] and data['data']:
            # Ambil ID dari hasil pertama
            return data['data'][0]['id']
        return None
    except Exception as e:
        print(f"Error saat mencari ID kota: {e}")
        return None

def get_prayer_times_raw(city: str):
    """Mengambil data jadwal sholat mentah dari API MyQuran."""
    city_id = get_city_id(city)
    if not city_id:
        return None
    
    today = datetime.now()
    try:
        url = f"{BASE_URL}/sholat/jadwal/{city_id}/{today.year}/{today.month}/{today.day}"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        if data['status'] and data['data']:
            return data['data']
        return None
    except Exception as e:
        print(f"Error saat mengambil jadwal sholat: {e}")
        return None

def format_prayer_times(city: str, data: dict):
    """Memformat data jadwal sholat menjadi teks yang rapi dan aman."""
    jadwal = data['jadwal']
    safe_city = escape_markdown_v2(city)
    safe_date = escape_markdown_v2(jadwal.get('tanggal'))
    current_time = datetime.now(WIB).strftime("%H:%M:%S")
    
    # Sesuaikan nama kunci dengan respons API MyQuran
    return (
        f"🕋 *Jadwal Sholat untuk {safe_city}*\n"
        f"🗓️ Tanggal: {safe_date}\n"
        f"🕰️ Waktu Sekarang: `{current_time}` WIB\n\n"
        f"**Imsak:** `{jadwal.get('imsak', '-')}`\n"
        f"**Subuh:** `{jadwal.get('subuh', '-')}`\n"
        f"**Terbit:** `{jadwal.get('terbit', '-')}`\n"
        f"**Dhuha:** `{jadwal.get('dhuha', '-')}`\n"
        f"**Dzuhur:** `{jadwal.get('dzuhur', '-')}`\n"
        f"**Ashar:** `{jadwal.get('ashar', '-')}`\n"
        f"**Maghrib:** `{jadwal.get('maghrib', '-')}`\n"
        f"**Isya:** `{jadwal.get('isya', '-')}`"
    )

def get_prayer_times(city: str, country: str = "Indonesia"):
    """Fungsi utama untuk mendapatkan teks jadwal sholat yang sudah diformat."""
    data = get_prayer_times_raw(city)
    if data:
        return format_prayer_times(city, data)
    return escape_markdown_v2(f"Maaf, tidak dapat menemukan jadwal sholat untuk kota '{city}'.")