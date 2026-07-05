FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    fonts-liberation \
    fonts-dejavu-core \
    wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY video_builder.py .

RUN mkdir -p /app/music
RUN mkdir -p /tmp/swa_videos

EXPOSE 8080

CMD ["python", "video_builder.py"]
