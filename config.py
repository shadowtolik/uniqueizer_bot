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
# Пресет x264 для самой уникализации (качество некритично) — быстрее ре-энкод.
UNIQ_PRESET = os.environ.get("UNIQ_PRESET", "veryfast")
AUDIO_RATE = int(os.environ.get("OUT_AUDIO_RATE", 48000))

# Нормализовать вход к W×H перед уникализацией. True — стабильные метаданные и
# одинаковый размер на выходе (рекомендуется). False — сохраняет исходный кадр.
NORMALIZE_INPUT = os.environ.get("NORMALIZE_INPUT", "1") not in ("0", "false", "False")


# --- Кнопки выбора числа версий (в интерфейсе бота) -------------------------
COUNT_CHOICES = _parse_ids(os.environ.get("COUNT_CHOICES", "1 3 5 10")) or {1, 3, 5, 10}
MAX_COUNT = int(os.environ.get("MAX_COUNT", 20))


# --- Параметры уникализации -------------------------------------------------
# Жёсткий пресет: сильный сдвиг видео- и аудио-фингерпринта без видимой деградации
# (против дедупа Instagram/TikTok). geometry=True добавляет зум+микро-поворот+кроп
# и обрезку кадров; фильтры (colorbalance/vignette/eq/hue) и аудио-питч — всегда.
# Для видео с текстом у самых краёв ставь geometry=False.
UNIQUIFY = {
    "speed": (
        float(os.environ.get("UNIQ_SPEED_MIN", 0.97)),
        float(os.environ.get("UNIQ_SPEED_MAX", 1.03)),
    ),
    # --- геометрия (только при geometry=True) ---
    "zoom": (1.05, 1.08),            # увеличение (поле под поворот/сдвиг)
    "rotate": float(os.environ.get("UNIQ_ROTATE", 1.0)),   # ±градусы микро-поворота
    "trim_frames": (2, 9),           # обрезка кадров с начала
    # --- цвет/тон (умеренно, без видимого каста) ---
    "brightness": float(os.environ.get("UNIQ_BRIGHTNESS", 0.03)),
    "contrast": float(os.environ.get("UNIQ_CONTRAST", 0.05)),
    "saturation": float(os.environ.get("UNIQ_SATURATION", 0.07)),
    "gamma": float(os.environ.get("UNIQ_GAMMA", 0.05)),
    "hue": float(os.environ.get("UNIQ_HUE", 2.0)),     # ±градусы (больше — тонирует)
    # --- фильтры-оверлеи (всегда, не режут кадр) ---
    "colorbalance": float(os.environ.get("UNIQ_COLORBALANCE", 0.02)),  # сдвиг грейда
    "vignette": (0.32, 0.50),        # угол виньетки, рад (МЕНЬШЕ = светлее)
    "noise": (2, 5),                 # лёгкое зерно (сильное раздувает файл)
    "crf": (
        int(os.environ.get("UNIQ_CRF_MIN", 21)),
        int(os.environ.get("UNIQ_CRF_MAX", 25)),
    ),
    # --- аудио: микро-сдвиг тона против аудио-хеша (на слух почти незаметно) ---
    "pitch_cents": float(os.environ.get("UNIQ_PITCH_CENTS", 35)),  # ±центы
}

# По умолчанию ЖЁСТКО — с геометрией (UNIQ_GEOMETRY=0 отключает для видео с
# текстом у самых краёв).
GEOMETRY = os.environ.get("UNIQ_GEOMETRY", "1") in ("1", "true", "True")


# --- Лимиты Telegram --------------------------------------------------------
# Отдаём файлы не больше этого размера (лимит sendVideo/sendDocument ~50 МБ).
TELEGRAM_MAX_MB = int(os.environ.get("TELEGRAM_MAX_MB", 48))


# --- Рабочие папки ----------------------------------------------------------
WORK_DIR = BASE_DIR / "work"      # временные файлы по каждому запросу
OUT_DIR = BASE_DIR / "out"        # готовые ролики

for _d in (WORK_DIR, OUT_DIR):
    _d.mkdir(parents=True, exist_ok=True)
