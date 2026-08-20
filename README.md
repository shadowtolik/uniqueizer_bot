# Uniqueizer Bot 🔀

Телеграм-бот, который из одного готового видео собирает **N уникальных версий**.
Каждая версия получает случайные микро-изменения (цвет, тон, зерно, скорость) и
**полностью переписанные метаданные**, поэтому визуальный и аудио-«отпечаток»
(fingerprint) ролика сдвигается. Для систем дедупликации контента (Instagram
Reels, TikTok и т.п.) версии выглядят как разные ролики, при этом на глаз
качество не меняется.

Работает автономно: только Python + `ffmpeg`, **без вызовов Claude, OpenAI и
любых внешних API**. Всё считается локально на машине, где запущен бот.

---

## Что именно меняется

| Параметр | По умолчанию | Зачем |
|---|---|---|
| Скорость (`setpts` + `atempo`) | ±3 % | Смещает тайминги и число кадров |
| Яркость / контраст / насыщенность / гамма (`eq`) | ±3–6 % | Сдвигает цветовой фингерпринт |
| Оттенок (`hue`) | ±3° | То же |
| Зерно (`noise`) | лёгкое | Ломает попиксельное сравнение |
| CRF при кодировании | случайный 20–24 | Разный битрейт/вес |
| Метаданные | сброс + случайные | Разные `encoder`/`comment`, нет исходных тегов |
| Геометрия (зум+кроп+обрезка кадров) | **выкл** | Сильнее уникализирует, но может подрезать текст у краёв |

По умолчанию **геометрия выключена** — это безопасно для видео с вшитыми
субтитрами и логотипами (ничего не обрезается и не сдвигается). Включается флагом
`UNIQ_GEOMETRY=1`, если нужен более агрессивный сдвиг и края не важны.

---

## Требования

- **Python 3.11+**
- **ffmpeg** и **ffprobe** в `PATH`
  (для HDR-исходников нужна сборка со `zscale`/`libzimg` — в homebrew и в
  большинстве пакетов Linux она есть; для обычного SDR-видео подойдёт любой ffmpeg)
- Токен бота от [@BotFather](https://t.me/BotFather)

Установка ffmpeg:

```bash
# macOS
brew install ffmpeg
# Debian/Ubuntu
sudo apt-get update && sudo apt-get install -y ffmpeg
```

---

## Быстрый старт

```bash
git clone <URL-этого-репозитория> uniqueizer_bot
cd uniqueizer_bot

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# открой .env и впиши TG_BOT_TOKEN от @BotFather

python bot.py
```

Бот запустится в режиме long-polling. Открой его в Telegram, отправь `/start`,
пришли видео, выбери число версий — получишь готовые ролики.

Токен можно задать тремя способами (приоритет сверху вниз):
1. переменная окружения `TG_BOT_TOKEN`;
2. строка в файле `.env` рядом с `bot.py`;
3. файл `token.txt` рядом с `bot.py` (одной строкой).

---

## Настройка (`.env`)

Все параметры необязательны, кроме `TG_BOT_TOKEN`. Полный список с комментариями —
в [`.env.example`](.env.example). Часто нужные:

| Переменная | По умолчанию | Описание |
|---|---|---|
| `TG_BOT_TOKEN` | — | **Обязательно.** Токен бота от @BotFather |
| `ALLOWED_USER_IDS` | пусто (все) | Список Telegram `user_id` через запятую/пробел — кому можно пользоваться |
| `COUNT_CHOICES` | `1 3 5 10` | Кнопки выбора числа версий |
| `MAX_COUNT` | `20` | Максимум версий за один запрос |
| `UNIQ_GEOMETRY` | `0` | `1` — включить зум+кроп (агрессивнее, но режет края) |
| `NORMALIZE_INPUT` | `1` | Приводить вход к `OUT_W×OUT_H` перед уникализацией |
| `OUT_W`/`OUT_H`/`OUT_FPS` | `1080`/`1920`/`30` | Параметры вывода |
| `TELEGRAM_MAX_MB` | `48` | Порог, выше которого файл пережимается под лимит Telegram |

Свой `user_id` для `ALLOWED_USER_IDS` можно узнать у [@userinfobot](https://t.me/userinfobot).

---

## Запуск как сервис (Linux, systemd)

`/etc/systemd/system/uniqueizer-bot.service`:

```ini
[Unit]
Description=Uniqueizer Telegram Bot
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/uniqueizer_bot
EnvironmentFile=/opt/uniqueizer_bot/.env
ExecStart=/opt/uniqueizer_bot/.venv/bin/python /opt/uniqueizer_bot/bot.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now uniqueizer-bot
sudo journalctl -u uniqueizer-bot -f   # логи
```

> Держи **один** запущенный экземпляр на токен: Telegram не даёт двум процессам
> одновременно поллить одного бота.

---

## Большие входные файлы (важно)

Через облачный Bot API Telegram отдаёт боту на скачивание файлы **не больше 20 МБ**.
Если пользователи будут присылать более тяжёлые ролики, подними
[локальный Bot API сервер](https://github.com/tdlib/telegram-bot-api) и укажи боту
его адрес (в aiogram — через `Bot(..., session=AiohttpSession(api=TelegramAPIServer.from_base("http://localhost:8081")))`).
С локальным сервером лимит скачивания — до 2 ГБ.

На **выход** действует лимит ~50 МБ на `sendVideo`/`sendDocument`; бот сам
пережимает файлы под `TELEGRAM_MAX_MB` (по умолчанию 48 МБ).

---

## Структура проекта

```
uniqueizer_bot/
├── bot.py            # телеграм-бот (aiogram): диалог и отправка результатов
├── uniquifier.py     # ядро: ffmpeg-нормализация и уникализация (без внешних API)
├── config.py         # конфиг из переменных окружения / .env / token.txt
├── requirements.txt  # зависимости (только aiogram)
├── .env.example      # шаблон настроек
├── .gitignore
├── work/             # временные файлы (создаётся автоматически, в .gitignore)
└── out/              # готовые ролики      (создаётся автоматически, в .gitignore)
```

Ядро можно использовать и без Telegram:

```python
from pathlib import Path
from uniquifier import uniquify_file

versions = uniquify_file(Path("input.mp4"), Path("out"), "myclip", count=5)
print(versions)   # [out/myclip_1.mp4, ..., out/myclip_5.mp4]
```

---

## Как это работает под капотом

1. **Нормализация** (`normalize`) — вход приводится к `1080×1920`, `30 fps`,
   `h264/aac`, стерео, SDR/BT.709. HDR (PQ/HLG) тонмапится в SDR. Это делает
   метаданные и размеры стабильными и предсказуемыми.
2. **N проходов** (`uniquify_once`) — каждый со своими случайными значениями
   цвета/скорости/зерна/CRF и уникальными метаданными.
3. **Подгон под Telegram** (`ensure_telegram_size`) — если версия тяжелее лимита,
   она пережимается подбором CRF.

Все версии в пределах запроса гарантированно различаются и по содержимому
(разный md5), и по длительности (из-за случайной скорости).

---

## Оговорка

Инструмент меняет только сам медиафайл (перекодирование и метаданные) и не
взаимодействует ни с какими сторонними платформами. Ответственность за
соблюдение правил площадок, где публикуется контент, лежит на пользователе.
