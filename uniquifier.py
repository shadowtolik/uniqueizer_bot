"""Уникализация видео чистым ffmpeg (без Claude, без внешних сервисов).

Из одного готового ролика собирает N уникальных версий: у каждой свои
случайные микро-трансформации (скорость, цвет/тон, зерно, CRF) и полностью
переписанные метаданные. Визуальный и аудио-фингерпринт сдвигается так, что
для алгоритмов дедупликации (в т.ч. Instagram/TikTok) версии выглядят разными
роликами, при этом на глаз качество не страдает.
"""

from __future__ import annotations

import random
import subprocess
import uuid
from pathlib import Path

import config as cfg


# --------------------------------------------------------------------------- #
# ffmpeg / ffprobe helpers
# --------------------------------------------------------------------------- #
def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed ({proc.returncode})\nCMD: {' '.join(cmd)}\n"
            f"STDERR:\n{proc.stderr[-2000:]}"
        )


def has_audio(path: Path) -> bool:
    out = subprocess.run(
        [cfg.FFPROBE, "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=index", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    return bool(out.stdout.strip())


def is_hdr(path: Path) -> bool:
    """HDR, если трансфер PQ (smpte2084) или HLG (arib-std-b67)."""
    out = subprocess.run(
        [cfg.FFPROBE, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=color_transfer", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    return out.stdout.strip() in ("smpte2084", "arib-std-b67")


# --------------------------------------------------------------------------- #
# Нормализация к W×H, гарантированно со стерео-аудио и SDR-тегами
# --------------------------------------------------------------------------- #
_SCALE = (
    f"scale={cfg.W}:{cfg.H}:force_original_aspect_ratio=decrease,"
    f"pad={cfg.W}:{cfg.H}:(ow-iw)/2:(oh-ih)/2:black,"
    f"fps={cfg.FPS},format=yuv420p,"
    "setparams=colorspace=bt709:color_primaries=bt709:color_trc=bt709:range=tv"
)

# HDR (PQ/HLG) → SDR (BT.709): линеаризуем, тонмапим (hable), возвращаем в bt709.
# Требует ffmpeg со zscale/libzimg. Применяется только к HDR-исходникам.
_HDR_TO_SDR = (
    "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
    "tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p,"
)

_SDR_TAGS = ["-colorspace", "bt709", "-color_primaries", "bt709",
             "-color_trc", "bt709", "-color_range", "tv"]


def normalize(src: Path, dst: Path) -> Path:
    """Перекодирует src → dst (W×H, FPS, h264/aac, стерео, SDR/BT.709).
    HDR-исходники тонмапятся в SDR; при отсутствии аудио добавляется тишина."""
    src = Path(src)
    vf = (_HDR_TO_SDR + _SCALE) if is_hdr(src) else _SCALE
    common_v = ["-c:v", "libx264", "-crf", str(cfg.CRF), "-preset", cfg.PRESET, *_SDR_TAGS]
    common_a = ["-c:a", "aac", "-ar", str(cfg.AUDIO_RATE), "-ac", "2"]
    if has_audio(src):
        cmd = [cfg.FFMPEG, "-y", "-i", str(src),
               "-vf", vf, *common_v, *common_a, "-movflags", "+faststart", str(dst)]
    else:
        cmd = [cfg.FFMPEG, "-y", "-i", str(src),
               "-f", "lavfi",
               "-i", f"anullsrc=channel_layout=stereo:sample_rate={cfg.AUDIO_RATE}",
               "-map", "0:v:0", "-map", "1:a:0",
               "-vf", vf, *common_v, *common_a, "-shortest",
               "-movflags", "+faststart", str(dst)]
    _run(cmd)
    return dst


# --------------------------------------------------------------------------- #
# Один проход уникализации
# --------------------------------------------------------------------------- #
def uniquify_once(video: Path, out: Path, geometry: bool | None = None) -> Path:
    """Одна уникальная версия: случайные скорость, цвет/тон, зерно, чистка+
    подмена метаданных, случайный CRF. geometry=True добавляет зум+кроп и обрезку
    первых кадров (сильнее, но может подрезать текст у краёв)."""
    if geometry is None:
        geometry = cfg.GEOMETRY
    u = cfg.UNIQUIFY
    spd = random.uniform(*u["speed"])
    br = random.uniform(-u["brightness"], u["brightness"])
    co = 1 + random.uniform(-u["contrast"], u["contrast"])
    sa = 1 + random.uniform(-u["saturation"], u["saturation"])
    ga = 1 + random.uniform(-u["gamma"], u["gamma"])
    hu = random.uniform(-u["hue"], u["hue"])
    noi = random.randint(*u["noise"])
    crf = random.randint(*u["crf"])

    geo = ""
    ss: list[str] = []
    if geometry:
        z = random.uniform(*u["zoom"])
        ox, oy = random.random(), random.random()
        geo = (f"scale=iw*{z:.4f}:ih*{z:.4f},"
               f"crop={cfg.W}:{cfg.H}:(iw-{cfg.W})*{ox:.3f}:(ih-{cfg.H})*{oy:.3f},")
        ss = ["-ss", f"{random.randint(*u['trim_frames']) / cfg.FPS:.3f}"]

    vf = (
        f"{geo}"
        f"eq=brightness={br:.3f}:contrast={co:.3f}:saturation={sa:.3f}:gamma={ga:.3f},"
        f"hue=h={hu:.2f},noise=alls={noi}:allf=t,"
        f"setpts=PTS/{spd:.4f},format=yuv420p"
    )
    cmd = [
        cfg.FFMPEG, "-y", *ss, "-i", str(video),
        "-vf", vf, "-af", f"atempo={spd:.4f}",
        "-map_metadata", "-1",
        "-metadata", f"encoder=lavf-{random.randint(1000, 9999)}",
        "-metadata", f"comment={uuid.uuid4().hex[:16]}",
        "-c:v", "libx264", "-crf", str(crf), "-preset", cfg.PRESET, *_SDR_TAGS,
        "-c:a", "aac", "-ar", str(cfg.AUDIO_RATE), "-ac", "2",
        "-movflags", "+faststart", str(out),
    ]
    _run(cmd)
    return out


def ensure_telegram_size(path: Path, mb: int | None = None) -> Path:
    """Если файл больше лимита Telegram, пережимает под mb МБ, подбирая CRF.
    Возвращает тот же путь (перезаписанный)."""
    mb = mb or cfg.TELEGRAM_MAX_MB
    path = Path(path)
    if path.stat().st_size <= mb * 1048576:
        return path
    tmp = path.with_name(path.stem + "__fit.mp4")
    for crf in (26, 28, 30, 32, 34):
        _run([cfg.FFMPEG, "-y", "-i", str(path), "-c:v", "libx264", "-crf", str(crf),
              "-preset", "fast", "-c:a", "aac", "-b:a", "160k",
              "-movflags", "+faststart", str(tmp)])
        if tmp.stat().st_size <= mb * 1048576:
            break
    tmp.replace(path)
    return path


def uniquify_file(src: Path, out_dir: Path, base_name: str, count: int,
                  geometry: bool | None = None) -> list[Path]:
    """Готовое видео → count уникальных версий. При NORMALIZE_INPUT нормализует
    вход к W×H (стабильные метаданные и размер), затем делает N проходов."""
    work = cfg.WORK_DIR / base_name
    work.mkdir(parents=True, exist_ok=True)
    source = normalize(Path(src), work / "src.mp4") if cfg.NORMALIZE_INPUT else Path(src)
    outs: list[Path] = []
    for i in range(count):
        out = Path(out_dir) / f"{base_name}_{i + 1}.mp4"
        uniquify_once(source, out, geometry=geometry)
        outs.append(ensure_telegram_size(out))
    return outs
