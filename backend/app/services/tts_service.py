from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path

import httpx
import edge_tts
from mutagen import File as MutagenFile


async def synthesize(text: str, config: dict[str, str], output: Path) -> tuple[Path, float]:
    text = text.strip()
    if not text:
        raise ValueError("TTS text is required")
    provider = config["provider"]
    output.parent.mkdir(parents=True, exist_ok=True)
    if provider == "edge":
        try:
            await edge_tts.Communicate(text, config["model"] or "zh-CN-XiaoxiaoNeural").save(str(output))
        except Exception:
            output = output.with_suffix(".wav")
            await asyncio.to_thread(_system_tts, text, "Tingting", output)
    elif provider == "system":
        await asyncio.to_thread(_system_tts, text, config["model"], output)
    elif provider == "openai":
        await _openai_tts(text, config, output)
    else:
        raise ValueError("audio purpose only supports provider edge/system/openai")
    media = MutagenFile(output)
    duration = float(media.info.length) if media and media.info else len(text) / 4.5
    return output, max(1.0, duration)


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


async def _openai_tts(text: str, config: dict[str, str], output: Path) -> None:
    base_url = (config.get("baseUrl") or "https://api.openai.com/v1").rstrip("/")
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            f"{base_url}/audio/speech",
            headers={"Authorization": f"Bearer {config['apiKey']}"},
            json={"model": config["model"], "voice": "alloy", "input": text, "response_format": "wav"},
        )
        response.raise_for_status()
        output.write_bytes(response.content)
