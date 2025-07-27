FROM python:3.11-slim

# Переменные окружения для подключения к хостовому дисплею
ENV DEBIAN_FRONTEND=noninteractive
ENV DISPLAY=:0
ENV BROWSER=google-chrome

WORKDIR /app

# Устанавливаем только необходимые библиотеки для работы с X11
RUN apt-get update && apt-get install -y --no-install-recommends \
        libx11-6 libxext6 libxrender1 libxtst6 libxi6 \
        libglib2.0-0 libgtk-3-0 libgdk-pixbuf2.0-0 \
        libxss1 libnss3 libxcomposite1 libxdamage1 \
        libxrandr2 libasound2 libpangocairo-1.0-0 \
        libatk1.0-0 libcairo-gobject2 libgtk-3-0 \ \
    rm -rf /var/lib/apt/lists/*

# Копируем исходники проекта
COPY . /app

# Устанавливаем Python-зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Простой скрипт запуска
CMD ["python", "/app/tgbot.py"]
