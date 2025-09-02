# File: scripture_handler.py (Versi Upgrade API MyQuran)

import os
import requests
import random

BASE_URL = "https://api.myquran.com/v2"

def search_quran(keyword: str):
    """Mencari ayat Qur'an, mengambil terjemahan DAN teks Arab."""
    try:
        response = requests.get(f"{BASE_URL}/quran/ayat/keyword/{keyword}/terjemah/semua")
        response.raise_for_status()
        data = response.json()
        if data['status'] and data['data']:
            ayat = random.choice(data['data'])
            teks_indonesia = ayat['terjemah']['teks']
            teks_arab = ayat['teks']['arab'] # <-- Mengambil teks Arab
            surat = ayat['surat']['nama']['id']
            nomor_ayat = ayat['nomor']
            return {
                "text": teks_indonesia,
                "arabic": teks_arab, # <-- Menambahkan teks Arab ke output
                "reference": f"QS. {surat}: {nomor_ayat}"
            }
        return None
    except Exception as e:
        print(f"Error saat mencari Qur'an (MyQuran): {e}")
        return None

def search_hadith(keyword: str):
    """Mencari hadis dalam Bahasa Indonesia dari beberapa perawi."""
    # Daftar perawi prioritas untuk dicari
    narrators = ["bukhari", "muslim", "abu-daud", "tirmidzi", "nasai", "ibnu-majah"]
    random.shuffle(narrators) # Acak urutan agar tidak monoton

    for narrator in narrators:
        try:
            # Cari 5 hadis dan pilih salah satu secara acak
            url = f"{BASE_URL}/hadits/{narrator}/cari?q={keyword}&limit=5"
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            if data['status'] and data['data']['hadits']:
                hadith = random.choice(data['data']['hadits'])
                teks = hadith['terjemah']
                nomor = hadith['nomor']
                return {"text": teks, "reference": f"HR. {narrator.capitalize()} No. {nomor}"}
        except Exception as e:
            print(f"Error saat mencari Hadis {narrator}: {e}")
            continue # Jika gagal, coba perawi selanjutnya
            
    return None # Jika tidak ditemukan sama sekali