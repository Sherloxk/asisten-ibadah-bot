# File: utils.py
def escape_markdown_v2(text: str) -> str:
    """Melindungi teks agar aman dikirim menggunakan MarkdownV2."""
    if not isinstance(text, str): 
        return ""
    # Karakter yang harus di-escape dalam MarkdownV2
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return ''.join(f'\\{char}' if char in escape_chars else char for char in text)