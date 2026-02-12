#!/usr/bin/env python3
"""
telemetry.py — Lightweight usage telemetry for TSG Builder.

Emits anonymous custom events to Azure Application Insights for adoption
and operational metrics. All calls are fire-and-forget — failures are
silently swallowed and never affect application behavior.

Privacy guarantees:
- Only counts, enums, durations, and version strings are emitted
- Never emits notes, TSG text, error messages with user content, or PII
- Opt out by setting TSG_TELEMETRY=0 in .env or environment

See docs/telemetry-plan.md and issues/issue-usage-telemetry.md for details.
"""

from __future__ import annotations

import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Any

from dotenv import set_key

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_initialized = False
_logger: logging.Logger | None = None
_install_id: str | None = None


# ---------------------------------------------------------------------------
# Connection string resolution
# ---------------------------------------------------------------------------

def _get_connection_string() -> str | None:
    """Resolve the App Insights connection string.

    Cascade:
      1. _build_config.py (generated at build time, gitignored)
      2. APPINSIGHTS_CONNECTION_STRING environment variable
      3. None → telemetry silently disabled
    """
    # 1. Build-time injected config (release binaries)
    try:
        from _build_config import APPINSIGHTS_CONNECTION_STRING  # type: ignore[import-not-found]
        if APPINSIGHTS_CONNECTION_STRING:
            return APPINSIGHTS_CONNECTION_STRING
    except (ImportError, AttributeError):
        pass

    # 2. Environment variable (dev / admin override)
    conn_str = os.environ.get("APPINSIGHTS_CONNECTION_STRING")
    if conn_str:
        return conn_str

    # 3. No connection string available → disabled
    return None


# ---------------------------------------------------------------------------
# Opt-out check
# ---------------------------------------------------------------------------

def is_telemetry_enabled() -> bool:
    """Check whether telemetry is enabled.

    Telemetry is **enabled by default**. Set ``TSG_TELEMETRY=0`` or
    ``TSG_TELEMETRY=false`` (case-insensitive) to disable.
    """
    value = os.environ.get("TSG_TELEMETRY", "").strip().lower()
    if value in ("0", "false", "no"):
        return False
    return True


# ---------------------------------------------------------------------------
# Install ID
# ---------------------------------------------------------------------------

def _get_env_path() -> Path:
    """Get the .env file path (same logic as web_app._get_app_dir)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / ".env"
    else:
        return Path.cwd() / ".env"


def _get_or_create_install_id() -> str | None:
    """Get or create a random install ID for correlating events.

    The ID is a random UUID4, not derived from any machine/user/network
    identifier. It is persisted to ``.env`` as ``TSG_INSTALL_ID`` so it
    survives restarts. Returns ``None`` when telemetry is opted out.
    """
    global _install_id

    if not is_telemetry_enabled():
        return None

    # Return cached value if already resolved
    if _install_id is not None:
        return _install_id

    # Check environment first (already loaded by web_app via load_dotenv)
    existing = os.environ.get("TSG_INSTALL_ID", "").strip()
    if existing:
        _install_id = existing
        return _install_id

    # Generate a new one and persist
    new_id = str(uuid.uuid4())
    try:
        env_path = _get_env_path()
        if env_path.exists():
            set_key(str(env_path), "TSG_INSTALL_ID", new_id)
        os.environ["TSG_INSTALL_ID"] = new_id
    except Exception:
        pass  # Non-critical — use the ID in-memory even if persist fails

    _install_id = new_id
    return _install_id


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

def init_telemetry() -> None:
    """Initialize the telemetry subsystem.

    Sets up the OpenTelemetry logging pipeline with an
    ``AzureMonitorLogExporter``. Safe to call multiple times (no-op after
    the first successful init). Never raises.
    """
    global _initialized, _logger

    if _initialized:
        return

    try:
        if not is_telemetry_enabled():
            _initialized = True
            return

        connection_string = _get_connection_string()
        if not connection_string:
            _initialized = True
            return

        # Import OpenTelemetry components
        from opentelemetry._logs import set_logger_provider
        from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
        from azure.monitor.opentelemetry.exporter import AzureMonitorLogExporter

        # Set up the exporter and logger provider
        logger_provider = LoggerProvider()
        exporter = AzureMonitorLogExporter(connection_string=connection_string)
        logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(exporter)
        )
        set_logger_provider(logger_provider)

        # Create a namespaced logger (avoids recursion with azure-core internals)
        handler = LoggingHandler()
        _logger = logging.getLogger("tsgbuilder.telemetry")
        _logger.addHandler(handler)
        _logger.setLevel(logging.INFO)

        _initialized = True

    except Exception:
        # Telemetry setup failure must never crash the app
        _initialized = True


# ---------------------------------------------------------------------------
# Event emission
# ---------------------------------------------------------------------------

def track_event(
    name: str,
    properties: dict[str, str] | None = None,
    measurements: dict[str, float | int] | None = None,
) -> None:
    """Emit a custom event to Application Insights.

    This is a fire-and-forget call. Failures are silently swallowed.

    Args:
        name: Event name (e.g. ``"tsg_generated"``, ``"app_started"``).
        properties: String key-value pairs (dimensions).
        measurements: Numeric key-value pairs (metrics).
    """
    try:
        if not is_telemetry_enabled():
            return

        if _logger is None:
            return

        # Build the extras dict for the log record
        extra: dict[str, Any] = {
            "microsoft.custom_event.name": name,
        }

        # Merge properties
        if properties:
            extra.update(properties)

        # Merge measurements (App Insights treats numeric custom dimensions
        # the same as string ones in customEvents; callers use the
        # measurements dict for semantic clarity)
        if measurements:
            for k, v in measurements.items():
                extra[k] = v

        # Attach install_id if available
        install_id = _get_or_create_install_id()
        if install_id and "install_id" not in extra:
            extra["install_id"] = install_id

        _logger.info(name, extra=extra)

    except Exception:
        # Fire-and-forget — never crash, never log spam
        pass
