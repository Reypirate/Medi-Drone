FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Copy common utilities module
COPY ../common /app/common
COPY . .
CMD ["python", "order.py"]
