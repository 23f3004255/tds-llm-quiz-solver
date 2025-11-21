# ---- Base image ----
FROM python:3.10-slim

# ---- Install system dependencies for Playwright ----
RUN apt-get update && apt-get install -y \
    wget gnupg ca-certificates libnss3 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 \
    libgbm1 libasound2 libpangocairo-1.0-0 libpango-1.0-0 libcairo2 \
    libatspi2.0-0 libxfixes3 libxext6 libxshmfence1 libgl1 libgles2 \
    && rm -rf /var/lib/apt/lists/*

# ---- Create a non-root user ----
RUN useradd -m appuser
USER appuser
WORKDIR /home/appuser

# ---- Copy project files ----
COPY --chown=appuser:appuser . .

# ---- Install Python dependencies ----
# (Playwright must be installed AFTER requirements)
RUN pip install --no-cache-dir -r requirements.txt

# ---- Install Playwright browsers (Chromium only for smaller size) ----
RUN playwright install chromium

# ---- Expose API port (HuggingFace uses 7860) ----
EXPOSE 7860

# ---- Start FastAPI ----
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
