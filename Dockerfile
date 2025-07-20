# Use official slim Python image for smaller footprint
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (if any)
RUN apt-get update \
    && apt-get install --no-install-recommends -y gcc libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy application files
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requarements.txt

# Expose port if your bot serves a webhook or web endpoint (optional)
# EXPOSE 8443

# Default command to run the Telegram bot
CMD ["python", "tgbot.py"]
