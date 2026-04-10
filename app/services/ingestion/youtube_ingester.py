from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from app.models.schemas import IngestedContent

log = logging.getLogger(__name__)


def _is_playlist(url: str) -> bool:
    return "playlist" in url or "list=" in url


def _download_audio(url: str, output_dir: Path) -> list[tuple[str, str]]:
    try:
        import yt_dlp
    except ImportError as exc:
        raise ImportError(
            "yt-dlp is required for YouTube ingestion. Install: pip install yt-dlp"
        ) from exc

    results: list[tuple[str, str]] = []
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(output_dir / "%(id)s.%(ext)s"),
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "128"}
        ],
        "quiet": True,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        entries = info.get("entries", [info]) if "entries" in info else [info]
        for entry in entries:
            video_id = entry.get("id", "unknown")
            title = entry.get("title", video_id)
            audio_path = output_dir / f"{video_id}.mp3"
            if audio_path.exists():
                results.append((str(audio_path), title))

    return results


def _transcribe(audio_path: str) -> str:
    try:
        import whisper
    except ImportError as exc:
        raise ImportError(
            "openai-whisper is required for transcription. Install: pip install openai-whisper"
        ) from exc

    model = whisper.load_model("base")
    return model.transcribe(audio_path, fp16=False)["text"]


def ingest_youtube(url: str, title: str | None = None) -> IngestedContent:
    is_playlist = _is_playlist(url)
    source_type = "youtube_playlist" if is_playlist else "youtube_video"

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        try:
            audio_files = _download_audio(url, tmp_path)
        except Exception as exc:
            raise RuntimeError(f"Failed to download audio from {url}: {exc}") from exc

        if not audio_files:
            raise RuntimeError(f"No audio tracks downloaded from: {url}")

        transcripts: list[str] = []
        inferred_title: str | None = title

        for audio_path, video_title in audio_files:
            if not inferred_title:
                inferred_title = video_title
            try:
                transcript = _transcribe(audio_path)
                transcripts.append(f"[{video_title}]\n{transcript}")
                log.info("Transcribed: %s", video_title)
            except Exception as exc:
                log.warning("Transcription failed for %s: %s", video_title, exc)

    if not transcripts:
        raise RuntimeError("All transcriptions failed.")

    return IngestedContent(
        source_type=source_type,
        source_ref=url,
        title=inferred_title or "YouTube Content",
        full_text="\n\n".join(transcripts),
    )
