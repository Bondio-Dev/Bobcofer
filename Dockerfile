FROM python:3.11-slim

# Установка зависимостей для X11 и Tkinter
RUN apt-get update && apt-get install -y \
    xauth \
    xvfb \
    libxtst6 \
    libxrandr2 \
    libasound2 \
    libpangocairo-1.0-0 \
    libatk1.0-0 \
    libgtk-3-0 \
    libgdk-pixbuf2.0-0 \
    python3-tk \  
    python3-dev \
  && rm -rf /var/lib/apt/lists/*

# Переменные окружения
ENV DEBIAN_FRONTEND=noninteractive
ENV DISPLAY=:0
ENV BROWSER=google-chrome

WORKDIR /app
COPY . /app

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "/app/tgbot.py"]
