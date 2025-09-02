# File: ai_handler.py

import os
import random
from dotenv import load_dotenv
import anthropic
import db_handler as db
import scripture_handler
from utils import escape_markdown_v2
from datetime import datetime, timedelta

# Muat environment variables
load_dotenv()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Inisialisasi client Anthropic
try:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    print("Berhasil terhubung ke Anthropic API.")
except Exception as e:
    print(f"Error saat inisialisasi client Anthropic: {e}")
    client = None

def analyze_logs(logs: list) -> str:
    """Menganalisis log dengan lebih cerdas."""
    if not logs:
        return "Pengguna ini belum memiliki catatan ibadah."

    item_counts = {item: 0 for item in db.CHECKLIST_ITEMS}
    for day_log in logs:
        for item in db.CHECKLIST_ITEMS:
            if day_log.get(item) == "Sudah":
                item_counts[item] += 1
    
    total_wajib_tercatat = sum(item_counts.get(s, 0) for s in db.WAJIB_ITEMS)
    
    amalan_terbaik = None
    for item in db.WAJIB_ITEMS + db.SUNNAH_ITEMS + db.LAINNYA_ITEMS:
        if item_counts.get(item, 0) > 0:
            amalan_terbaik = item
            break
            
    amalan_terlewat = None
    for item in db.WAJIB_ITEMS:
        if item_counts.get(item, 0) == 0:
            amalan_terlewat = item
            break
            
    summary = f"Pengguna menyelesaikan {total_wajib_tercatat} dari 5 sholat wajib. "
    if amalan_terbaik:
        summary += f"Dia sudah berhasil mengerjakan amalan '{amalan_terbaik}'. "
    if amalan_terlewat:
        summary += f"Namun, dia terlewat dalam amalan '{amalan_terlewat}'."
        
    return summary

def get_theme_from_ai(log_summary: str):
    """Langkah 1: Meminta AI untuk menentukan tema dari ringkasan log."""
    if not client: return None
    prompt = f"""
    Berdasarkan ringkasan aktivitas ibadah pengguna berikut: "{log_summary}", 
    berikan satu kata kunci atau tema yang paling relevan untuk diberikan motivasi dalam bahasa Indonesia.
    Contoh: 'syukur', 'sabar', 'keutamaan sholat', 'sedekah', 'istiqomah'.
    Jawab HANYA dengan 1-2 kata saja.
    """
    try:
        message = client.messages.create(
            model="claude-3-haiku-20240307", max_tokens=10,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text.strip()
    except Exception as e:
        print(f"Error saat get_theme_from_ai: {e}")
        return None

def generate_motivational_message(logs: list):
    """Menghasilkan motivasi singkat dengan kutipan ayat."""
    if not client:
        return f"\n\n> {escape_markdown_v2('Maaf, layanan motivasi AI sedang tidak tersedia.')}"

    log_summary = analyze_logs(logs)
    theme = get_theme_from_ai(log_summary)
    dalil_data = None
    if theme:
        dalil_data = scripture_handler.search_quran(theme)
        
    prompt_akhir = f"""
    Anda adalah seorang motivator Islami yang memberikan nasihat singkat dan berbobot.
    Ringkasan Ibadah Pengguna: {log_summary}
    """
    if dalil_data:
        prompt_akhir += f"\nDalil Pendukung:\n{dalil_data['text']} {dalil_data['reference']}\n"
    
    prompt_akhir += """
    Instruksi Final:
    1. Berikan SATU kalimat motivasi singkat yang relevan dengan ringkasan ibadah.
    2. Setelah itu, KUTIP POTONGAN PALING RELEVAN dari terjemahan ayat di 'Dalil Pendukung'.
    3. JANGAN ADA SAPAAN.
    4. Format WAJIB: [Kalimat Motivasi Anda].\n\n📜 _"[Potongan kutipan ayat di sini]"_ [Referensi Ayat].
    """
    
    try:
        message = client.messages.create(
            model="claude-3-haiku-20240307", max_tokens=100,
            messages=[{"role": "user", "content": prompt_akhir}]
        )
        ai_response = message.content[0].text.strip()
        safe_response = escape_markdown_v2(ai_response)
        return f"\n\n> {safe_response}"
    except Exception as e:
        print(f"Error saat generate_motivational_message: {e}")
        return f"\n\n> {escape_markdown_v2('Gagal mendapatkan motivasi personal saat ini.')}"

def generate_discussion_response(user_id: int, user_question: str, history: list):
    """Menghasilkan jawaban dari Konsultan Islami AI yang personal dan berbasis dalil."""
    if not client: return escape_markdown_v2("Maaf, layanan diskusi AI sedang tidak tersedia.")

    # --- LANGKAH BARU: Mengambil data ibadah pengguna ---
    today = datetime.now()
    start_date = (today - timedelta(days=6)).strftime("%Y-%m-%d")
    end_date = today.strftime("%Y-%m-%d")
    logs = db.get_user_logs_for_period(user_id, start_date, end_date)
    ibadah_summary = analyze_logs(logs) # Menganalisis rutinitas ibadah pengguna

    # --- Mencari referensi dalil (tidak berubah) ---
    keywords = user_question.split()
    quran_ref = scripture_handler.search_quran(user_question)
    hadith_ref = scripture_handler.search_hadith(random.choice(keywords)) if len(keywords) > 1 else None

    # --- PROMPT MASTER BARU ---
    prompt = f"""
    Anda adalah seorang Konsultan Islami AI yang bijaksana, empatik, dan berpegang teguh pada dalil. Anda memberikan jawaban yang personal dan relevan berdasarkan history percakapan dan ringkasan rutinitas ibadah pengguna.
    
    KONTEKS PENGGUNA:
    1.  Pertanyaan Pengguna Saat Ini: "{user_question}"
    2.  Sapa pengguna dengan hormat di awal jawaban Anda dengan singkat, misalnya "Saudaraku yang dirahmati Allah,". Respon berdasarkan konteks request, apabila dia memberikan pujian, balas dengan ucapan terima kasih. Apabila dia mengeluh, berikan empati. Apabila dia bertanya, jawab dengan jelas dan ringkas.
    REFERENSI DALIL YANG DITEMUKAN:
    """
    
    if quran_ref:
        prompt += f"\n- Al-Qur'an: {quran_ref['arabic']} | {quran_ref['text']} {quran_ref['reference']}\n"
    if hadith_ref:
        prompt += f"\n- Hadis: {hadith_ref['text']} {hadith_ref['reference']}\n"
        
    prompt += """
    INSTRUKSI FINAL WAJIB DIPATUHI:
    1.  Apabila ada pertanyaan dari pengguna jawab HANYA BERDASARKAN referensi dalil yang diberikan. JANGAN berhalusinasi atau menggunakan pengetahuan eksternal.
    2.  **Personalisasi Jawaban:** Kaitkan jawaban Anda dengan 'Ringkasan Rutinitas Ibadah Pengguna'. Jika pengguna bertanya tentang amalan yang ia sering lewatkan, berikan jawaban yang lebih menyemangati.
    3.  **Struktur Jawaban:**
        a. Apabila ada pertanyaan mohon berikan jawaban yang to the point dan memparafrasekan dalil dengan bahasa yang mudah dimengerti.
        b. Sertakan Teks Arab dari ayat Al-Qur'an jika tersedia.
        c. Sertakan kutipan lengkap terjemahan dalil yang paling relevan (Qur'an atau Hadis).
        d. Sertakan sumbernya dengan jelas.
    4.  **Aturan Tambahan:**
        - Jika referensi tidak cukup, WAJIB jawab: "Mohon maaf, saya tidak menemukan dalil yang relevan untuk menjawab pertanyaan Anda secara spesifik. Sebaiknya Anda bertanya kepada ustadz atau ahli fiqih terpercaya."
    5.  **Disclaimer WAJIB:** Akhiri jawaban dengan disclaimer: "_Jawaban ini adalah hasil parafrase dari AI berdasarkan dalil yang ditemukan dan perlu divalidasi oleh ahli. Wallahu a'lam._"
    """

    messages_to_send = history + [{'role': 'user', 'content': prompt}]

    try:
        message = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=600, # Tambah sedikit ruang untuk jawaban yang lebih kaya
            messages=messages_to_send
        )
        ai_response = message.content[0].text.strip()
        return ai_response
    except Exception as e:
        print(f"Error saat generate_discussion_response: {e}")
        return escape_markdown_v2("Maaf, terjadi kesalahan saat menyusun jawaban.")
