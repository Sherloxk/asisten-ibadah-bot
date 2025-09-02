# File: main.py

import os
import logging
from dotenv import load_dotenv
from datetime import datetime, timedelta, time
import pytz

from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

# Impor semua handler kustom kita
import db_handler as db
import prayer_handler
import report_handler
import ai_handler
import calendar_handler

# --- SETUP DASAR ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_USER_ID = os.getenv("ADMIN_USER_ID")
WIB = pytz.timezone('Asia/Jakarta')

# --- DEFINISI STATE ---
(STATE_REGISTER_NAME, STATE_ASK_LOCATION, STATE_AWAIT_FEEDBACK, STATE_AWAIT_DISCUSSION) = range(4)

# --- FUNGSI & TEKS GLOBAL ---
TERMS_AND_CONDITIONS = """
Sebelum melanjutkan, kami memohon Anda untuk membaca dan menyetujui beberapa adab dan ketentuan penggunaan bot ini.

**Syarat & Ketentuan Bot Asisten Ibadah:**

1.  **Niat yang Lurus:** Gunakanlah bot ini semata-mata untuk mendekatkan diri kepada Allah SWT.
2.  **Menjaga Kerahasiaan:** Data ibadah Anda adalah privasi. Bot ini tidak membagikan data personal Anda.
3.  **Bukan Pengganti Ulama:** Bot ini adalah alat bantu. Untuk Fiqih, tetaplah merujuk kepada Ulama.
4.  **Saling Mendoakan:** Mari niatkan setiap interaksi di sini untuk saling mendukung dalam ketaatan.

Apakah Anda membaca, memahami, dan bersedia mengikuti ketentuan di atas?
"""
CHECKLIST_ITEMS = db.CHECKLIST_ITEMS
WAJIB_ITEMS = db.WAJIB_ITEMS
SUNNAH_ITEMS = db.SUNNAH_ITEMS
LAINNYA_ITEMS = db.LAINNYA_ITEMS

def escape_markdown_v2(text: str) -> str:
    if not isinstance(text, str): return ""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return ''.join(f'\\{char}' if char in escape_chars else char for char in text)

# --- FUNGSI BARU & MODIFIKASI UNTUK NOTIFIKASI ---

def schedule_default_jobs(user_id: int, job_queue):
    """Menjadwalkan notifikasi default untuk pengguna baru."""
    job_queue.run_daily(schedule_prayer_notifications_for_user, time(hour=2, tzinfo=WIB), user_id=user_id, name=f"notif_sholat_{user_id}")
    job_queue.run_daily(send_daily_summary, time(hour=21, minute=30, tzinfo=WIB), user_id=user_id, name=f"notif_rangkuman_{user_id}")
    job_queue.run_daily(send_daily_motivation, time(hour=7, tzinfo=WIB), user_id=user_id, name=f"notif_motivasi_{user_id}")
    logger.info(f"Notifikasi default dijadwalkan untuk pengguna baru: {user_id}")

# --- FUNGSI MENU UTAMA & PEMBATALAN ---
async def show_main_menu(message, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["Waktu Sholat 🕋", "Checklist Ibadah Harian ✅"],
        ["Laporan Ibadah 📊", "Kritik dan Saran ✍️"],
        ["Diskusi Islami 💬"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    await message.reply_text("Menu Utama:", reply_markup=reply_markup)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Aksi dibatalkan.")
    await show_main_menu(update.message, context)
    return ConversationHandler.END

# --- ALUR PENDAFTARAN & VERIFIKASI ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user; user_id = user.id
    user_data = db.find_user_by_id(user_id)
    if user_data:
        status, agreed_terms = user_data.get("status"), user_data.get("agreed_terms") == 1
        if status == "Approved" and agreed_terms:
            await show_main_menu(update.message, context)
            return ConversationHandler.END
        elif status == "Approved" and not agreed_terms:
            keyboard = [[InlineKeyboardButton("Ya, Saya Bersedia", callback_data=f"agree_terms_{user_id}")]]
            combined_text = "Alhamdulillah, akun Anda telah disetujui\n" + TERMS_AND_CONDITIONS
            await update.message.reply_text(combined_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return ConversationHandler.END
        elif status == "Pending":
            await update.message.reply_text("Akun Anda masih menunggu persetujuan admin.", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        elif status == "Rejected":
            await update.message.reply_text("Maaf, pendaftaran Anda sebelumnya telah ditolak.", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
    await update.message.reply_text("Assalamu'alaikum, selamat datang! Silakan ketikkan nama lengkap Anda.", reply_markup=ReplyKeyboardRemove())
    return STATE_REGISTER_NAME

async def received_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user; user_id, username, full_name = user.id, user.username or "", update.message.text
    if db.add_new_user_for_verification(user_id, username, full_name) in ["success", "already_exists"]:
        await update.message.reply_text(f"Terima kasih, {full_name}.\nPendaftaran Anda sedang menunggu persetujuan admin.")
        keyboard = [[InlineKeyboardButton("✅ Setujui", callback_data=f"approve_{user_id}"), InlineKeyboardButton("❌ Tolak", callback_data=f"reject_{user_id}")]]
        admin_message = f"🔔 Pendaftaran Baru\n\nNama: {full_name}\nUsername: @{username}\nUser ID: `{user_id}`"
        await context.bot.send_message(chat_id=ADMIN_USER_ID, text=admin_message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='MarkdownV2')
    else:
        await update.message.reply_text("Maaf, terjadi kesalahan.")
    return ConversationHandler.END

async def admin_verification_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer(); action, user_id_str = query.data.split('_', 1); user_id = int(user_id_str)
    if action == "approve":
        if db.update_user_status(user_id, "Approved"):
            await query.edit_message_text(text=f"{query.message.text}\n\n*✅ DISETUJUI oleh admin\\.*", parse_mode='MarkdownV2')
            keyboard = [[InlineKeyboardButton("Ya, Saya Bersedia", callback_data=f"agree_terms_{user_id}")]]
            combined_text = "Alhamdulillah, akun Anda telah disetujui!\n" + TERMS_AND_CONDITIONS
            try:
                await context.bot.send_message(chat_id=user_id, text=combined_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            except Exception as e:
                logger.error(f"Gagal mengirim pesan S&K ke user {user_id}: {e}")
    elif action == "reject":
        if db.update_user_status(user_id, "Rejected"):
            await query.edit_message_text(text=f"{query.message.text}\n\n*❌ DITOLAK oleh admin\\.*", parse_mode='MarkdownV2')
            try:
                await context.bot.send_message(chat_id=user_id, text="Maaf, pendaftaran Anda belum dapat kami setujui.")
            except Exception as e:
                logger.error(f"Gagal kirim penolakan ke {user_id}: {e}")

async def user_terms_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, _, user_id_str = query.data.split('_')
    user_id = int(user_id_str)
    if query.from_user.id != user_id: await query.answer("Ini bukan tombol untuk Anda.", show_alert=True); return
    
    await query.answer()
    if db.update_user_terms_agreement(user_id):
        await query.edit_message_text(text="Jazakallah khairan. Selamat menggunakan bot!")
        
        # JADWALKAN NOTIFIKASI DEFAULT DI SINI
        schedule_default_jobs(user_id, context.job_queue)
        
        await show_main_menu(query.message, context)
    else: await query.edit_message_text(text="Terjadi kesalahan.")

# --- HANDLER FITUR UTAMA ---
async def menu_sholat_handler_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id; user_data = db.find_user_by_id(user_id)
    current_location = user_data.get("location")
    if current_location and current_location != "-":
        safe_location = escape_markdown_v2(current_location)
        await update.message.reply_text(f"Lokasi Anda: **{safe_location}**\\.", parse_mode='MarkdownV2')
        await update.message.reply_text("Mengambil jadwal & motivasi personal...")
        schedule_message = prayer_handler.get_prayer_times(city=current_location)
        today = datetime.now()
        start_date, end_date = (today - timedelta(days=6)).strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")
        logs = db.get_user_logs_for_period(user_id, start_date, end_date)
        motivational_message = ai_handler.generate_motivational_message(logs)
        final_message = schedule_message + motivational_message
        await update.message.reply_text(final_message, parse_mode='MarkdownV2')
        keyboard = [[InlineKeyboardButton("🔄 Ganti Lokasi", callback_data="change_location")]]
        await update.message.reply_text("Ganti lokasi?", reply_markup=InlineKeyboardMarkup(keyboard)); return ConversationHandler.END
    else:
        await update.message.reply_text("Anda belum mengatur lokasi. Silakan ketik nama kota Anda."); return STATE_ASK_LOCATION

async def ask_location_again(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer(); await query.message.reply_text("Baik, silakan ketik nama kota baru Anda."); return STATE_ASK_LOCATION

async def received_location_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id, city_name = update.effective_user.id, update.message.text
    safe_city_name = escape_markdown_v2(city_name)
    await update.message.reply_text(f"Mencari jadwal untuk **{safe_city_name}**\\.\\.\\.", parse_mode='MarkdownV2')
    schedule_message = prayer_handler.get_prayer_times(city=city_name)
    if "Maaf, tidak dapat menemukan" not in schedule_message:
        db.update_user_location(user_id, city_name); await update.message.reply_text("Lokasi Anda berhasil disimpan.")
    await update.message.reply_text(schedule_message, parse_mode='MarkdownV2')
    await show_main_menu(update.message, context); return ConversationHandler.END

async def menu_checklist_handler_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("Ibadah Wajib", callback_data="checklist_cat_wajib")], [InlineKeyboardButton("Ibadah Sunnah", callback_data="checklist_cat_sunnah")],
                [InlineKeyboardButton("Ibadah Lainnya", callback_data="checklist_cat_lainnya")], [InlineKeyboardButton("Kembali ke Menu Utama", callback_data="back_to_main_menu")]]
    await update.message.reply_text("Silakan pilih kategori checklist:", reply_markup=InlineKeyboardMarkup(keyboard))

async def show_checklist_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer(); category = query.data.split('_')[-1]
    user_id, today_date = query.from_user.id, datetime.now().strftime("%Y-%m-%d")
    daily_log = db.get_or_create_daily_log(user_id, today_date)
    if not daily_log: await query.message.reply_text("Gagal ambil data."); return
    if category == "wajib": items, title = WAJIB_ITEMS, "Ibadah Wajib"
    elif category == "sunnah": items, title = SUNNAH_ITEMS, "Ibadah Sunnah"
    elif category == "lainnya": items, title = LAINNYA_ITEMS + calendar_handler.get_todays_sunnah_fasts(), "Ibadah Lainnya"
    else: return
    try: await query.edit_message_text(f"📝 Checklist {title} - {today_date}", reply_markup=build_checklist_keyboard(daily_log, items, "back_to_checklist_cat"))
    except Exception as e: logger.info(f"Pesan tidak diubah: {e}")

async def back_to_checklist_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    keyboard = [[InlineKeyboardButton("Ibadah Wajib", callback_data="checklist_cat_wajib")], [InlineKeyboardButton("Ibadah Sunnah", callback_data="checklist_cat_sunnah")],
                [InlineKeyboardButton("Ibadah Lainnya", callback_data="checklist_cat_lainnya")], [InlineKeyboardButton("Kembali ke Menu Utama", callback_data="back_to_main_menu")]]
    await query.edit_message_text("Pilih kategori checklist:", reply_markup=InlineKeyboardMarkup(keyboard))

def build_checklist_keyboard(daily_log: dict, items_to_show: list, back_callback: str):
    keyboard, row = [], []
    for item in items_to_show:
        status, icon = daily_log.get(item, "Belum"), "✅" if daily_log.get(item) == "Sudah" else "❌"
        row.append(InlineKeyboardButton(f"{icon} {item}", callback_data=f"checklist_{item}_{status}"))
        if len(row) == 2: keyboard.append(row); row = []
    if row: keyboard.append(row)
    keyboard.append([InlineKeyboardButton("⬅️ Kembali", callback_data=back_callback)])
    return InlineKeyboardMarkup(keyboard)

async def checklist_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; _, item_name, current_status = query.data.split('_', 2)
    user_id, today_date = query.from_user.id, datetime.now().strftime("%Y-%m-%d")
    new_status = "Sudah" if current_status == "Belum" else "Belum"
    if db.update_daily_log_item(user_id, today_date, item_name, new_status):
        await query.answer(f"{item_name} dicatat '{new_status}'.")
        updated_log = db.get_or_create_daily_log(user_id, today_date)
        if updated_log:
            if item_name in WAJIB_ITEMS: items = WAJIB_ITEMS
            elif item_name in SUNNAH_ITEMS: items = SUNNAH_ITEMS
            else: items = LAINNYA_ITEMS + calendar_handler.get_todays_sunnah_fasts()
            try: await query.edit_message_reply_markup(reply_markup=build_checklist_keyboard(updated_log, items, "back_to_checklist_cat"))
            except Exception as e: logger.info(f"Markup tidak berubah: {e}")
    else: await query.answer("Gagal update.", show_alert=True)

async def back_to_main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer(); await query.message.delete(); await show_main_menu(query.message, context)

async def menu_laporan_handler_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("Harian", callback_data="laporan_harian"), InlineKeyboardButton("Mingguan", callback_data="laporan_mingguan"), InlineKeyboardButton("Bulanan", callback_data="laporan_bulanan")]]
    await update.message.reply_text("Pilih periode laporan:", reply_markup=InlineKeyboardMarkup(keyboard))

async def report_period_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer("Memproses laporan...")
    _, period = query.data.split('_', 1); user_id, today = query.from_user.id, datetime.now()
    end_date = today.strftime("%Y-%m-%d")
    if period == "harian": start_date = today.strftime("%Y-%m-%d")
    elif period == "mingguan": start_date = (today - timedelta(days=6)).strftime("%Y-%m-%d")
    else: start_date = (today - timedelta(days=29)).strftime("%Y-%m-%d")
    logs = db.get_user_logs_for_period(user_id, start_date, end_date)
    report_message = report_handler.generate_report(logs, period.capitalize())
    await query.message.reply_text(report_message, parse_mode='MarkdownV2')

async def menu_feedback_handler_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Silakan ketik kritik/saran Anda.\nKirim /cancel untuk batal."); return STATE_AWAIT_FEEDBACK

async def received_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user, feedback_text = update.effective_user, update.message.text
    if db.add_feedback(user.id, user.username or "", feedback_text):
        await update.message.reply_text("Jazakallah khairan. Masukan Anda telah kami terima.")
        safe_feedback, safe_username = escape_markdown_v2(feedback_text), escape_markdown_v2(user.username or "")
        admin_message = f"📬 Masukan Baru\n\n*Dari:* @{safe_username}\n*Pesan:* {safe_feedback}"
        await context.bot.send_message(chat_id=ADMIN_USER_ID, text=admin_message, parse_mode='MarkdownV2')
    else: await update.message.reply_text("Gagal menyimpan masukan.")
    await show_main_menu(update.message, context); return ConversationHandler.END

async def menu_discussion_handler_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db.clear_discussion_history(update.effective_user.id)
    text = "Anda memasuki mode *Diskusi Islami*.\n\nSilakan ajukan pertanyaan pertama Anda terkait ibadah dan hal-hal yang berkaitan dengan Islam.\n\nKirim /selesai untuk keluar."
    await update.message.reply_text(text, parse_mode='Markdown'); return STATE_AWAIT_DISCUSSION

async def received_discussion_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id, user_question = update.effective_user.id, update.message.text
    await update.message.reply_text("_Sedang berpikir..._", parse_mode='Markdown')
    history = db.get_discussion_history(user_id)
    db.add_discussion_message(user_id, 'user', user_question)
    history.append({'role': 'user', 'content': user_question})
    ai_answer = ai_handler.generate_discussion_response(user_id, user_question, history)
    try:
        # Kita coba kirim dengan Markdown, jika gagal (karena format AI), kirim teks biasa
        await update.message.reply_text(ai_answer, parse_mode='Markdown')
        db.add_discussion_message(user_id, 'assistant', ai_answer)
    except Exception:
        await update.message.reply_text(ai_answer)
        db.add_discussion_message(user_id, 'assistant', ai_answer)
    return STATE_AWAIT_DISCUSSION

async def exit_discussion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db.clear_discussion_history(update.effective_user.id)
    await update.message.reply_text("Anda telah keluar dari mode Diskusi Islami.")
    await show_main_menu(update.message, context); return ConversationHandler.END

# --- NOTIFIKASI ---
async def notifikasi_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan menu pengaturan notifikasi."""
    user_id = update.effective_user.id
    user_data = db.find_user_by_id(user_id)
    if not user_data: return

    statuses = {
        'sholat': "✅ Hidup" if user_data.get('notif_sholat') == 1 else "❌ Mati",
        'rangkuman': "✅ Hidup" if user_data.get('notif_rangkuman') == 1 else "❌ Mati",
        'dzikir': "✅ Hidup" if user_data.get('notif_dzikir') == 1 else "❌ Mati",
        'dhuha': "✅ Hidup" if user_data.get('notif_dhuha') == 1 else "❌ Mati",
        'jumat': "✅ Hidup" if user_data.get('notif_jumat') == 1 else "❌ Mati",
        'motivasi': "✅ Hidup" if user_data.get('notif_motivasi') == 1 else "❌ Mati",
    }
    keyboard = [
        [InlineKeyboardButton(f"Waktu Sholat & Pengingat: {statuses['sholat']}", callback_data="toggle_notif_sholat")],
        [InlineKeyboardButton(f"Rangkuman Harian (21:30): {statuses['rangkuman']}", callback_data="toggle_notif_rangkuman")],
        [InlineKeyboardButton(f"Dzikir Pagi & Petang: {statuses['dzikir']}", callback_data="toggle_notif_dzikir")],
        [InlineKeyboardButton(f"Sholat Dhuha (09:00): {statuses['dhuha']}", callback_data="toggle_notif_dhuha")],
        [InlineKeyboardButton(f"Jumat (Al-Kahfi, 07:00): {statuses['jumat']}", callback_data="toggle_notif_jumat")],
        [InlineKeyboardButton(f"Motivasi Harian (07:00): {statuses['motivasi']}", callback_data="toggle_notif_motivasi")],
    ]
    # Jika dipanggil dari command, kirim pesan baru. Jika dari tombol, edit.
    if update.callback_query:
        await update.callback_query.edit_message_text("Pengaturan Notifikasi (WIB):", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text("Pengaturan Notifikasi (WIB):", reply_markup=InlineKeyboardMarkup(keyboard))

async def toggle_notification_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer(); user_id = query.from_user.id
    notif_key = query.data.split('_')[-1]; notif_type = f"notif_{notif_key}"
    
    user_data = db.find_user_by_id(user_id)
    new_status = 1 - user_data.get(notif_type, 0)
    db.set_user_notification(user_id, notif_type, new_status)
    
    base_job_name = f"{notif_type}_{user_id}"
    for job in context.job_queue.get_jobs_by_name(base_job_name): job.schedule_removal()

    if new_status == 1:
        if notif_type == "notif_sholat": 
            context.job_queue.run_daily(schedule_prayer_notifications_for_user, time(hour=2, tzinfo=WIB), user_id=user_id, name=base_job_name)
            # Jalankan sekali sekarang juga untuk hari ini
            context.job_queue.run_once(schedule_prayer_notifications_for_user, 1, user_id=user_id, name=f"immediate_{base_job_name}")
        elif notif_type == "notif_rangkuman": context.job_queue.run_daily(send_daily_summary, time(hour=21, minute=30, tzinfo=WIB), user_id=user_id, name=base_job_name)
        elif notif_type == "notif_dzikir":
            context.job_queue.run_daily(send_dzikir_notification, time(hour=6, minute=30, tzinfo=WIB), user_id=user_id, name=base_job_name, data="Pagi")
            context.job_queue.run_daily(send_dzikir_notification, time(hour=16, minute=30, tzinfo=WIB), user_id=user_id, name=base_job_name, data="Petang")
        elif notif_type == "notif_dhuha": context.job_queue.run_daily(send_dhuha_notification, time(hour=9, tzinfo=WIB), user_id=user_id, name=base_job_name)
        elif notif_type == "notif_jumat": context.job_queue.run_daily(send_jumat_reminder, time(hour=7, tzinfo=WIB), user_id=user_id, name=base_job_name)
        elif notif_type == "notif_motivasi": context.job_queue.run_daily(send_daily_motivation, time(hour=7, tzinfo=WIB), user_id=user_id, name=base_job_name)
    
    class FakeUpdate:
        def __init__(self, message): self.effective_user = message.chat; self.message = message
    await notifikasi_menu(FakeUpdate(query.message), context)
    await query.answer(f"Notifikasi '{notif_key.replace('_', ' ').capitalize()}' {'dihidupkan' if new_status else 'dimatikan'}.")

async def schedule_prayer_notifications_for_user(context: ContextTypes.DEFAULT_TYPE):
    user_id = context.job.user_id
    user_data = db.find_user_by_id(user_id)
    location = user_data.get("location")

    if not location or location == "-":
        await context.bot.send_message(chat_id=user_id, text="Notifikasi sholat gagal dijadwalkan karena lokasi Anda belum diatur."); return
        
    prayer_data = prayer_handler.get_prayer_times_raw(city=location)
    if not prayer_data:
        await context.bot.send_message(chat_id=user_id, text=f"Gagal mengambil jadwal sholat untuk '{location}' hari ini."); return
    
    prayer_times = prayer_data['timings']
    prayer_order = {"Fajr":"Subuh", "Dhuhr":"Dzuhur", "Asr":"Ashar", "Maghrib":"Maghrib", "Isha":"Isya"}

    for prayer_api_name, prayer_display_name in prayer_order.items():
        prayer_time_str = prayer_times.get(prayer_api_name)
        if not prayer_time_str: continue
        
        hour, minute = map(int, prayer_time_str.split(':'))
        prayer_time_obj = time(hour=hour, minute=minute, tzinfo=WIB)
        
        # Hanya jadwalkan jika waktunya belum lewat untuk hari ini
        if prayer_time_obj > datetime.now(WIB).time():
            # 1. Jadwalkan notifikasi tepat waktu
            context.job_queue.run_once(send_prayer_notification, prayer_time_obj, user_id=user_id, data={"prayer_name": prayer_display_name})
            
            # 2. Jadwalkan pengingat 15 menit sebelumnya
            reminder_dt = datetime.now(WIB).replace(hour=hour, minute=minute, second=0, microsecond=0) - timedelta(minutes=15)
            if reminder_dt > datetime.now(WIB):
                context.job_queue.run_once(send_reminder_notification, reminder_dt.time(), user_id=user_id, data={"prayer_name": prayer_display_name})
    logger.info(f"Berhasil menjadwalkan notifikasi sholat untuk user {user_id} di {location}")

async def send_prayer_notification(context: ContextTypes.DEFAULT_TYPE):
    """Mengirim notifikasi saat waktu sholat tiba DAN melakukan pengecekan terakhir."""
    user_id = context.job.user_id
    prayer_name = context.job.data["prayer_name"]
    
    # Kirim notifikasi utama
    await context.bot.send_message(
        chat_id=user_id, 
        text=f"🔔 Waktu sholat *{escape_markdown_v2(prayer_name)}* telah tiba!", 
        parse_mode='MarkdownV2'
    )
    # --- PENAMBAHAN LOGIKA PENGINGAT CADANGAN ---
    prayer_order = ["Subuh", "Dzuhur", "Ashar", "Maghrib", "Isya"]
    try:
        current_index = prayer_order.index(prayer_name)
        if current_index == 0:  # Tidak ada pengecekan sebelum Subuh
            return
        previous_prayer = prayer_order[current_index - 1]
    except ValueError:
        return  # Bukan sholat wajib

    today_date = datetime.now(WIB).strftime("%Y-%m-%d")
    daily_log = db.get_or_create_daily_log(user_id, today_date)

    if daily_log and daily_log.get(previous_prayer) == "Belum":
        await context.bot.send_message(
            chat_id=user_id,
            text=f"❗️ Sekadar mengingatkan, sepertinya sholat *{escape_markdown_v2(previous_prayer)}* Anda belum ditandai selesai di checklist.",
            parse_mode='MarkdownV2'
        )

async def send_reminder_notification(context: ContextTypes.DEFAULT_TYPE):
    user_id = context.job.user_id
    current_prayer = context.job.data["prayer_name"]
    prayer_order = ["Subuh", "Dzuhur", "Ashar", "Maghrib", "Isya"]
    try:
        current_index = prayer_order.index(current_prayer)
        if current_index == 0: return
        previous_prayer = prayer_order[current_index - 1]
    except ValueError: return

    today_date = datetime.now(WIB).strftime("%Y-%m-%d")
    daily_log = db.get_or_create_daily_log(user_id, today_date)
    
    if daily_log and daily_log.get(previous_prayer) == "Belum":
        await context.bot.send_message(chat_id=user_id, text=f"❗️ Pengingat: 15 menit lagi masuk waktu *{escape_markdown_v2(current_prayer)}*. Sepertinya sholat *{escape_markdown_v2(previous_prayer)}* Anda belum ditandai selesai.")

async def send_daily_summary(context: ContextTypes.DEFAULT_TYPE):
    user_id = context.job.user_id
    today_date = datetime.now(WIB).strftime("%Y-%m-%d")
    logs = db.get_user_logs_for_period(user_id, today_date, today_date)
    summary_message = report_handler.generate_report(logs, "Harian")
    await context.bot.send_message(chat_id=user_id, text=summary_message, parse_mode='MarkdownV2')

async def send_dzikir_notification(context: ContextTypes.DEFAULT_TYPE):
    user_id, time_of_day = context.job.user_id, context.job.data
    motivation = ai_handler.generate_dzikir_motivation(time_of_day)
    await context.bot.send_message(chat_id=user_id, text=f"🌤️ Waktunya Dzikir *{escape_markdown_v2(time_of_day)}*!\n\n_{motivation}_", parse_mode='MarkdownV2')

async def send_dhuha_notification(context: ContextTypes.DEFAULT_TYPE):
    user_id = context.job.user_id
    motivation = ai_handler.generate_dhuha_motivation()
    await context.bot.send_message(chat_id=user_id, text=f"✨ Jangan lupa sholat *Dhuha* ya!\n\n_{motivation}_", parse_mode='MarkdownV2')

async def send_jumat_reminder(context: ContextTypes.DEFAULT_TYPE):
    if datetime.now(WIB).weekday() in [3, 4]: # Kamis atau Jumat
        user_id = context.job.user_id
        motivation = ai_handler.generate_jumat_motivation()
        await context.bot.send_message(chat_id=user_id, text=f"🕋 *Jumat Berkah*! Jangan lupa perbanyak shalawat dan baca Surah Al-Kahfi.\n\n_{motivation}_", parse_mode='MarkdownV2')

async def send_daily_motivation(context: ContextTypes.DEFAULT_TYPE):
    user_id = context.job.user_id
    yesterday_date = (datetime.now(WIB) - timedelta(days=1)).strftime("%Y-%m-%d")
    logs = db.get_user_logs_for_period(user_id, yesterday_date, yesterday_date)
    motivation = ai_handler.generate_motivational_message(logs)
    await context.bot.send_message(chat_id=user_id, text=f"☀️ *Semangat Pagi*!\n{motivation}", parse_mode='MarkdownV2')

# --- FUNGSI MAIN ---
# Di dalam file main.py

def main() -> None:
    """Jalankan bot secara keseluruhan."""
    db.init_db()
    from telegram.ext import JobQueue
    job_queue = JobQueue()

    # Kembali ke cara inisialisasi yang paling dasar dan standar
    application = Application.builder().token(TELEGRAM_TOKEN).job_queue(job_queue).build()
    job_queue.set_application(application)
    job_queue.start()
    # --- Conversation Handlers ---
    registration_conv = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={STATE_REGISTER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_name)]},
        fallbacks=[CommandHandler('cancel', cancel)],
        per_message=False
    )
    
    location_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^Waktu Sholat 🕋$"), menu_sholat_handler_text),
            CallbackQueryHandler(ask_location_again, pattern='^change_location$')
        ],
        states={STATE_ASK_LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_location_text)]},
        fallbacks=[CommandHandler('cancel', cancel)],
        per_message=False
    )

    feedback_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^Kritik dan Saran ✍️$"), menu_feedback_handler_text)],
        states={STATE_AWAIT_FEEDBACK: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_feedback)]},
        fallbacks=[CommandHandler('cancel', cancel)],
        per_message=False
    )

    discussion_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^Diskusi Islami 💬$"), menu_discussion_handler_text)],
        states={STATE_AWAIT_DISCUSSION: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_discussion_query)]},
        fallbacks=[CommandHandler('selesai', exit_discussion)],
        per_message=False
    )

    # --- Menambahkan semua handler ke aplikasi ---
    application.add_handler(registration_conv)
    application.add_handler(location_conv)
    application.add_handler(feedback_conv)
    application.add_handler(discussion_conv)
    
    # Message Handlers untuk Menu Utama
    application.add_handler(MessageHandler(filters.Regex("^Checklist Ibadah Harian ✅$"), menu_checklist_handler_text))
    application.add_handler(MessageHandler(filters.Regex("^Laporan Ibadah 📊$"), menu_laporan_handler_text))
    application.add_handler(MessageHandler(filters.Regex("^🔔 Notifikasi$"), notifikasi_menu))

    # Command Handlers
    application.add_handler(CommandHandler("notifikasi", notifikasi_menu))
    application.add_handler(CommandHandler('start', start))

    # Callback Query Handlers untuk semua tombol inline
    application.add_handler(CallbackQueryHandler(admin_verification_handler, pattern='^approve_|^reject_'))
    application.add_handler(CallbackQueryHandler(user_terms_handler, pattern='^agree_terms_'))
    application.add_handler(CallbackQueryHandler(show_checklist_category, pattern='^checklist_cat_'))
    application.add_handler(CallbackQueryHandler(back_to_checklist_categories, pattern='^back_to_checklist_cat$'))
    application.add_handler(CallbackQueryHandler(checklist_button_handler, pattern='^checklist_'))
    application.add_handler(CallbackQueryHandler(back_to_main_menu_handler, pattern='^back_to_main_menu$'))
    application.add_handler(CallbackQueryHandler(report_period_handler, pattern='^laporan_'))
    application.add_handler(CallbackQueryHandler(toggle_notification_handler, pattern='^toggle_notif_'))
    
    print("Bot berjalan dengan semua fitur lengkap...")
    application.run_polling()

if __name__ == '__main__':
    main()