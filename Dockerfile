FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8789 \
    DATA_DIR=data

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY *.py ./
COPY providers ./providers
COPY subtitles ./subtitles
COPY public ./public
COPY config.example.env ./config.example.env

VOLUME ["/app/data"]
EXPOSE 8789

CMD ["python", "app.py"]
