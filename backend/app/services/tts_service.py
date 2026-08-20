from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from pathlib import Path

import edge_tts


async def synthesize(text: str, config: dict[str, str], output: Path) -> tuple[Path, float]:
    """Create a local audition clip; configured audio models are reserved for voice design."""
    text = text.strip()
    if not text:
        raise ValueError("TTS text is required")
    output.parent.mkdir(parents=True, exist_ok=True)
    if config["provider"] == "edge":
        try:
            await edge_tts.Communicate(text, config["model"] or "zh-CN-XiaoxiaoNeural").save(str(output))
        except Exception:
            output = output.with_suffix(".wav")
            await asyncio.to_thread(_system_tts, text, "Tingting", output)
    elif config["provider"] == "system":
        await asyncio.to_thread(_system_tts, text, config["model"], output)
    else:
        raise ValueError("voice audition only supports local TTS")
    return output, _duration(output, len(text) / 4.5)


def _duration(path: Path, fallback: float) -> float:
    if ffprobe := shutil.which("ffprobe"):
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
            check=False,
            capture_output=True,
            text=True,
        )
        try:
            return max(1.0, float(json.loads(result.stdout)["format"]["duration"]))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            pass
    return max(1.0, fallback)


def _system_tts(text: str, voice: str, output: Path) -> None:
    if say := shutil.which("say"):
        subprocess.run(
            [say, "-v", voice or "Tingting", "--data-format=LEI16@22050", "-o", str(output), text],
            check=True,
            capture_output=True,
        )
        return
    if espeak := shutil.which("espeak-ng") or shutil.which("espeak"):
        command = [espeak, "-w", str(output), "-v", "zh" if not voice or voice == "Tingting" else voice]
        subprocess.run([*command, text], check=True, capture_output=True)
        return
    raise RuntimeError("local TTS requires macOS say or espeak-ng")
