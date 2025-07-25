# Используем официальный slim Python образ для компактности
FROM python:3.11-slim

# Рабочая директория
WORKDIR /app

# Установка необходимых системных пакетов, включая зависимости для Chrome, Xvfb и x11vnc
RUN apt-get update && apt-get install --no-install-recommends -y \
    gcc libsqlite3-dev \
    wget xvfb x11vnc \
    libappindicator1 fonts-liberation libxss1 libindicator7 \
    libcanberra-gtk3-0 libgl1-mesa-dri libgl1-mesa-glx libpango1.0-0 \
    libpulse0 libv4l-0 fonts-symbola \
    --fix-missing && \
    # Установка Google Chrome
    wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && \
    dpkg -i google-chrome-stable_current_amd64.deb || apt-get install -fy && \
    rm -f google-chrome-stable_current_amd64.deb && \
    rm -rf /var/lib/apt/lists/*

# Копирование файлов приложения внутрь контейнера
COPY . .

# Установка Python-зависимостей
RUN pip install --no-cache-dir -r requarements.txt

# (При необходимости) открываем порт VNC или иные сервисные порты
# EXPOSE 5900 # для VNC
# EXPOSE 8443 # если нужен webhook

# Пример запуска: сначала Xvfb (виртуальный дисплей), затем ваш скрипт
CMD ["sh", "-c", "Xvfb :99 -screen 0 1920x1080x24 & export DISPLAY=:99 && python tgbot.py"]
