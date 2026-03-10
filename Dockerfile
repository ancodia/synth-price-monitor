FROM python:3.11-slim

# Copy uv binary from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# System dependencies required by Playwright's Chromium
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libwayland-client0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (layer cached unless pyproject.toml / uv.lock changes)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Install Playwright Chromium browser
RUN uv run playwright install chromium

# Copy application code
COPY src/ ./src/
COPY dashboard/ ./dashboard/

# Ensure logs directory exists
RUN mkdir -p logs

# Health check: verify the database connection works
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD uv run python -c "import sqlite3; sqlite3.connect('price_monitor.db').close()"

# Default command: run the Streamlit dashboard
CMD ["uv", "run", "streamlit", "run", "dashboard/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
