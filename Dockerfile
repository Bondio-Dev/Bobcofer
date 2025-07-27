FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV DISPLAY=:0
ENV BROWSER=google-chrome
ENV PATH="/usr/local/bin:/usr/bin:/bin:${PATH}"

WORKDIR /app

# ───── 1. Системные пакеты (минимум) ─────
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl wget gnupg ca-certificates \
        libxss1 libnss3 libatk-bridge2.0-0 libdrm2 libxdamage1 \
        libgbm1 libu2f-udev libasound2 xdg-utils && \
    rm -rf /var/lib/apt/lists/*

# ───── 2. Установка Google Chrome ─────
RUN curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | apt-key add - && \
    md64] http://dl.google.com/linux/chrome/deb/ stable main" \
      > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && apt-get install -y --no-install-recommends google-chrome-stable && \
    rm -rf /var/lib/apt/lists/*

# ───── 3. Обёртки с --no-sandbox ─────
RUN printf '#!/usr/bin/env bash\nexec /usr/bin/google-chrome-stable \
           --no-sandbox --disable-gpu "$@"\n' \
           > /usr/local/bin/google-chrome-stable && \
    chmod +x /usr/local/bin/google-chrome-stable && \
    ln -sf /usr/local/bin/google-chrome-stable /usr/local/bin/google-chrome && \
    ln -sf /usr/local/bin/google-chrome-stable /usr/local/bin/chromium-browser

# ───── 4. Исходники проекта ─────
COPY . /app

# ───── 5. Python-зависимости ─────
RUN pip install --no-cache-dir -r requirements.txt

# ───── 6. Стартовый скрипт ─────
RUN printf '#!/usr/bin/env bash\nexec python /app/tgbot.py\n' \
    > /usr/local/bin/entrypoint.sh && chmod +x /usr/local/bin/entrypoint.sh

CMD ["/usr/local/bin/entrypoint.sh"]
