FROM python:3.11-slim

WORKDIR /app

# Устанавливаем системные зависимости, Chrome, Xvfb и x11vnc
RUN apt-get update && apt-get install --no-install-recommends -y \
    gcc libsqlite3-dev wget \
    xvfb x11vnc fluxbox \
    libappindicator1 fonts-liberation libxss1 libindicator7 \
    libcanberra-gtk3-0 libgl1-mesa-dri libgl1-mesa-glx libpango1.0-0 \
    libpulse0 libv4l-0 fonts-symbola \
    && wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && dpkg -i google-chrome-stable_current_amd64.deb || apt-get install -fy \
    && rm -f google-chrome-stable_current_amd64.deb \
    && rm -rf /var/lib/apt/lists/*

COPY . .

RUN pip install --no-cache-dir -r requarements.txt

# Создаём VNC пароль (замените '12345' на свой безопасный)
RUN mkdir /root/.vnc \
    && x11vnc -storepasswd 12345 /root/.vnc/passwd

# По умолчанию запускаем всё нужное в фоне и ваш бот
CMD Xvfb :99 -screen 0 1920x1080x24 & \
    fluxbox & \
    x11vnc -display :99 -forever -nopw -rfbauth /root/.vnc/passwd -bg -rfbport 5900 & \
    export DISPLAY=:99 && python tgbot.py
