"""Text normalization, cleaning, and semantic analysis utilities."""

import re
import unicodedata
from core.logger import setup_logging
from shared.enums import LeadLevelEnum

logger = setup_logging(__name__)

# جدول یکسان‌سازی حروف و اعداد عربی/فارسی به استاندارد واحد
CHAR_MAP = {
    "ك": "ک",
    "ي": "ی",
    "ئ": "ی",
    "إ": "ا",
    "أ": "ا",
    "آ": "ا",
    "ة": "ه",
    "ؤ": "و",
    "١": "1",
    "٢": "2",
    "٣": "3",
    "٤": "4",
    "٥": "5",
    "٦": "6",
    "٧": "7",
    "٨": "8",
    "٩": "9",
    "٠": "0",
    "۱": "1",
    "۲": "2",
    "۳": "3",
    "۴": "4",
    "۵": "5",
    "۶": "6",
    "۷": "7",
    "۸": "8",
    "۹": "9",
    "۰": "0",
}

DIACRITICS_RE = re.compile(r"[\u064B-\u0652\u0670]")
URL_RE = re.compile(r"https?://\S+|www\.\S+|t\.me/\S+|@[a-zA-Z0-9_]+")
EXTRA_SPACES_RE = re.compile(r"\s+")
EXTRA_ZWNJ_RE = re.compile(r"\u200c+")
# حروف/ارقام فارسی، عربی و لاتین برای توکن معنادار و مرز کلمه
MEANINGFUL_TOKEN_RE = re.compile(r"[0-9A-Za-z\u0600-\u06FF]+")


def normalize_chars(text: str) -> str:
    """تبدیل کاراکترها و اعداد عربی/فارسی به نسخه یکسان استاندارد."""
    return "".join(CHAR_MAP.get(char, char) for char in text)


def remove_diacritics(text: str) -> str:
    """حذف اعراب و نشانه‌های آوازی."""
    return DIACRITICS_RE.sub("", text)


def remove_urls_and_mentions(text: str) -> str:
    """حذف لینک‌ها و آیدی‌های تلگرام."""
    return URL_RE.sub(" ", text)


def remove_emojis_and_symbols(text: str) -> str:
    """حذف ایموجی‌ها و نمادهای غیرمتنی."""
    cleaned = []
    for char in text:
        category = unicodedata.category(char)
        if category.startswith("S") or category in ("So", "Cn"):
            cleaned.append(" ")
        else:
            cleaned.append(char)
    return "".join(cleaned)


def normalize_spaces(text: str) -> str:
    """حذف فاصله‌ها و نیم‌فاصله‌های اضافی و متوالی."""
    text = EXTRA_ZWNJ_RE.sub("\u200c", text)
    text = EXTRA_SPACES_RE.sub(" ", text)
    return text.strip()


def clean_text(raw_text: str) -> str:
    """
    خط لوله کامل نرمال‌سازی متن ورودی جهت تطبیق دقیق کلمات کلیدی.
    """
    if not raw_text:
        return ""

    text = raw_text.lower()
    text = normalize_chars(text)
    text = remove_diacritics(text)
    text = remove_urls_and_mentions(text)
    text = remove_emojis_and_symbols(text)
    text = normalize_spaces(text)

    return text


def tokenize_meaningful_words(text: str) -> list[str]:
    """توکن‌های حرف/رقم پس از تبدیل نیم‌فاصله به فاصله."""
    if not text:
        return []
    prepared = text.replace("\u200c", " ")
    return MEANINGFUL_TOKEN_RE.findall(prepared)


def count_meaningful_tokens(text: str) -> int:
    """تعداد کلمات معنادار فارسی/لاتین/عددی در متن نرمال‌شده."""
    return len(tokenize_meaningful_words(text))


def has_phrase_match(text: str, phrase: str) -> bool:
    """
    تطبیق عبارت بر پایهٔ دنبالهٔ متوالی توکن‌ها (مرز کلمه).
    هم تک‌کلمه‌ای و هم چندکلمه‌ای را پوشش می‌دهد.
    """
    text_tokens = tokenize_meaningful_words(text)
    phrase_tokens = tokenize_meaningful_words(phrase)
    if not phrase_tokens or len(phrase_tokens) > len(text_tokens):
        return False
    window = len(phrase_tokens)
    for index in range(len(text_tokens) - window + 1):
        if text_tokens[index : index + window] == phrase_tokens:
            return True
    return False


async def score_intent(text: str) -> tuple[float, LeadLevelEnum]:
    """
    Perform semantic analysis and return an intent confidence score.
    (Placeholder for LLM/Embedding analysis in later phases)
    """
    logger.debug("NLP intent scoring placeholder called")
    # در فازهای بعدی مدل هوش مصنوعی در این بخش قرار می‌گیرد
    return 1.0, LeadLevelEnum.HOT


