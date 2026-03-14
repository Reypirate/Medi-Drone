import os
import time
import pika

RABBITMQ_HOST = os.environ.get("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_PORT = int(os.environ.get("RABBITMQ_PORT", 5672))

EXCHANGES = {
    "orders": "topic",
    "notifications": "topic",
}


def wait_for_rabbitmq(max_retries=12, delay=5):
    for attempt in range(max_retries):
        try:
            print(f"  [AMQP] Attempting connection to {RABBITMQ_HOST}:{RABBITMQ_PORT} (attempt {attempt + 1}/{max_retries})...")
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(host=RABBITMQ_HOST, port=RABBITMQ_PORT,
                                          heartbeat=300, blocked_connection_timeout=300)
            )
            print(f"  [AMQP] Connected successfully to {RABBITMQ_HOST}:{RABBITMQ_PORT}")
            return connection
        except pika.exceptions.AMQPConnectionError as e:
            print(f"  [AMQP] Connection failed: {e} - retrying in {delay}s...")
            time.sleep(delay)
    raise Exception("Could not connect to RabbitMQ after retries")


def setup_exchanges(channel):
    for exchange_name, exchange_type in EXCHANGES.items():
        try:
            channel.exchange_declare(exchange=exchange_name, exchange_type=exchange_type, durable=True)
            print(f"  [AMQP] Declared exchange: {exchange_name} ({exchange_type})")
        except Exception as e:
            print(f"  [AMQP] Failed to declare exchange {exchange_name}: {e}")
            raise


def get_connection():
    print(f"  [AMQP] Initializing AMQP connection...")
    connection = wait_for_rabbitmq()
    channel = connection.channel()
    setup_exchanges(channel)
    print(f"  [AMQP] AMQP initialization complete - channel and exchanges ready")
    return connection, channel
