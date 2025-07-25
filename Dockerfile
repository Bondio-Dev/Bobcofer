# Используем полный образ Debian (а не slim) — в нем есть все основные репозитории
FROM python:3.11-bullseye

WORKDIR /app

# Дополняем system-пакетами для Chrome, Xvfb, x11vnc, fluxbox и зависимостям
RUN apt-get update && apt-get install --no-install-recommends -y \
    gcc libsqlite3-dev wget \
    xvfb x11vnc \
    libappindicator1 fonts-liberation libxss1 libindicator7 \
    libcanberra-gtk3-0 libgl1-mesa-dri libgl1-mesa-glx libpango1.0-0 \
    libpulse0 libv4l-0 fonts-symbola \
    && wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && dpkg -i google-chrome-stable_current_amd64.deb || apt-get install -fy \
    && rm -f google-chrome-stable_current_amd64.deb \
    && rm -rf /var/lib/apt/lists/*

# Копируем приложение
COPY . .

# Устанавливаем Python-зависимости
RUN pip install --no-cache-dir -r requarements.txt

# Создаем VNC-пароль (пароль '12345' — замените на свой!)
# (Здесь x11vnc гарантированно установлен)
RUN mkdir -p /root/.vnc \
    && x11vnc -storepasswd 12345 /root/.vnc/passwd

# Запуск виртуального X-сервера, fluxbox, VNC и бота
CMD Xvfb :99 -screen 0 1920x1080x24 & \
    fluxbox & \
    x11vnc -display :99 -forever -nopw -rfbauth /root/.vnc/passwd -bg -rfbport 5900 & \
    export DISPLAY=:99 && python tgbot.py
