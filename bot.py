"""Telegram-бот «Уникализатор видео».

Сценарий:
  1. Пользователь присылает готовое видео (как видео или файлом).
  2. Выбирает, сколько уникальных версий сделать.
  3. Бот прогоняет видео через уникализатор (случайные микро-трансформации
     цвета/тона/зерна/скорости + подмена метаданных) и присылает N версий.

Запуск:  TG_BOT_TOKEN=... python3 bot.py
"""

import asyncio
import logging
import shutil
import time
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message,
)

import config as cfg
from uniquifier import uniquify_file, ensure_telegram_size

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("uniqbot")

dp = Dispatcher()


class Flow(StatesGroup):
    wait_video = State()   # ждём готовое видео
    wait_count = State()   # выбор числа версий
    wait_geom = State()    # выбор режима геометрии


def _allowed(user_id: int) -> bool:
    return not cfg.ALLOWED_USER_IDS or user_id in cfg.ALLOWED_USER_IDS


def _count_kb() -> InlineKeyboardMarkup:
    choices = sorted(n for n in cfg.COUNT_CHOICES if 0 < n <= cfg.MAX_COUNT)
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=str(n), callback_data=f"cnt:{n}") for n in choices
    ]])


def _geom_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛡 Безопасно (без геометрии)", callback_data="geo:safe")],
        [InlineKeyboardButton(text="⚡️ Агрессивно (зум+кроп+обрезка)", callback_data="geo:full")],
    ])


def _udir(user_id: int) -> Path:
    d = cfg.WORK_DIR / f"u{user_id}"
    d.mkdir(parents=True, exist_ok=True)
    return d


HELLO = (
    "🔀 <b>Уникализатор видео</b>\n\n"
    "Пришли готовое видео — верну несколько уникальных версий.\n"
    "Меняю только цвет, тон, зерно, скорость и метаданные — субтитры, музыка "
    "и кадрирование остаются как есть.\n\n"
    "Пришли видео (как видео или файлом)."
)


@dp.message(CommandStart())
async def on_start(msg: Message, state: FSMContext):
    if not _allowed(msg.from_user.id):
        await msg.answer("Доступ запрещён.")
        return
    await state.clear()
    await state.set_state(Flow.wait_video)
    await msg.answer(HELLO)


@dp.message(Command("cancel"))
async def on_cancel(msg: Message, state: FSMContext):
    await state.clear()
    await state.set_state(Flow.wait_video)
    await msg.answer("Отменил. Пришли видео для уникализации.")


async def _download(msg: Message, bot: Bot, dest: Path) -> bool:
    file_obj = msg.video or msg.document or msg.animation
    if msg.document and not (msg.document.mime_type or "").startswith("video"):
        await msg.answer("Это не похоже на видео. Пришли видео-файл.")
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        tg_file = await bot.get_file(file_obj.file_id)
        if cfg.TELEGRAM_API_LOCAL_MODE and tg_file.file_path and Path(tg_file.file_path).is_file():
            # локальный Bot API (--local): файл уже лежит на диске, копируем
            await asyncio.to_thread(shutil.copy, tg_file.file_path, dest)
        else:
            await bot.download_file(tg_file.file_path, destination=dest)
    except Exception as e:  # noqa: BLE001
        await msg.answer(
            f"Не смог скачать файл: {e}\n"
            "Через облачный Bot API лимит загрузки — 20 МБ. Для файлов больше "
            "нужен локальный Bot API сервер (см. README)."
        )
        return False
    return True


@dp.message(F.video | F.document | F.animation)
async def on_video(msg: Message, state: FSMContext, bot: Bot):
    if not _allowed(msg.from_user.id):
        await msg.answer("Доступ запрещён.")
        return
    await msg.answer("Скачиваю видео…")
    if not await _download(msg, bot, _udir(msg.from_user.id) / "src.mp4"):
        return
    await state.set_state(Flow.wait_count)
    await msg.answer("Видео принято. Сколько уникальных версий сделать?",
                     reply_markup=_count_kb())


@dp.callback_query(Flow.wait_count, F.data.startswith("cnt:"))
async def on_count(cb: CallbackQuery, state: FSMContext):
    n = int(cb.data.split(":", 1)[1])
    await _ask_geom(cb.message, state, n)
    await cb.answer()


@dp.message(Flow.wait_count, F.text.regexp(r"^\d+$"))
async def on_count_typed(msg: Message, state: FSMContext):
    await _ask_geom(msg, state, int(msg.text))


async def _ask_geom(msg: Message, state: FSMContext, n: int):
    n = max(1, min(n, cfg.MAX_COUNT))
    await state.update_data(uniq_n=n)
    await state.set_state(Flow.wait_geom)
    try:
        await msg.edit_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001
        pass
    await msg.answer(
        "Какой режим уникализации?\n"
        "🛡 <b>Безопасно</b> — цвет/тон/зерно/скорость/метаданные. Кадр целиком, "
        "субтитры и логотипы не режутся.\n"
        "⚡️ <b>Агрессивно</b> — то же плюс зум+кроп и обрезка первых кадров: "
        "сильнее сдвигает отпечаток, но подрезает края (не для вшитых субтитров).",
        reply_markup=_geom_kb(),
    )


@dp.callback_query(Flow.wait_geom, F.data.startswith("geo:"))
async def on_geom(cb: CallbackQuery, state: FSMContext):
    geometry = cb.data.split(":", 1)[1] == "full"
    data = await state.get_data()
    n = int(data.get("uniq_n", 1))
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001
        pass
    await cb.answer()
    await _run_uniquify(cb.message, state, cb.from_user.id, n, geometry)


async def _run_uniquify(msg: Message, state: FSMContext, uid: int, n: int,
                        geometry: bool):
    n = max(1, min(n, cfg.MAX_COUNT))
    src = _udir(uid) / "src.mp4"
    if not src.exists():
        await state.set_state(Flow.wait_video)
        await msg.answer("Видео потерялось — пришли его заново.")
        return
    mode = "агрессивно (с геометрией)" if geometry else "безопасно"
    await msg.answer(
        f"Делаю {n} уникальн{'ую версию' if n == 1 else 'ых версий'} — режим: {mode}… "
        "это может занять до пары минут."
    )
    base = f"uniq_{uid}_{int(time.time())}"
    try:
        outs = await asyncio.to_thread(uniquify_file, src, cfg.OUT_DIR, base, n, geometry)
    except Exception as e:  # noqa: BLE001
        log.exception("uniquify failed")
        await msg.answer(f"Ошибка уникализации: {e}")
        return
    for i, out in enumerate(outs, 1):
        await _send_result(msg, out, caption=f"Уникальная версия {i}/{n}")
    await state.set_state(Flow.wait_video)
    await msg.answer("Готово ✅ Пришли ещё видео, если нужно.")


async def _send_result(msg: Message, out_path: Path, caption: str | None = None):
    out_path = await asyncio.to_thread(ensure_telegram_size, out_path)
    await msg.answer_video(
        FSInputFile(out_path), width=cfg.W, height=cfg.H, supports_streaming=True,
        caption=caption,
    )
    # Дублируем файлом — без потери качества при пересылке/скачивании.
    await msg.answer_document(
        FSInputFile(out_path), disable_content_type_detection=True, caption=caption,
    )


@dp.message()
async def on_fallback(msg: Message, state: FSMContext):
    if not _allowed(msg.from_user.id):
        return
    cur = await state.get_state()
    if cur == Flow.wait_count.state:
        await msg.answer("Выбери число версий кнопкой выше или пришли число.",
                         reply_markup=_count_kb())
    elif cur == Flow.wait_geom.state:
        await msg.answer("Выбери режим уникализации кнопкой выше.",
                         reply_markup=_geom_kb())
    else:
        await msg.answer("Пришли видео для уникализации (как видео или файлом).")


async def main():
    if not cfg.BOT_TOKEN:
        raise SystemExit(
            "Нет токена бота. Задай TG_BOT_TOKEN или положи token.txt рядом с bot.py."
        )
    session = None
    if cfg.TELEGRAM_API_BASE:
        api = TelegramAPIServer.from_base(cfg.TELEGRAM_API_BASE,
                                          is_local=cfg.TELEGRAM_API_LOCAL_MODE)
        session = AiohttpSession(api=api)
        log.info("Локальный Bot API: %s (local_mode=%s)",
                 cfg.TELEGRAM_API_BASE, cfg.TELEGRAM_API_LOCAL_MODE)
    bot = Bot(cfg.BOT_TOKEN, session=session,
              default=DefaultBotProperties(parse_mode="HTML"))
    log.info("Уникализатор запущен. geometry=%s, choices=%s, api=%s",
             cfg.GEOMETRY, sorted(cfg.COUNT_CHOICES), cfg.TELEGRAM_API_BASE or "cloud")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
