FROM python:3.11-slim

# Переменные окружения для подключения к хостовому дисплею
ENV DEBIAN_FRONTEND=noninteractive
ENV DISPLAY=:0
ENV BROWSER=google-chrome

WORKDIR /app
# Копируем исходники проекта
COPY . /app

# Устанавливаем Python-зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Простой скрипт запуска
CMD ["python", "/app/tgbot.py"]
