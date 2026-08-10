#!/usr/bin/env python3
"""Render a deterministic vertical social video from a validated JSON manifest."""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import tempfile
from datetime import date
from pathlib import Path


WIDTH = 1080
HEIGHT = 1920
FPS = 30
MIN_DURATION = 15.0
MAX_DURATION = 35.0
MAX_SCENES = 7


def fail(message: str) -> None:
    raise SystemExit(message)


def run(command: list[str]) -> None:
    completed = subprocess.run(command, text=True, capture_output=True)
    if completed.returncode:
        details = completed.stderr.strip()[-3000:]
        fail(f"command failed ({completed.returncode}): {details}")


def probe_video(ffprobe: str, path: Path) -> tuple[dict, float] | None:
    completed = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration:stream=codec_name,codec_type,width,height", "-of", "json", str(path)],
        text=True, capture_output=True,
    )
    if completed.returncode:
        return None
    try:
        metadata = json.loads(completed.stdout)
        return metadata, float(metadata["format"]["duration"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def ass_time(seconds: float) -> str:
    centiseconds = round(seconds * 100)
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    secs, cents = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cents:02d}"


def ass_text(value: str) -> str:
    value = value.replace("\\", r"\N").replace("{", "(").replace("}", ")")
    words = value.split()
    if len(words) <= 4:
        return " ".join(words)
    midpoint = math.ceil(len(words) / 2)
    return " ".join(words[:midpoint]) + r"\N" + " ".join(words[midpoint:])


def validate_manifest(raw: object, manifest_path: Path) -> dict:
    if not isinstance(raw, dict):
        fail("manifest must be a JSON object")
    required = ("tenant", "profile", "title", "caption", "hashtags", "scenes")
    missing = [key for key in required if not raw.get(key)]
    if missing:
        fail("missing manifest fields: " + ", ".join(missing))
    if raw["tenant"] not in {"viralbarato", "mundonoprato"}:
        fail("tenant must be viralbarato or mundonoprato")
    scenes = raw["scenes"]
    if not isinstance(scenes, list) or not 4 <= len(scenes) <= MAX_SCENES:
        fail(f"scenes must contain between 4 and {MAX_SCENES} items")
    total = 0.0
    for index, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            fail(f"scene {index} must be an object")
        text = str(scene.get("text", "")).strip()
        if not 3 <= len(text) <= 90:
            fail(f"scene {index} text must contain 3-90 characters")
        duration = float(scene.get("duration", 0))
        if not 1.5 <= duration <= 8:
            fail(f"scene {index} duration must be between 1.5 and 8 seconds")
        image = Path(str(scene.get("image", "")))
        if not image.is_absolute():
            image = (manifest_path.parent / image).resolve()
        if not image.is_file():
            fail(f"scene {index} image does not exist: {image}")
        scene["image"] = str(image)
        total += duration
    if not MIN_DURATION <= total <= MAX_DURATION:
        fail(f"total duration must be between {MIN_DURATION:g} and {MAX_DURATION:g} seconds")
    hashtags = raw["hashtags"]
    if not isinstance(hashtags, list) or not 3 <= len(hashtags) <= 8:
        fail("hashtags must contain between 3 and 8 items")
    return raw


def write_ass(path: Path, scenes: list[dict]) -> None:
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Main,DejaVu Sans,62,&H00FFFFFF,&H00FFFFFF,&H00111111,&H90000000,-1,0,0,0,100,100,0,0,3,4,0,2,100,190,350,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    elapsed = 0.0
    events = []
    for scene in scenes:
        end = elapsed + float(scene["duration"])
        events.append(
            f"Dialogue: 0,{ass_time(elapsed)},{ass_time(end)},Main,,0,0,0,,{ass_text(scene['text'])}"
        )
        elapsed = end
    path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")


def render(manifest: dict, output_dir: Path, force: bool) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        fail("ffmpeg and ffprobe are required")
    output_dir.mkdir(parents=True, exist_ok=True)
    video_path = output_dir / "video.mp4"
    if video_path.exists() and not force:
        existing = probe_video(ffprobe, video_path)
        if existing:
            metadata, duration = existing
            streams = metadata.get("streams", [])
            video = next((item for item in streams if item.get("codec_type") == "video"), {})
            audio = next((item for item in streams if item.get("codec_type") == "audio"), {})
            package_path = output_dir / "package.json"
            package_valid = False
            if package_path.is_file():
                try:
                    package_valid = json.loads(package_path.read_text(encoding="utf-8")).get("render", {}).get("validated") is True
                except (OSError, json.JSONDecodeError):
                    package_valid = False
            complete = (output_dir / "cover.jpg").is_file() and (output_dir / "publicacao.md").is_file() and package_valid
            if video.get("width") == WIDTH and video.get("height") == HEIGHT and audio and MIN_DURATION <= duration <= MAX_DURATION and complete:
                print(json.dumps({"status": "already_exists", "video": str(video_path)}))
                return video_path

    scenes = manifest["scenes"]
    captions_path = output_dir / "captions.ass"
    write_ass(captions_path, scenes)
    temporary_video = output_dir / ".video.rendering.mp4"
    total = sum(float(scene["duration"]) for scene in scenes)
    with tempfile.TemporaryDirectory(prefix="segments-", dir=output_dir) as temporary_dir_name:
        temporary_dir = Path(temporary_dir_name)
        segment_paths = []
        for index, scene in enumerate(scenes):
            segment_path = temporary_dir / f"scene-{index:02d}.mp4"
            segment_ass = temporary_dir / f"scene-{index:02d}.ass"
            write_ass(segment_ass, [scene])
            escaped_ass = str(segment_ass).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
            video_filter = (
                f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
                f"crop={WIDTH}:{HEIGHT},fps={FPS},trim=duration={scene['duration']},"
                f"setpts=PTS-STARTPTS,subtitles='{escaped_ass}',format=yuv420p"
            )
            run([
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-loop", "1", "-t", str(scene["duration"]), "-i", scene["image"],
                "-vf", video_filter, "-an", "-c:v", "libx264", "-preset", "veryfast",
                "-crf", "21", "-pix_fmt", "yuv420p", str(segment_path),
            ])
            segment_paths.append(segment_path)
        concat_path = temporary_dir / "concat.txt"
        concat_path.write_text(
            "".join(f"file '{str(path).replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'\n" for path in segment_paths),
            encoding="utf-8",
        )
        run([
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_path),
            "-f", "lavfi", "-t", str(total), "-i", "anullsrc=r=44100:cl=stereo",
            "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
            "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(temporary_video),
        ])
    probed = probe_video(ffprobe, temporary_video)
    if not probed:
        fail("render validation failed: ffprobe could not read the temporary video")
    metadata, duration = probed
    streams = metadata.get("streams", [])
    video = next((item for item in streams if item.get("codec_type") == "video"), {})
    audio = next((item for item in streams if item.get("codec_type") == "audio"), {})
    if video.get("width") != WIDTH or video.get("height") != HEIGHT or not audio:
        fail("render validation failed: expected 1080x1920 video with an audio stream")
    if abs(duration - total) > 0.25:
        fail("render validation failed: unexpected duration")
    temporary_video.replace(video_path)
    run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", "0.4",
        "-i", str(video_path), "-frames:v", "1", "-q:v", "2", str(output_dir / "cover.jpg"),
    ])
    package = dict(manifest)
    package["generated_on"] = date.today().isoformat()
    package["render"] = {"video": "video.mp4", "cover": "cover.jpg", "duration": duration, "validated": True}
    (output_dir / "package.json").write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    hashtags = " ".join("#" + re.sub(r"[^\w]", "", tag.lstrip("#"), flags=re.UNICODE) for tag in manifest["hashtags"])
    publication = f"""# {manifest['title']}

Status: pronto-para-publicacao

Perfil: `{manifest['profile']}`

## Legenda

{manifest['caption'].strip()}

## Hashtags

{hashtags}

## Arquivos

- Vídeo validado: `video.mp4`
- Capa: `cover.jpg`
- Manifesto e origem editorial: `package.json`

## Publicação

- Revisar o vídeo e a legenda antes de publicar.
- Adicionar no TikTok um áudio em tendência com volume baixo.
- Registrar a URL e as métricas de 24 h, 72 h e sete dias.
"""
    (output_dir / "publicacao.md").write_text(publication, encoding="utf-8")
    print(json.dumps({"status": "rendered", "video": str(video_path), "duration": duration}, ensure_ascii=False))
    return video_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    manifest_path = args.manifest.resolve()
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest = validate_manifest(raw, manifest_path)
    render(manifest, args.output_dir.resolve(), args.force)


if __name__ == "__main__":
    main()
