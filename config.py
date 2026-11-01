import os

SITE_NAME = os.getenv("SITE_NAME", "Xəbər Saytım")
SITE_TAGLINE = os.getenv("SITE_TAGLINE", "Gündəlik xəbərlərin qısa və aydın xülasəsi")
SITE_URL = os.getenv("SITE_URL", "https://example.com").rstrip("/")
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "info@example.com")
LANG_CODE = "az"
LANG_NAME = "Azərbaycan dili"

# AI xidməti: "gemini" (pulsuz planı var) və ya "claude" (pulludur)
AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini").lower()
GEMINI_MODEL = os.getenv("GEMINI_MODEL") or "gemini-3.5-flash-lite"
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")

# Hər işləmədə maksimum yeni xəbər və hər lentdən maksimum xəbər.
# Az amma keyfiyyətli xəbər Google üçün daha yaxşıdır.
MAX_PER_RUN = int(os.getenv("MAX_PER_RUN", "2"))
PER_FEED = int(os.getenv("PER_FEED", "2"))

# true olsa, xəbərlər "draft" olaraq saxlanır; content/*.json faylında
# "status": "published" etsən dərc olunur (GitHub mobil tətbiqindən də olur).
REVIEW_MODE = os.getenv("REVIEW_MODE", "false").lower() == "true"
