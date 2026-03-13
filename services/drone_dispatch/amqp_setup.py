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
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(host=RABBITMQ_HOST, port=RABBITMQ_PORT,
                                          heartbeat=300, blocked_connection_timeout=300)
            )
            print(f"  Connected to RabbitMQ at {RABBITMQ_HOST}:{RABBITMQ_PORT}")
            return connection
        except pika.exceptions.AMQPConnectionError:
            print(f"  Waiting for RabbitMQ... attempt {attempt + 1}/{max_retries}")
            time.sleep(delay)
    raise Exception("Could not connect to RabbitMQ after retries")


def setup_exchanges(channel):
    for exchange_name, exchange_type in EXCHANGES.items():
        channel.exchange_declare(exchange=exchange_name, exchange_type=exchange_type, durable=True)
        print(f"  Declared exchange: {exchange_name} ({exchange_type})")


def get_connection():
    connection = wait_for_rabbitmq()
    channel = connection.channel()
    setup_exchanges(channel)
    return connection, channel
