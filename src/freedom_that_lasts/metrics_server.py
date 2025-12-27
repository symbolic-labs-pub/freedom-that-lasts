"""
Prometheus metrics server for Freedom That Lasts.

This script starts an HTTP server that exposes Prometheus metrics at /metrics.
It can be run standalone or integrated with the main application.

Usage:
    python -m freedom_that_lasts.metrics_server --port 9090
"""

import argparse
import time

from freedom_that_lasts.kernel.logging import configure_logging, get_logger
from freedom_that_lasts.kernel.metrics import start_metrics_server

logger = get_logger(__name__)


def main() -> None:
    """
    Start the Prometheus metrics server.

    The server exposes all FTL metrics at http://0.0.0.0:<port>/metrics
    in Prometheus text format.
    """
    parser = argparse.ArgumentParser(description="Freedom That Lasts Metrics Server")
    parser.add_argument(
        "--port",
        type=int,
        default=9090,
        help="Port to listen on (default: 9090)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level (default: INFO)",
    )
    parser.add_argument(
        "--json-logs",
        action="store_true",
        help="Output logs in JSON format (default: False)",
    )

    args = parser.parse_args()

    # Configure logging
    configure_logging(json_output=args.json_logs, log_level=args.log_level)

    logger.info(
        "Starting Prometheus metrics server",
        port=args.port,
        endpoint=f"http://0.0.0.0:{args.port}/metrics",
    )

    # Start metrics server
    start_metrics_server(port=args.port)

    logger.info("Metrics server started successfully")

    # Keep the server running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down metrics server")


if __name__ == "__main__":
    main()
