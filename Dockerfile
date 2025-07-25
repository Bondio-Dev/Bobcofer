FROM python:3.11-bullseye

ENV DEBIAN_FRONTEND=noninteractive
ENV DISPLAY=:99

WORKDIR /app

# --- Системные пакеты и Google Chrome ---------------------------------------
RUN apt-get update && apt-get install --no-install-recommends -y \
    curl wget gnupg gcc libsqlite3-dev \
    xvfb x11vnc fluxbox x11-utils xauth \
    fonts-liberation libxss1 libcanberra-gtk3-0 \
    libgl1-mesa-dri libgl1-mesa-glx libpango1.0-0 \
    libpulse0 libv4l-0 fonts-symbola \
 && curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
 && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" \
       > /etc/apt/sources.list.d/google-chrome.list \
 && apt-get update && apt-get install --no-install-recommends -y \
       google-chrome-stable \
 && rm -rf /var/lib/apt/lists/*

# --- Fluxbox минимальная конфигурация ---------------------------------------
RUN mkdir -p /root/.fluxbox && \
    echo 'session.screen0.workspaces: 1'          > /root/.fluxbox/init && \
    echo 'session.screen0.toolbar.visible: false' >> /root/.fluxbox/init

# --- Проект ------------------------------------------------------------------
COPY . /app
RUN pip install --no-cache-dir -r requirements.txt

# --- VNC-пароль --------------------------------------------------------------
RUN mkdir -p /root/.vnc && \
    x11vnc -storepasswd 12345 /root/.vnc/passwd && \
    chmod 600 /root/.vnc/passwd

# --- Стартовый скрипт --------------------------------------------------------
RUN printf '#!/bin/bash\n\
set -e\n\
rm -f /tmp/.X*-lock /tmp/.X11-unix/X*\n\
echo \"[start] Xvfb\"\n\
Xvfb :99 -screen 0 1920x1080x24 -ac &\n\
sleep 2\n\
export DISPLAY=:99\n\
echo \"[start] fluxbox\"\n\
fluxbox &\n\
sleep 1\n\
echo \"[start] x11vnc\"\n\
x11vnc -display :99 -forever -shared \\\n\
       -noxdamage -rfbauth /root/.vnc/passwd \\\n\
       -rfbport 5900 -listen 0.0.0.0 -bg &\n\
sleep 1\n\
echo \"[start] python bot\"\n\
python /app/tgbot.py\n' > /start.sh && chmod +x /start.sh

CMD ["/start.sh"]
