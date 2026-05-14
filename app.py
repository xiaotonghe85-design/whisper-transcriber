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
    from openai import OpenAI
except ImportError:  # pragma: no cover - handled at runtime in the UI
    OpenAI = None

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
TRANSLATION_MODEL = os.getenv("OPENAI_TRANSLATION_MODEL", "gpt-4.1-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

SUPPORTED_LANGUAGE_OPTIONS = [
    ("auto", "自动检测"),
    ("ar", "阿拉伯语"),
    ("es", "西班牙语"),
    ("en", "英语"),
    ("ko", "韩语"),
    ("ja", "日语"),
    ("de", "德语"),
    ("th", "泰语"),
    ("fr", "法语"),
    ("zh", "中文"),
]

TRANSLATE_TO_CHINESE_LANGUAGES = {"ar", "es", "en", "ko", "ja", "de", "th", "fr"}

UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
BIN_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024
_cached_model = None
_cached_openai_client = None


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


def get_openai_client():
    global _cached_openai_client
    if not OPENAI_API_KEY:
        raise RuntimeError("尚未配置 OPENAI_API_KEY，暂时无法把外语结果翻译成中文。")
    if OpenAI is None:
        raise RuntimeError("OpenAI SDK 未安装，请先安装 requirements.txt 里的依赖。")
    if _cached_openai_client is None:
        _cached_openai_client = OpenAI(api_key=OPENAI_API_KEY)
    return _cached_openai_client


def should_translate_to_chinese(language_code: str) -> bool:
    return language_code in TRANSLATE_TO_CHINESE_LANGUAGES


def normalize_language(language_code: str) -> str | None:
    if language_code == "auto":
        return None
    return language_code


def translate_text_to_chinese(text: str, source_language_label: str) -> str:
    client = get_openai_client()
    response = client.responses.create(
        model=TRANSLATION_MODEL,
        input=[
            {
                "role": "system",
                "content": (
                    "You are a professional translator. Translate the user's transcript into natural, accurate Simplified Chinese. "
                    "Preserve names, numbers, structure, and meaning. Output only the final Chinese translation."
                ),
            },
            {
                "role": "user",
                "content": f"Source language: {source_language_label}\n\nTranscript:\n{text}",
            },
        ],
    )
    translated = (response.output_text or "").strip()
    if not translated:
        raise RuntimeError("翻译接口没有返回可用中文内容。")
    return translated


def get_language_label(language_code: str | None) -> str:
    for code, label in SUPPORTED_LANGUAGE_OPTIONS:
        if code == language_code:
            return label
    return "自动检测" if language_code is None else language_code


def render_home(**context):
    return render_template(
        "index.html",
        model_name=WHISPER_MODEL,
        supported_formats=supported_formats(),
        max_upload_mb=MAX_UPLOAD_MB,
        language_options=SUPPORTED_LANGUAGE_OPTIONS,
        translation_model=TRANSLATION_MODEL,
        has_openai_translation=bool(OPENAI_API_KEY),
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
            "translation_enabled": bool(OPENAI_API_KEY),
            "translation_model": TRANSLATION_MODEL if OPENAI_API_KEY else None,
            "target_language": "zh-CN",
        }
    )


@app.post("/transcribe")
def transcribe_audio():
    uploaded = request.files.get("audio")
    selected_language = request.form.get("language", "auto")
    if uploaded is None or uploaded.filename == "":
        return render_home(
            error=f"请选择一个音频文件后再开始转写，支持 {supported_formats()}。",
            selected_language=selected_language,
        )

    if not allowed_file(uploaded.filename):
        return render_home(
            error=f"目前只支持上传 {supported_formats()} 文件。",
            selected_language=selected_language,
        )

    original_name = secure_filename(uploaded.filename)
    file_stem = Path(original_name).stem
    upload_name = f"{uuid.uuid4().hex}_{original_name}"
    upload_path = UPLOAD_DIR / upload_name
    uploaded.save(upload_path)

    try:
        model = get_model()
        whisper_language = normalize_language(selected_language)
        result = model.transcribe(
            str(upload_path),
            fp16=False,
            language=whisper_language,
            task="transcribe",
        )
        transcript = (result.get("text") or "").strip()
        detected_language = (result.get("language") or selected_language or "auto").lower()

        if not transcript:
            raise RuntimeError("Whisper 没有返回可用文本，请换一个文件再试。")

        final_text = transcript
        translation_notice = None
        if should_translate_to_chinese(detected_language):
            final_text = translate_text_to_chinese(
                transcript,
                get_language_label(detected_language),
            )
            translation_notice = f"已将 {get_language_label(detected_language)} 转写结果翻译为中文。"

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        txt_name = f"{slugify_filename(file_stem)}-{timestamp}.txt"
        txt_path = OUTPUT_DIR / txt_name
        txt_path.write_text(final_text, encoding="utf-8")
    except Exception as exc:  # pragma: no cover - depends on local runtime
        return render_home(
            error=f"转写失败：{exc}",
            selected_language=selected_language,
        )
    finally:
        upload_path.unlink(missing_ok=True)

    return render_home(
        success="转写完成，可以直接复制结果或下载 TXT。",
        transcript=final_text,
        source_transcript=transcript,
        detected_language=get_language_label(detected_language),
        translation_notice=translation_notice,
        download_url=url_for("download_transcript", filename=txt_name),
        output_filename=txt_name,
        selected_language=selected_language,
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
