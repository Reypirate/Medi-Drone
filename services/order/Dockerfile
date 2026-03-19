FROM python:3.11-slim
WORKDIR /app
# Install curl for health checks
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY order/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Copy common utilities module
COPY common /app/common
COPY order/ .
CMD ["python", "order.py"]
