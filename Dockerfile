FROM python:3.11-bullseye

ENV DEBIAN_FRONTEND=noninteractive
ENV DISPLAY=:99

WORKDIR /app

# Устанавливаем все зависимости, включая x11-utils для xmessage
RUN apt-get update && apt-get install --no-install-recommends -y \
      curl wget gnupg gcc libsqlite3-dev \
      xvfb x11vnc fluxbox \
      x11-utils xauth \
      fonts-liberation libxss1 libcanberra-gtk3-0 \
      libgl1-mesa-dri libgl1-mesa-glx libpango1.0-0 \
      libpulse0 libv4l-0 fonts-symbola \
  && curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
  && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" \
         > /etc/apt/sources.list.d/google-chrome.list \
  && apt-get update && apt-get install --no-install-recommends -y \
      google-chrome-stable \
  && rm -rf /var/lib/apt/lists/*

# Создаем минимальную конфигурацию fluxbox
RUN mkdir -p /root/.fluxbox && \
    echo "session.screen0.workspaces: 1" > /root/.fluxbox/init && \
    echo "session.screen0.toolbar.visible: false" >> /root/.fluxbox/init && \
    echo "session.screen0.slit.autoHide: true" >> /root/.fluxbox/init

COPY . /app

RUN pip install --no-cache-dir -r requirements.txt

RUN mkdir -p /root/.vnc && \
    x11vnc -storepasswd 12345 /root/.vnc/passwd

# Создаем скрипт запуска с логированием
RUN echo '#!/bin/bash\n\
set -e\n\
echo "=== Cleaning old X locks ==="\n\
rm -f /tmp/.X*-lock /tmp/.X11-unix/X*\n\
echo "=== Starting Xvfb ==="\n\
Xvfb :99 -screen 0 1920x1080x24 -ac +extension GLX +extension RANDR +extension RENDER &\n\
XVFB_PID=$!\n\
sleep 3\n\
echo "=== Starting fluxbox ==="\n\
fluxbox 2>/dev/null &\n\
FLUXBOX_PID=$!\n\
sleep 2\n\
echo "=== Starting x11vnc ==="\n\
x11vnc -display :99 -forever -rfbauth /root/.vnc/passwd -bg -rfbport 5900 -listen 0.0.0.0 -o /tmp/x11vnc.log &\n\
VNC_PID=$!\n\
sleep 3\n\
echo "=== Checking if VNC is running ==="\n\
if ps -p $VNC_PID > /dev/null; then\n\
    echo "VNC server started successfully on port 5900"\n\
else\n\
    echo "Failed to start VNC server"\n\
    exit 1\n\
fi\n\
echo "=== Starting Python bot ==="\n\
python /app/tgbot.py\n' > /start.sh && chmod +x /start.sh

CMD ["/start.sh"]
