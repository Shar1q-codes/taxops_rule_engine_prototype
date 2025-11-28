FROM python:3.10-slim

# System dependencies for OCR and PDF parsing
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        tesseract-ocr \
        libtesseract-dev \
        poppler-utils && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy full repository (includes backend, auditor_inference, etc.)
COPY . /app

# Install Python dependencies
RUN pip install --no-cache-dir -r backend/requirements.txt

WORKDIR /app/backend

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
