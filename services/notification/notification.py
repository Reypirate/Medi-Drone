import os
import json
import threading
import pika
from flask import Flask, jsonify
from flask_cors import CORS
from twilio.rest import Client as TwilioClient
import amqp_setup

app = Flask(__name__)
CORS(app)

TWILIO_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM = os.environ.get("TWILIO_FROM_NUMBER", "")
TWILIO_TO = os.environ.get("TWILIO_TO_NUMBER", "")

notification_log = []


def send_sms(to_number, body):
    """Send SMS via Twilio REST API."""
    if not all([TWILIO_SID, TWILIO_TOKEN, TWILIO_FROM]):
        print(f"  [MOCK SMS] To: {to_number} | Body: {body}")
        notification_log.append({"to": to_number, "body": body, "status": "MOCK_SENT"})
        return {"status": "MOCK_SENT"}

    try:
        client = TwilioClient(TWILIO_SID, TWILIO_TOKEN)
        message = client.messages.create(to=to_number, from_=TWILIO_FROM, body=body)
        print(f"  [SMS SENT] SID: {message.sid} | To: {to_number}")
        notification_log.append({"to": to_number, "body": body, "sid": message.sid, "status": "SENT"})
        return {"sid": message.sid, "status": "queued"}
    except Exception as e:
        print(f"  [SMS ERROR] {str(e)}")
        notification_log.append({"to": to_number, "body": body, "status": "ERROR", "error": str(e)})
        return {"status": "ERROR", "error": str(e)}


def on_notification(channel, method, properties, body):
    """Callback for AMQP messages on the notifications exchange."""
    try:
        data = json.loads(body)
        print(f"  [NOTIFICATION] Received: {json.dumps(data, indent=2)}")

        message_body = data.get("message", "You have a new notification from Medi-Drone.")
        to_number = data.get("phone_number", TWILIO_TO)

        order_id = data.get("order_id", "N/A")
        event_type = data.get("event_type", "GENERAL")

        sms_body = f"[Medi-Drone | {event_type}] Order {order_id}: {message_body}"
        send_sms(to_number, sms_body)

        channel.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        print(f"  [NOTIFICATION ERROR] {str(e)}")
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def start_consumer():
    """Start the AMQP consumer in a background thread."""
    print(f"  [AMQP] Starting notification consumer...")
    connection, channel = amqp_setup.get_connection()

    queue_name = "notification_queue"
    print(f"  [AMQP] Declaring queue: {queue_name} (durable=True)")
    channel.queue_declare(queue=queue_name, durable=True)

    print(f"  [AMQP] Binding queue '{queue_name}' to exchange 'notifications' with routing key 'notify.sms'")
    channel.queue_bind(exchange="notifications", queue=queue_name, routing_key="notify.sms")

    print(f"  [AMQP] Binding queue '{queue_name}' to exchange 'orders' with routing key 'order.failed'")
    channel.queue_bind(exchange="orders", queue=queue_name, routing_key="order.failed")

    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=queue_name, on_message_callback=on_notification)

    print(f"  [AMQP] Listening for notification messages on queue '{queue_name}'...")
    channel.start_consuming()


@app.route("/notifications/log", methods=["GET"])
def get_log():
    return jsonify({"notifications": notification_log[-50:]})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "service": "notification"})


if __name__ == "__main__":
    consumer_thread = threading.Thread(target=start_consumer, daemon=True)
    consumer_thread.start()

    print("  Notification Service running on port 5004")
    app.run(host="0.0.0.0", port=5004, debug=True)
