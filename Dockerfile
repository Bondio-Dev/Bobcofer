FROM python:3.11-bullseye

# ────────────────────────
# Базовые переменные окружения
# ────────────────────────
ENV DEBIAN_FRONTEND=noninteractive
ENV DISPLAY=:99
ENV PATH="/usr/local/bin:/usr/bin:/bin:${PATH}"
ENV BROWSER="google-chrome"

WORKDIR /app

# ────────────────────────
# 1. Системные пакеты и Google Chrome
# ────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl wget gnupg gcc libsqlite3-dev \
        xvfb x11vnc fluxbox \
        x11-utils xauth procps net-tools \
        fonts-liberation libxss1 libcanberra-gtk3-0 \
        libgl1-mesa-dri libgl1-mesa-glx libpango1.0-0 \
        libpulse0 libv4l-0 fonts-symbola && \
    curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | apt-key add - && \
    echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" \
        > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && apt-get install -y --no-install-recommends google-chrome-stable && \
    rm -rf /var/lib/apt/lists/*

# ────────────────────────
# 2. Обёртки Chrome с --no-sandbox для всех возможных вызовов
# ────────────────────────
RUN printf '#!/usr/bin/env bash\nexec /usr/bin/google-chrome-stable --no-sandbox --disable-gpu "$@"\n' \
      > /usr/local/bin/google-chrome-stable && \
    chmod +x /usr/local/bin/google-chrome-stable

# Создаём символическую ссылку google-chrome → google-chrome-stable
RUN ln -sf /usr/local/bin/google-chrome-stable /usr/local/bin/google-chrome

# Дополнительная обёртка для chromium-browser (если нужно)
RUN ln -sf /usr/local/bin/google-chrome-stable /usr/local/bin/chromium-browser

# ────────────────────────
# 3. Копируем скрипты и делаем их исполняемыми
# ────────────────────────
COPY setup_x11_config.sh /usr/local/bin/setup_x11_config.sh
COPY start.sh            /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/setup_x11_config.sh /usr/local/bin/start.sh

# ────────────────────────
# 4. Копируем исходники проекта
# ────────────────────────
COPY . /app

# ────────────────────────
# 5. Python-зависимости
# ────────────────────────
RUN pip install --no-cache-dir -r /app/requirements.txt

# ────────────────────────
# 6. VNC-пароль
# ────────────────────────
RUN mkdir -p /root/.vnc && \
    x11vnc -storepasswd 12345 /root/.vnc/passwd && \
    chmod 600 /root/.vnc/passwd

# ────────────────────────
# 7. Точка входа
# ────────────────────────
CMD ["/usr/local/bin/start.sh"]
