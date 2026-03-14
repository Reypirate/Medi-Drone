"""
Request tracking utilities for Medi-Drone services.

This module provides functions to generate and track request IDs
for tracing requests across microservices.
"""

import uuid
import time
import threading
from functools import wraps

# Thread-local storage for request context
_request_context = threading.local()


def generate_request_id():
    """Generate a unique request ID."""
    return f"REQ-{uuid.uuid4().hex[:12].upper()}"


def get_request_id():
    """Get the current request ID from thread-local storage."""
    return getattr(_request_context, 'request_id', None)


def set_request_id(request_id):
    """Set the request ID in thread-local storage."""
    _request_context.request_id = request_id


def clear_request_id():
    """Clear the request ID from thread-local storage."""
    _request_context.request_id = None


def log_with_context(logger, message, level="info", **extra):
    """
    Log a message with request context.

    Args:
        logger: Logger object (or use print if None)
        message: Message to log
        level: Log level (info, warning, error)
        **extra: Additional context to include
    """
    request_id = get_request_id()
    timestamp = time.strftime("%H:%M:%S")

    context_parts = []
    if request_id:
        context_parts.append(f"REQ:{request_id}")
    for key, value in extra.items():
        context_parts.append(f"{key}={value}")

    context_str = " | ".join(context_parts) if context_parts else ""
    full_message = f"[{timestamp}] {message}"
    if context_str:
        full_message += f" | {context_str}"

    if logger:
        getattr(logger, level)(full_message)
    else:
        print(f"  [{level.upper()}] {full_message}")


def with_request_id(func):
    """
    Decorator to ensure request ID is set for a function.
    If no request ID exists, generates one automatically.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not get_request_id():
            set_request_id(generate_request_id())
        try:
            return func(*args, **kwargs)
        finally:
            # Don't clear - let the caller decide when to clean up
            pass
    return wrapper


def extract_request_id_from_headers(headers):
    """
    Extract request ID from HTTP headers or AMQP properties.

    Args:
        headers: Dictionary of headers (can be Flask request.headers or dict)

    Returns:
        Request ID string or None
    """
    if hasattr(headers, 'get'):
        # Flask request.headers or similar
        return headers.get('X-Request-ID') or headers.get('X-Request-Id')
    elif isinstance(headers, dict):
        return headers.get('X-Request-ID') or headers.get('X-Request-Id')
    return None


def extract_request_id_from_amqp(properties):
    """
    Extract request ID from AMQP message properties.

    Args:
        properties: pika.BasicProperties object

    Returns:
        Request ID string or None
    """
    if properties and properties.headers:
        return properties.headers.get('X-Request-ID') or properties.headers.get('X-Request-Id')
    return None


class RequestContext:
    """Context manager for request tracking."""

    def __init__(self, request_id=None):
        self.request_id = request_id or generate_request_id()
        self.previous_id = None

    def __enter__(self):
        self.previous_id = get_request_id()
        set_request_id(self.request_id)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.previous_id:
            set_request_id(self.previous_id)
        else:
            clear_request_id()
        return False


# Flask integration helper
def init_flask_request_tracking(app):
    """
    Initialize request tracking for a Flask app.
    Adds before_request and after_request handlers.

    Args:
        app: Flask application instance
    """
    @app.before_request
    def set_request_context():
        from flask import request
        request_id = extract_request_id_from_headers(request.headers)
        if not request_id:
            request_id = generate_request_id()
        set_request_id(request_id)
        request.request_id = request_id  # Store on Flask request object

    @app.after_request
    def log_request(response):
        from flask import request
        request_id = getattr(request, 'request_id', None)
        if request_id:
            response.headers['X-Request-ID'] = request_id
        return response
