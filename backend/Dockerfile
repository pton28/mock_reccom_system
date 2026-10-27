FROM python:3.13-slim
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend backend
COPY data_generator data_generator
COPY pipeline pipeline
COPY recommendation recommendation
COPY configs configs
COPY scripts scripts
ENV PYTHONUNBUFFERED=1 NUTEE_DATA_DIR=/app/data
EXPOSE 8000
CMD ["python", "-m", "scripts.start"]
