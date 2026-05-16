FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

# Install Python deps first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium
RUN playwright install chromium --with-deps

# Copy source
COPY . .

# Expose dashboard port
EXPOSE 8000

# Start FastAPI dashboard
CMD ["python", "dashboard/app.py"]
