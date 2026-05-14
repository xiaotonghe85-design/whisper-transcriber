from __future__ import annotations

import os
import re
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file, url_for
from werkzeug.utils import secure_filename

try:
    import imageio_ffmpeg
except ImportError:  # pragma: no cover - handled at runtime in the UI
    imageio_ffmpeg = None

try:
    import whisper
except ImportError:  # pragma: no cover - handled at runtime in the UI
    whisper = None


BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
BIN_DIR = BASE_DIR / ".bin"
ALLOWED_EXTENSIONS = {"mp3", "m4a", "wav"}
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "100"))

UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
BIN_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024
_cached_model = None


def configure_ffmpeg_path() -> None:
    if imageio_ffmpeg is None:
        return
    ffmpeg_source = Path(imageio_ffmpeg.get_ffmpeg_exe())
    ffmpeg_target = BIN_DIR / "ffmpeg"
    if not ffmpeg_target.exists():
        ffmpeg_target.symlink_to(ffmpeg_source)
    ffmpeg_dir = str(ffmpeg_target.parent)
    current_path = os.environ.get("PATH", "")
    if ffmpeg_dir not in current_path.split(os.pathsep):
        os.environ["PATH"] = os.pathsep.join([ffmpeg_dir, current_path]) if current_path else ffmpeg_dir


configure_ffmpeg_path()


def supported_formats() -> str:
    return ", ".join(f".{ext}" for ext in sorted(ALLOWED_EXTENSIONS))


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def slugify_filename(name: str) -> str:
    cleaned = re.sub(r"[^\w\-.]+", "_", name).strip("._")
    return cleaned or "transcript"


def get_model():
    global _cached_model
    if whisper is None:
        raise RuntimeError(
            "Whisper is not installed. Run `pip install -r requirements.txt` first."
        )
    if _cached_model is None:
        _cached_model = whisper.load_model(WHISPER_MODEL)
    return _cached_model


def render_home(**context):
    return render_template(
        "index.html",
        model_name=WHISPER_MODEL,
        supported_formats=supported_formats(),
        max_upload_mb=MAX_UPLOAD_MB,
        **context,
    )


@app.get("/")
def index():
    return render_home()


@app.get("/health")
def health():
    return jsonify(
        {
            "status": "ok",
            "model": WHISPER_MODEL,
            "max_upload_mb": MAX_UPLOAD_MB,
            "supported_formats": sorted(ALLOWED_EXTENSIONS),
        }
    )


@app.post("/transcribe")
def transcribe_audio():
    uploaded = request.files.get("audio")
    if uploaded is None or uploaded.filename == "":
        return render_home(
            error=f"请选择一个音频文件后再开始转写，支持 {supported_formats()}。",
        )

    if not allowed_file(uploaded.filename):
        return render_home(
            error=f"目前只支持上传 {supported_formats()} 文件。",
        )

    original_name = secure_filename(uploaded.filename)
    file_stem = Path(original_name).stem
    upload_name = f"{uuid.uuid4().hex}_{original_name}"
    upload_path = UPLOAD_DIR / upload_name
    uploaded.save(upload_path)

    try:
        model = get_model()
        result = model.transcribe(str(upload_path), fp16=False)
        transcript = (result.get("text") or "").strip()

        if not transcript:
            raise RuntimeError("Whisper 没有返回可用文本，请换一个文件再试。")

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        txt_name = f"{slugify_filename(file_stem)}-{timestamp}.txt"
        txt_path = OUTPUT_DIR / txt_name
        txt_path.write_text(transcript, encoding="utf-8")
    except Exception as exc:  # pragma: no cover - depends on local runtime
        return render_home(
            error=f"转写失败：{exc}",
        )
    finally:
        upload_path.unlink(missing_ok=True)

    return render_home(
        success="转写完成，可以直接复制结果或下载 TXT。",
        transcript=transcript,
        download_url=url_for("download_transcript", filename=txt_name),
        output_filename=txt_name,
    )


@app.get("/download/<path:filename>")
def download_transcript(filename: str):
    target = OUTPUT_DIR / filename
    if not target.exists():
        return render_home(
            error="找不到对应的 TXT 文件，请重新转写一次。",
        )
    return send_file(target, as_attachment=True, download_name=target.name)


@app.errorhandler(413)
def file_too_large(_error):
    return (
        render_home(error=f"文件太大了，当前最大支持 {MAX_UPLOAD_MB}MB。"),
        413,
    )


if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "").lower() in {"1", "true", "yes"}
    app.run(debug=debug, host=host, port=port)
