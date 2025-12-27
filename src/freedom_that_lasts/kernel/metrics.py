"""
Prometheus metrics collection for Freedom That Lasts.

Provides observability into system operations, performance, and health.
"""

import time
from collections.abc import Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from prometheus_client import Counter, Gauge, Histogram, start_http_server

# ============================================================================
# Core Event Store Metrics
# ============================================================================

events_appended_total = Counter(
    "ftl_events_appended_total",
    "Total number of events appended to the event store",
    ["stream_type", "event_type"],
)

events_loaded_total = Counter(
    "ftl_events_loaded_total",
    "Total number of events loaded from the event store",
    ["stream_type"],
)

stream_version_conflicts_total = Counter(
    "ftl_stream_version_conflicts_total",
    "Total number of optimistic locking version conflicts",
    ["stream_type"],
)

# ============================================================================
# Command Processing Metrics
# ============================================================================

command_duration_seconds = Histogram(
    "ftl_command_duration_seconds",
    "Duration of command processing in seconds",
    ["command_type"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

commands_processed_total = Counter(
    "ftl_commands_processed_total",
    "Total number of commands processed",
    ["command_type", "status"],  # status: success, failure
)

# ============================================================================
# Freedom Health Metrics
# ============================================================================

risk_level = Gauge(
    "ftl_risk_level",
    "Current system risk level (0=GREEN, 1=YELLOW, 2=RED)",
    ["workspace_id"],
)

delegation_gini_coefficient = Gauge(
    "ftl_delegation_gini_coefficient",
    "Gini coefficient for delegation concentration (0=equal, 1=concentrated)",
    ["workspace_id"],
)

laws_overdue_review_total = Gauge(
    "ftl_laws_overdue_review_total",
    "Number of laws overdue for review",
    ["workspace_id"],
)

# ============================================================================
# Budget Metrics
# ============================================================================

budget_utilization_ratio = Gauge(
    "ftl_budget_utilization_ratio",
    "Budget utilization ratio (allocated/total)",
    ["workspace_id", "budget_id"],
)

expenditure_approvals_total = Counter(
    "ftl_expenditure_approvals_total",
    "Total number of expenditure approvals",
    ["workspace_id"],
)

# ============================================================================
# Procurement Metrics
# ============================================================================

feasible_set_empty_total = Counter(
    "ftl_feasible_set_empty_total",
    "Total number of times feasible supplier set was empty",
    ["law_id"],
)

feasible_set_size = Histogram(
    "ftl_feasible_set_size",
    "Size of feasible supplier set at evaluation",
    ["law_id"],
    buckets=(0, 1, 2, 3, 5, 10, 20, 50, 100),
)

supplier_selection_duration_seconds = Histogram(
    "ftl_supplier_selection_duration_seconds",
    "Duration of supplier selection process",
    ["selection_method"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

tenders_by_status_total = Gauge(
    "ftl_tenders_by_status_total",
    "Number of tenders by status",
    ["status"],
)

supplier_reputation_score = Gauge(
    "ftl_supplier_reputation_score",
    "Current reputation score of suppliers",
    ["supplier_id", "supplier_name"],
)

# ============================================================================
# System Metrics
# ============================================================================

projection_rebuild_duration_seconds = Histogram(
    "ftl_projection_rebuild_duration_seconds",
    "Duration of projection rebuild in seconds",
    ["projection_name"],
    buckets=(0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 120.0),
)

tick_execution_duration_seconds = Histogram(
    "ftl_tick_execution_duration_seconds",
    "Duration of tick execution in seconds",
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0),
)

active_streams_total = Gauge(
    "ftl_active_streams_total",
    "Total number of active event streams",
    ["stream_type"],
)

# ============================================================================
# Helper Functions
# ============================================================================

P = ParamSpec("P")
R = TypeVar("R")


def track_command_duration(command_type: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    Decorator to track command processing duration.

    Args:
        command_type: Type of command being processed

    Returns:
        Decorated function that tracks duration
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            start = time.perf_counter()
            status = "success"
            try:
                result = func(*args, **kwargs)
                return result
            except Exception:
                status = "failure"
                raise
            finally:
                duration = time.perf_counter() - start
                command_duration_seconds.labels(command_type=command_type).observe(duration)
                commands_processed_total.labels(
                    command_type=command_type, status=status
                ).inc()

        return wrapper

    return decorator


def start_metrics_server(port: int = 9090) -> None:
    """
    Start Prometheus metrics HTTP server.

    Args:
        port: Port to listen on (default: 9090)
    """
    start_http_server(port)


def update_freedom_health_metrics(
    workspace_id: str,
    gini: float,
    risk: int,
    overdue_count: int,
) -> None:
    """
    Update Freedom Health metrics.

    Args:
        workspace_id: Workspace identifier
        gini: Gini coefficient value
        risk: Risk level (0=GREEN, 1=YELLOW, 2=RED)
        overdue_count: Number of overdue laws
    """
    delegation_gini_coefficient.labels(workspace_id=workspace_id).set(gini)
    risk_level.labels(workspace_id=workspace_id).set(risk)
    laws_overdue_review_total.labels(workspace_id=workspace_id).set(overdue_count)
