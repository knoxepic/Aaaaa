FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py downloader.py ./
COPY templates/ templates/
COPY static/ static/

ENV PORT=7860
EXPOSE 7860

CMD ["gunicorn", "-w", "2", "-t", "600", "--bind", "0.0.0.0:7860", "app:app"]
