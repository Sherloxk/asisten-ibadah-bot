# File: calendar_handler.py
from datetime import datetime
from hijri_converter import Gregorian

def get_todays_sunnah_fasts():
    today = datetime.now(); sunnah_fasts = []
    if today.weekday() == 0: sunnah_fasts.append("Puasa Senin")
    elif today.weekday() == 3: sunnah_fasts.append("Puasa Kamis")
    hijri_date = Gregorian(today.year, today.month, today.day).to_hijri()
    if hijri_date.day in [13, 14, 15]: sunnah_fasts.append("Puasa Ayyamul Bidh")
    if hijri_date.month == 12 and hijri_date.day == 9: sunnah_fasts.append("Puasa Arafah")
    if hijri_date.month == 1 and hijri_date.day in [9, 10]: sunnah_fasts.append("Puasa Tasu'a/Asyura")
    return sunnah_fasts