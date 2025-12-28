"""
Structured logging framework for Freedom That Lasts.

Provides correlation IDs, context propagation, and JSON output for production observability.

Fun fact: Correlation IDs were popularized by Google's Dapper distributed tracing system
in 2010. Now they're essential for debugging microservices - we're using them in a monolith!
"""

import contextvars
import logging
import os
import secrets
import sys
from typing import Any

import structlog

# Context variable for correlation ID (thread-safe)
correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default=""
)


def generate_correlation_id() -> str:
    """
    Generate a new correlation ID using cryptographic randomness.

    Uses secrets.token_urlsafe() instead of uuid.uuid4() for cryptographic strength.
    Returns a 22-character URL-safe base64 string (128 bits of entropy).
    """
    return secrets.token_urlsafe(16)  # 16 bytes = 128 bits = 22 base64 chars


def get_correlation_id() -> str:
    """Get the current correlation ID, or generate a new one if not set."""
    cid = correlation_id_var.get()
    if not cid:
        cid = generate_correlation_id()
        correlation_id_var.set(cid)
    return cid


def set_correlation_id(correlation_id: str) -> None:
    """Set the correlation ID for the current context."""
    correlation_id_var.set(correlation_id)


def add_correlation_id(
    logger: logging.Logger, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Add correlation ID to log event."""
    event_dict["correlation_id"] = get_correlation_id()
    return event_dict


def configure_logging(
    *,
    json_output: bool = False,
    log_level: str = "INFO",
) -> None:
    """
    Configure structured logging for the application.

    Args:
        json_output: If True, output JSON logs (for production).
                    If False, output human-readable console logs (for development).
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    # Convert log level string to logging constant
    level = getattr(logging, log_level.upper())

    # Configure stdlib logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )

    # Disable overly verbose third-party loggers
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    # Configure structlog processors
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        add_correlation_id,
    ]

    if json_output:
        # Production: JSON output
        processors = shared_processors + [
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Development: Human-readable console output
        processors = shared_processors + [
            structlog.processors.ExceptionRenderer(),
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger for the given module.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Structured logger instance
    """
    return structlog.get_logger(name)


def is_production() -> bool:
    """
    Determine if running in production environment.

    Checks ENVIRONMENT environment variable. Returns True if 'production', False otherwise.
    Defaults to False (development) if not set.
    """
    return os.getenv("ENVIRONMENT", "development").lower() == "production"


# Sensitive fields that should be redacted from logs (PII and financial data)
REDACTED_FIELDS = {
    "actor_id",
    "from_actor",
    "to_actor",
    "amount",
    "password",
    "token",
    "secret",
    "api_key",
    "private_key",
}


def redact_context(context: dict[str, Any]) -> dict[str, Any]:
    """
    Redact sensitive fields from log context to prevent PII leakage.

    Args:
        context: Dictionary of log context

    Returns:
        New dictionary with sensitive fields redacted

    Example:
        >>> redact_context({"actor_id": "alice", "operation": "delegate"})
        {"actor_id": "***REDACTED***", "operation": "delegate"}
    """
    return {
        k: "***REDACTED***" if k in REDACTED_FIELDS else v
        for k, v in context.items()
    }


# Convenience context manager for logging operations with timing
class LogOperation:
    """Context manager for logging operations with automatic timing."""

    def __init__(
        self,
        logger: structlog.stdlib.BoundLogger,
        operation: str,
        **context: Any,
    ):
        """
        Initialize operation logger.

        Args:
            logger: Structured logger instance
            operation: Operation name (e.g., "append_events", "handle_command")
            **context: Additional context to include in logs
        """
        self.logger = logger
        self.operation = operation
        self.context = context
        self.start_time: float = 0.0

    def __enter__(self) -> "LogOperation":
        """Start operation logging with PII redaction."""
        import time

        self.start_time = time.perf_counter()
        # Redact sensitive fields before logging
        redacted = redact_context(self.context)
        self.logger.info(
            f"{self.operation} started",
            operation=self.operation,
            **redacted,
        )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Complete operation logging with duration, PII redaction, and environment-aware stack traces."""
        import time

        duration_ms = (time.perf_counter() - self.start_time) * 1000
        # Redact sensitive fields before logging
        redacted = redact_context(self.context)
        # Only include stack traces in development (not production)
        production = is_production()

        if exc_type is None:
            # Success
            self.logger.info(
                f"{self.operation} completed",
                operation=self.operation,
                duration_ms=round(duration_ms, 2),
                **redacted,
            )
        else:
            # Error - include stack trace only in development
            self.logger.error(
                f"{self.operation} failed",
                operation=self.operation,
                duration_ms=round(duration_ms, 2),
                exc_info=not production,  # Stack traces only in development
                **redacted,
            )
