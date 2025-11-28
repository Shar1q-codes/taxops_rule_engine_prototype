FROM python:3.10-slim

# System dependencies for OCR and PDF parsing
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        tesseract-ocr \
        libtesseract-dev \
        poppler-utils && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy backend and core packages
COPY backend /app
COPY auditor_inference /app/auditor_inference
COPY auditor /app/auditor
COPY rule_engine /app/rule_engine
COPY corallo_taxops_rule_engine /app/corallo_taxops_rule_engine

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
