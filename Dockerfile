FROM python:3.11-bullseye

ENV DEBIAN_FRONTEND=noninteractive
ENV DISPLAY=:99

WORKDIR /app

# Установка всех зависимостей
RUN apt-get update && apt-get install --no-install-recommends -y \
    curl wget gnupg gcc libsqlite3-dev \
    xvfb x11vnc fluxbox \
    x11-utils xauth procps net-tools \
    fonts-liberation libxss1 libcanberra-gtk3-0 \
    libgl1-mesa-dri libgl1-mesa-glx libpango1.0-0 \
    libpulse0 libv4l-0 fonts-symbola \
  && curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
  && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" \
         > /etc/apt/sources.list.d/google-chrome.list \
  && apt-get update && apt-get install --no-install-recommends -y \
      google-chrome-stable \
  && rm -rf /var/lib/apt/lists/*

# Копирование проекта
COPY . /app

# Установка Python зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Настройка VNC
RUN mkdir -p /root/.vnc && \
    x11vnc -storepasswd 12345 /root/.vnc/passwd && \
    chmod 600 /root/.vnc/passwd

# Конфигурация fluxbox
RUN mkdir -p /root/.fluxbox && \
    echo "session.screen0.workspaces: 1" > /root/.fluxbox/init

# Улучшенный скрипт запуска с диагностикой
RUN echo '#!/bin/bash\n\
set -e\n\
cleanup() {\n\
    echo "Cleaning up processes..."\n\
    pkill -f "Xvfb|x11vnc|fluxbox" 2>/dev/null || true\n\
    rm -f /tmp/.X*-lock /tmp/.X11-unix/X* 2>/dev/null || true\n\
}\n\
\n\
trap cleanup EXIT\n\
cleanup\n\
\n\
echo "=== Starting Xvfb ==="\n\
Xvfb :99 -screen 0 1920x1080x24 -ac +extension GLX +extension RANDR +extension RENDER &\n\
XVFB_PID=$!\n\
export DISPLAY=:99\n\
\n\
# Ждем готовности Xvfb\n\
for i in {1..10}; do\n\
    if xdpyinfo >/dev/null 2>&1; then\n\
        echo "Xvfb ready after $i attempts"\n\
        break\n\
    fi\n\
    echo "Waiting for Xvfb... attempt $i"\n\
    sleep 1\n\
done\n\
\n\
if ! xdpyinfo >/dev/null 2>&1; then\n\
    echo "ERROR: Xvfb failed to start properly"\n\
    exit 1\n\
fi\n\
\n\
echo "=== Starting fluxbox ==="\n\
fluxbox &\n\
sleep 2\n\
\n\
echo "=== Starting x11vnc ==="\n\
x11vnc -display :99 -forever -shared -noxdamage \\\n\
       -rfbauth /root/.vnc/passwd -rfbport 5900 -listen 0.0.0.0 \\\n\
       -bg -o /tmp/x11vnc.log &\n\
\n\
# Проверка запуска VNC\n\
sleep 3\n\
if netstat -tuln | grep :5900 >/dev/null; then\n\
    echo "VNC server started successfully on port 5900"\n\
else\n\
    echo "ERROR: VNC server failed to start"\n\
    cat /tmp/x11vnc.log 2>/dev/null || echo "No VNC log available"\n\
    exit 1\n\
fi\n\
\n\
echo "=== All services ready, starting bot ==="\n\
python /app/tgbot.py\n' > /start.sh && chmod +x /start.sh

CMD ["/start.sh"]
