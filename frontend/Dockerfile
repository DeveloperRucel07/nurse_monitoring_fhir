FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY frontend ./frontend

EXPOSE 8501

CMD ["sh", "-c", "PYTHONPATH=/app streamlit run frontend/app.py --server.address 0.0.0.0 --server.port 8501"]
