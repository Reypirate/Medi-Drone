FROM python:3.11-slim
WORKDIR /app
COPY order/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Copy common utilities module
COPY common /app/common
COPY order/ .
CMD ["python", "order.py"]
