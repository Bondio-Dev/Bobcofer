FROM python:3.11-bullseye

ENV DEBIAN_FRONTEND=noninteractive
ENV DISPLAY=:99

WORKDIR /app

# 1) Системные зависимости, Xvfb, fluxbox, x11vnc, библиотеки для Chrome, шрифты и пр.
# 2) Добавляем репозиторий Google Chrome и сразу его устанавливаем
RUN apt-get update && apt-get install --no-install-recommends -y \
      curl wget gnupg gcc libsqlite3-dev \
      xvfb x11vnc fluxbox \
      fonts-liberation libxss1 libcanberra-gtk3-0 \
      libgl1-mesa-dri libgl1-mesa-glx libpango1.0-0 \
      libpulse0 libv4l-0 fonts-symbola \
  && curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
  && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" \
         > /etc/apt/sources.list.d/google-chrome.list \
  && apt-get update && apt-get install --no-install-recommends -y \
      google-chrome-stable \
  && rm -rf /var/lib/apt/lists/*

# Копируем весь проект в /app
COPY . /app

# Устанавливаем Python-библиотеки
RUN pip install --no-cache-dir -r requirements.txt

# Генерируем VNC-пароль (замените 12345 на свой)
RUN mkdir -p /root/.vnc \
 && x11vnc -storepasswd 12345 /root/.vnc/passwd

# Точка входа: запускаем Xvfb, fluxbox, x11vnc и ваш бот
CMD rm -f /tmp/.X*-lock /tmp/.X11-unix/X* && \
    Xvfb :99 -screen 0 1920x1080x24 -ac +extension GLX +extension RANDR +extension RENDER & \
    sleep 2 && \
    fluxbox & \
    sleep 1 && \
    x11vnc -display :99 -forever -rfbauth /root/.vnc/passwd -bg -rfbport 5900 -listen 0.0.0.0 && \
    python /app/tgbot.py
