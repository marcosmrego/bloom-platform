FROM python:3.13-slim

WORKDIR /app
COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY api/ .

EXPOSE 8000
CMD ["python", "main.py"]
