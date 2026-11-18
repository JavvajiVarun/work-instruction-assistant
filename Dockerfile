FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Pass the key at runtime: docker run -e ANTHROPIC_API_KEY=... -p 8000:8000 wia
EXPOSE 8000
CMD ["uvicorn", "wia.api:app", "--host", "0.0.0.0", "--port", "8000"]
