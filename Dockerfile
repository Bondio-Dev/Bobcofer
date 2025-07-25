FROM python:3.11-bullseye

WORKDIR /app

# Обновляем пакеты и устанавливаем базовые зависимости
RUN apt-get update && apt-get install --no-install-recommends -y \
    gcc libsqlite3-dev wget curl gnupg \
    && rm -rf /var/lib/apt/lists/*

# Добавляем репозиторий Google Chrome и устанавливаем его отдельно
RUN curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update && apt-get install --no-install-recommends -y \
    google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем X11 и VNC пакеты (убраны libindicator7 и libappindicator1)
RUN apt-get update && apt-get install --no-install-recommends -y \
    xvfb x11vnc fluxbox \
    fonts-liberation libxss1 \
    libcanberra-gtk3-0 libgl1-mesa-dri libgl1-mesa-glx libpango1.0-0 \
    libpulse0 libv4l-0 fonts-symbola \
    && rm -rf /var/lib/apt/lists/*

# Копируем файлы проекта
COPY . .

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Настраиваем VNC
RUN mkdir -p /root/.vnc && \
    echo "12345" | x11vnc -storepasswd -stdin /root/.vnc/passwd

# Настраиваем точку входа
CMD Xvfb :99 -screen 0 1920x1080x24 & \
    fluxbox & \
    x11vnc -display :99 -forever -rfbauth /root/.vnc/passwd -bg -rfbport 5900 & \
    export DISPLAY=:99 && python tgbot.py
