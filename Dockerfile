FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY cv_parser ./cv_parser
CMD ["sh", "-c", "uvicorn cv_parser.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
