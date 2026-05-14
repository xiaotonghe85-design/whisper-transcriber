FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    WHISPER_MODEL=base \
    MAX_UPLOAD_MB=100 \
    PORT=5000

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip "setuptools==80.9.0" wheel
RUN python -c "import setuptools, pkg_resources; print('setuptools', setuptools.__version__)"
RUN pip install Flask==3.0.3 gunicorn==23.0.0 imageio-ffmpeg==0.6.0
RUN pip install --no-build-isolation openai-whisper==20240930

COPY . .

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--timeout", "600", "app:app"]
