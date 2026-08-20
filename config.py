"""Конфигурация бота-уникализатора.

Все значимые параметры читаются из переменных окружения (см. .env.example),
чтобы отдел разработки мог настроить и запустить бота без правки кода.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


# --- .env (без внешних зависимостей) ----------------------------------------
def _load_dotenv(path: Path) -> None:
    """Простейший загрузчик .env: KEY=VALUE построчно. Существующие переменные
    окружения имеют приоритет (не перезаписываются)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


_load_dotenv(BASE_DIR / ".env")


# --- Telegram ---------------------------------------------------------------
def _load_token() -> str:
    """Токен из переменной окружения TG_BOT_TOKEN либо из файла token.txt рядом."""
    tok = os.environ.get("TG_BOT_TOKEN", "").strip()
    if tok:
        return tok
    tok_file = BASE_DIR / "token.txt"
    if tok_file.exists():
        return tok_file.read_text(encoding="utf-8").strip()
    return ""


BOT_TOKEN = _load_token()

# Базовый URL Telegram Bot API. Пусто = облачный api.telegram.org (лимит на
# скачивание входящих файлов — 20 МБ). Чтобы принимать файлы до 2 ГБ, подними
# локальный сервер telegram-bot-api и укажи, например, http://localhost:8081
TELEGRAM_API_BASE = os.environ.get("TELEGRAM_API_BASE", "").strip()
# Локальный сервер может отдавать file_path абсолютным путём на диске —
# тогда скачивание не нужно, читаем файл напрямую (режим "local").
TELEGRAM_API_LOCAL_MODE = os.environ.get("TELEGRAM_API_LOCAL_MODE", "0") in ("1", "true", "True")


def _parse_ids(raw: str) -> set[int]:
    return {int(x) for x in raw.replace(",", " ").split() if x.strip().isdigit()}


# Пусто = доступ всем. Иначе — список Telegram user_id через запятую/пробел.
ALLOWED_USER_IDS: set[int] = _parse_ids(os.environ.get("ALLOWED_USER_IDS", ""))


# --- ffmpeg -----------------------------------------------------------------
# По умолчанию системный ffmpeg/ffprobe. Можно указать пути через окружение.
# Для HDR-исходников нужен ffmpeg со zscale/libzimg (в сборках homebrew и в
# большинстве пакетов Linux он есть); для SDR-видео подойдёт любой ffmpeg.
_FFMPEG_LOCAL = BASE_DIR / "bin" / "ffmpeg"
FFMPEG = os.environ.get("FFMPEG_BIN") or (
    str(_FFMPEG_LOCAL) if _FFMPEG_LOCAL.exists() else "ffmpeg")
FFPROBE = os.environ.get("FFPROBE_BIN", "ffprobe")


# --- Видео-параметры вывода -------------------------------------------------
W = int(os.environ.get("OUT_W", 1080))
H = int(os.environ.get("OUT_H", 1920))
FPS = int(os.environ.get("OUT_FPS", 30))
CRF = int(os.environ.get("OUT_CRF", 20))
PRESET = os.environ.get("OUT_PRESET", "fast")
AUDIO_RATE = int(os.environ.get("OUT_AUDIO_RATE", 48000))

# Нормализовать вход к W×H перед уникализацией. True — стабильные метаданные и
# одинаковый размер на выходе (рекомендуется). False — сохраняет исходный кадр.
NORMALIZE_INPUT = os.environ.get("NORMALIZE_INPUT", "1") not in ("0", "false", "False")


# --- Кнопки выбора числа версий (в интерфейсе бота) -------------------------
COUNT_CHOICES = _parse_ids(os.environ.get("COUNT_CHOICES", "1 3 5 10")) or {1, 3, 5, 10}
MAX_COUNT = int(os.environ.get("MAX_COUNT", 20))


# --- Параметры уникализации -------------------------------------------------
# «Сбалансированный» пресет: заметный сдвиг фингерпринта без видимой деградации.
# geometry=True добавляет зум+кроп и обрезку кадров (сильнее уникализирует, но
# может подрезать текст у краёв). Для видео с вшитыми субтитрами — geometry=False.
UNIQUIFY = {
    "speed": (
        float(os.environ.get("UNIQ_SPEED_MIN", 0.97)),
        float(os.environ.get("UNIQ_SPEED_MAX", 1.03)),
    ),
    "zoom": (1.01, 1.03),            # используется только при geometry=True
    "brightness": float(os.environ.get("UNIQ_BRIGHTNESS", 0.03)),
    "contrast": float(os.environ.get("UNIQ_CONTRAST", 0.04)),
    "saturation": float(os.environ.get("UNIQ_SATURATION", 0.06)),
    "gamma": float(os.environ.get("UNIQ_GAMMA", 0.05)),
    "hue": float(os.environ.get("UNIQ_HUE", 3.0)),     # ±градусы
    "noise": (4, 8),                 # слабое зерно (alls)
    "trim_frames": (2, 9),           # обрезка кадров с начала (geometry=True)
    "crf": (
        int(os.environ.get("UNIQ_CRF_MIN", 20)),
        int(os.environ.get("UNIQ_CRF_MAX", 24)),
    ),
}

# По умолчанию без геометрии (безопасно для вшитых субтитров/логотипов).
GEOMETRY = os.environ.get("UNIQ_GEOMETRY", "0") in ("1", "true", "True")


# --- Лимиты Telegram --------------------------------------------------------
# Отдаём файлы не больше этого размера (лимит sendVideo/sendDocument ~50 МБ).
TELEGRAM_MAX_MB = int(os.environ.get("TELEGRAM_MAX_MB", 48))


# --- Рабочие папки ----------------------------------------------------------
WORK_DIR = BASE_DIR / "work"      # временные файлы по каждому запросу
OUT_DIR = BASE_DIR / "out"        # готовые ролики

for _d in (WORK_DIR, OUT_DIR):
    _d.mkdir(parents=True, exist_ok=True)
