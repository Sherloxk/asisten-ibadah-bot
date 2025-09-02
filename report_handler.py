# File: report_handler.py
from datetime import datetime
import db_handler as db
import ai_handler
from utils import escape_markdown_v2

def generate_report(logs: list, period_name: str) -> str:
    safe_period_name = escape_markdown_v2(period_name)
    if not logs: return f"Belum ada data ibadah untuk *{safe_period_name}*\\."
    total_days = len(logs)
    item_counts = {item: 0 for item in db.CHECKLIST_ITEMS}
    for day_log in logs:
        for item in db.CHECKLIST_ITEMS:
            if day_log.get(item) == "Sudah": item_counts[item] += 1
    report_text = f"📊 *Laporan Ibadah \\- Periode {safe_period_name}*\n_{escape_markdown_v2(f'{total_days} hari terakhir')}_\n\n"
    total_wajib_tercatat = sum(item_counts[s] for s in db.WAJIB_ITEMS)
    total_wajib_seharusnya = total_days * len(db.WAJIB_ITEMS)
    persen_wajib = (total_wajib_tercatat/total_wajib_seharusnya*100) if total_wajib_seharusnya > 0 else 0
    report_text += f"**🕌 Ibadah Wajib**\nKomitmen: *{persen_wajib:.0f}%* `({total_wajib_tercatat}/{total_wajib_seharusnya})`\n\n"
    report_text += "**✨ Ibadah Sunnah**\n"
    for item in db.SUNNAH_ITEMS: report_text += f"\\- {escape_markdown_v2(item)}: *{item_counts[item]} kali*\n"
    report_text += "\n"
    puasa_dikerjakan = {k:v for k,v in item_counts.items() if "Puasa" in k and v > 0}
    if puasa_dikerjakan:
        report_text += "**🌙 Puasa Sunnah**\n"
        for item, count in puasa_dikerjakan.items(): report_text += f"\\- {escape_markdown_v2(item)}: *{count} kali*\n"
        report_text += "\n"
    report_text += "**💖 Ibadah Lainnya**\n"
    for item in db.LAINNYA_ITEMS: report_text += f"\\- {escape_markdown_v2(item)}: *{item_counts[item]} kali*\n"
    motivational_message = ai_handler.generate_motivational_message(logs)
    return report_text + motivational_message