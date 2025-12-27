"""
Health check HTTP server for Kubernetes liveness and readiness probes.

Provides endpoints for monitoring the health and readiness of the FTL system.
"""

import sqlite3
from pathlib import Path
from typing import Any

from flask import Flask, jsonify

from freedom_that_lasts.kernel.logging import get_logger

logger = get_logger(__name__)

app = Flask(__name__)

# Global state - will be set by initialize_health_server()
_db_path: Path | None = None
_ftl_instance: Any = None  # FTL instance for health checks


def initialize_health_server(db_path: str | Path, ftl_instance: Any = None) -> None:
    """
    Initialize the health server with FTL instance and database path.

    Args:
        db_path: Path to SQLite database
        ftl_instance: Optional FTL instance for detailed health checks
    """
    global _db_path, _ftl_instance
    _db_path = Path(db_path)
    _ftl_instance = ftl_instance
    logger.info("Health server initialized", db_path=str(_db_path))


@app.route("/health/live", methods=["GET"])
def liveness() -> tuple[dict[str, Any], int]:
    """
    Liveness probe - checks if the process is running.

    Kubernetes will restart the pod if this fails.

    Returns:
        JSON response with status and 200 OK
    """
    return jsonify({"status": "alive", "service": "freedom-that-lasts"}), 200


@app.route("/health/ready", methods=["GET"])
def readiness() -> tuple[dict[str, Any], int]:
    """
    Readiness probe - checks if the service is ready to accept requests.

    Kubernetes will not route traffic to the pod if this fails.

    Checks:
    - Database is accessible
    - Database file exists
    - Can execute a simple query

    Returns:
        JSON response with status and 200 OK if ready, 503 if not ready
    """
    if _db_path is None:
        logger.error("Readiness check failed: DB path not initialized")
        return (
            jsonify(
                {
                    "status": "not_ready",
                    "reason": "database_path_not_initialized",
                }
            ),
            503,
        )

    # Check if database file exists
    if not _db_path.exists():
        logger.error("Readiness check failed: DB file does not exist", db_path=str(_db_path))
        return (
            jsonify(
                {
                    "status": "not_ready",
                    "reason": "database_file_not_found",
                    "db_path": str(_db_path),
                }
            ),
            503,
        )

    # Try to connect and execute a simple query
    try:
        conn = sqlite3.connect(str(_db_path), timeout=1.0)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM events")
        event_count = cursor.fetchone()[0]
        conn.close()

        logger.debug("Readiness check passed", event_count=event_count)
        return (
            jsonify(
                {
                    "status": "ready",
                    "database": "accessible",
                    "event_count": event_count,
                }
            ),
            200,
        )

    except sqlite3.OperationalError as e:
        logger.error("Readiness check failed: DB operational error", error=str(e))
        return (
            jsonify(
                {
                    "status": "not_ready",
                    "reason": "database_operational_error",
                    "error": str(e),
                }
            ),
            503,
        )
    except Exception as e:
        logger.error("Readiness check failed: Unexpected error", error=str(e), exc_info=True)
        return (
            jsonify(
                {
                    "status": "not_ready",
                    "reason": "unexpected_error",
                    "error": str(e),
                }
            ),
            503,
        )


@app.route("/health", methods=["GET"])
def detailed_health() -> tuple[dict[str, Any], int]:
    """
    Detailed health check - includes FreedomHealth metrics if available.

    Returns:
        JSON response with detailed health information
    """
    health_data: dict[str, Any] = {
        "status": "healthy",
        "service": "freedom-that-lasts",
        "version": "1.0.0-dev",
    }

    # Database health
    if _db_path and _db_path.exists():
        try:
            conn = sqlite3.connect(str(_db_path), timeout=1.0)
            cursor = conn.cursor()

            # Get event count
            cursor.execute("SELECT COUNT(*) FROM events")
            event_count = cursor.fetchone()[0]

            # Get stream count
            cursor.execute("SELECT COUNT(DISTINCT stream_id) FROM events")
            stream_count = cursor.fetchone()[0]

            # Get database size
            cursor.execute("PRAGMA page_count")
            page_count = cursor.fetchone()[0]
            cursor.execute("PRAGMA page_size")
            page_size = cursor.fetchone()[0]
            db_size_mb = (page_count * page_size) / (1024 * 1024)

            conn.close()

            health_data["database"] = {
                "status": "healthy",
                "path": str(_db_path),
                "event_count": event_count,
                "stream_count": stream_count,
                "size_mb": round(db_size_mb, 2),
            }

        except Exception as e:
            logger.error("Database health check failed", error=str(e))
            health_data["database"] = {
                "status": "unhealthy",
                "error": str(e),
            }
            health_data["status"] = "degraded"
    else:
        health_data["database"] = {"status": "not_initialized"}
        health_data["status"] = "degraded"

    # FreedomHealth metrics (if FTL instance available)
    if _ftl_instance:
        try:
            # Get freedom health from feedback module
            from freedom_that_lasts.feedback.indicators import compute_freedom_health

            freedom_health = compute_freedom_health(
                delegation_graph=_ftl_instance.delegation_graph,
                law_registry=_ftl_instance.law_registry,
                event_store=_ftl_instance.event_store,
            )

            health_data["freedom_health"] = {
                "gini_coefficient": round(freedom_health.gini_coefficient, 3),
                "concentration_ratio": round(freedom_health.concentration_ratio, 3),
                "risk_level": freedom_health.risk_level.name,
                "overdue_review_count": freedom_health.overdue_review_count,
            }

        except Exception as e:
            logger.warning("Could not compute freedom health", error=str(e))
            health_data["freedom_health"] = {"status": "unavailable", "error": str(e)}

    # Determine overall status code
    status_code = 200 if health_data["status"] == "healthy" else 503

    return jsonify(health_data), status_code


def run_health_server(port: int = 8080, debug: bool = False) -> None:
    """
    Run the health check server.

    Args:
        port: Port to listen on (default: 8080)
        debug: Enable Flask debug mode (default: False)
    """
    logger.info("Starting health check server", port=port)
    app.run(host="0.0.0.0", port=port, debug=debug)


if __name__ == "__main__":
    # For testing: python -m freedom_that_lasts.health_server
    initialize_health_server("/tmp/ftl-test.db")
    run_health_server(port=8080, debug=True)
