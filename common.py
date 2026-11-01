import re

_AZ = str.maketrans({
    "ə": "e", "Ə": "e", "ı": "i", "İ": "i", "ö": "o", "Ö": "o",
    "ü": "u", "Ü": "u", "ç": "c", "Ç": "c", "ş": "s", "Ş": "s",
    "ğ": "g", "Ğ": "g",
})


def slugify(text, max_len=70):
    text = text.translate(_AZ).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:max_len].strip("-") or "xeber"
