"""
Zentrale Logging-Konfiguration für ECO OpenAI Wrapper.

Features:
- Log-Rotation (10MB pro File, 5 Backups = max 60MB)
- Separate app.log (alle Levels) und error.log (nur Errors)
- Console + File Output
- Diagnostic-Logs optional (für Bug-Debugging)
- Environment-basierte Konfiguration (LOG_LEVEL)
- Security-Filter für sensitive Daten (API Keys, Tokens)

Integration:
- Kompatibel mit Request Limiter (request_limiter.py)
- Kompatibel mit bestehendem Logging in main.py
- Drop-in Replacement für logging.basicConfig()
"""

import logging
import logging.handlers
import os
import sys
import re
from pathlib import Path
from typing import Optional


# Projekt-Root und Logs-Verzeichnis
PROJECT_ROOT = Path(__file__).parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"


class SensitiveDataFilter(logging.Filter):
    """
    Filtert sensible Daten aus Log-Nachrichten.

    Patterns:
    - API Keys / Tokens (Bearer, api_key=...)
    - Passwörter (password=...)
    - Session IDs (teilweise maskiert)
    """

    PATTERNS = [
        # API Keys / Tokens (mit verschiedenen Formaten)
        (re.compile(r'(api[_-]?key|token|bearer)["\']?\s*[:=]\s*["\']?([A-Za-z0-9_-]{20,})', re.I),
         r'\1=***'),
        (re.compile(r'Bearer\s+([A-Za-z0-9_-]{20,})', re.I),
         r'Bearer ***'),

        # Passwörter
        (re.compile(r'password["\']?\s*[:=]\s*["\']?([^\s"\']+)', re.I),
         r'password=***'),

        # ANTHROPIC_API_KEY (speziell)
        (re.compile(r'ANTHROPIC_API_KEY["\']?\s*[:=]\s*["\']?([^\s"\']+)', re.I),
         r'ANTHROPIC_API_KEY=***'),

        # Session IDs (erste 8 Zeichen behalten, Rest maskieren)
        (re.compile(r'(session[_-]?id)["\']?\s*[:=]\s*["\']?([A-Za-z0-9_-]{10,})', re.I),
         lambda m: f"{m.group(1)}={m.group(2)[:8]}***"),
    ]

    def filter(self, record):
        """Filter sensitive data from log message."""
        msg = record.getMessage()

        for pattern, replacement in self.PATTERNS:
            if callable(replacement):
                msg = pattern.sub(replacement, msg)
            else:
                msg = pattern.sub(replacement, msg)

        # Update record message
        record.msg = msg
        record.args = ()
        return True


class DiagnosticFilter(logging.Filter):
    """
    Filter für Diagnostic-Logs (🔴🟡🔵🟣 Marker).
    Nur Logs mit Emoji-Markern durchlassen.
    """
    DIAGNOSTIC_MARKERS = ['🔴', '🟡', '🔵', '🟣']

    def filter(self, record):
        msg = record.getMessage()
        return any(marker in msg for marker in self.DIAGNOSTIC_MARKERS)


def setup_logging(
    log_level: Optional[str] = None,
    enable_diagnostic: bool = False,
    log_to_console: bool = True,
    log_to_file: bool = True,
    enable_json: bool = False,
    filter_sensitive_data: bool = True
) -> None:
    """
    Konfiguriert Logging für den gesamten Wrapper.

    Args:
        log_level: Log-Level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
                   Falls None, wird LOG_LEVEL aus Environment gelesen (default: INFO)
        enable_diagnostic: Aktiviert diagnostische Logs (🔴🟡🔵) in diagnostic.log
        log_to_console: Logs in Console ausgeben (stdout)
        log_to_file: Logs in Dateien schreiben (app.log, error.log)
        enable_json: JSON-Format für strukturiertes Logging (für Log-Aggregation)
        filter_sensitive_data: Filtert API Keys, Passwords, Tokens aus Logs

    Environment Variables:
        LOG_LEVEL: DEBUG, INFO, WARNING, ERROR, CRITICAL (default: INFO)
        ENABLE_DIAGNOSTIC: true/false (default: false)
        LOG_TO_FILE: true/false (default: true)
        FILTER_SENSITIVE_DATA: true/false (default: true)

    Files Created:
        logs/app.log       - Alle Logs (DEBUG+), rotiert bei 10MB
        logs/error.log     - Nur Errors (ERROR+), rotiert bei 10MB
        logs/diagnostic.log- Nur Diagnostic-Logs (optional)

    Example:
        # In main.py
        setup_logging(log_level="INFO", enable_diagnostic=False)

        # In allen anderen Modulen
        from config.logging_config import get_logger
        logger = get_logger(__name__)
    """

    # Log-Level aus Environment oder Parameter
    if log_level is None:
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    # Diagnostic aus Environment (falls nicht explizit gesetzt)
    if not enable_diagnostic:
        enable_diagnostic = os.getenv("ENABLE_DIAGNOSTIC", "false").lower() in ('true', '1', 'yes', 'on')

    # Log-to-File aus Environment
    if os.getenv("LOG_TO_FILE", "true").lower() in ('false', '0', 'no', 'off'):
        log_to_file = False

    # Sensitive Data Filter aus Environment
    if os.getenv("FILTER_SENSITIVE_DATA", "true").lower() in ('false', '0', 'no', 'off'):
        filter_sensitive_data = False

    # Logs-Verzeichnis erstellen
    LOGS_DIR.mkdir(exist_ok=True)

    # Root Logger konfigurieren
    root_logger = logging.getLogger()
    # Set root logger to configured level (not DEBUG - handlers have their own levels)
    numeric_level = getattr(logging, log_level.upper())
    root_logger.setLevel(numeric_level)

    # Alte Handler entfernen (wichtig bei Re-Konfiguration)
    root_logger.handlers.clear()

    # Get instance name from environment (for multi-instance deployments)
    instance_name = os.getenv('INSTANCE_NAME', 'main')
    port = os.getenv('PORT', '8000')

    # Formatter definieren
    if enable_json:
        # JSON-Format für Log-Aggregation (ELK, Splunk, etc.)
        import json

        class JSONFormatter(logging.Formatter):
            def format(self, record):
                log_data = {
                    'timestamp': self.formatTime(record, self.datefmt),
                    'instance': instance_name,
                    'port': int(port),
                    'level': record.levelname,
                    'logger': record.name,
                    'message': record.getMessage(),
                    'module': record.module,
                    'function': record.funcName,
                    'line': record.lineno,
                    'process': record.process,
                    'thread': record.thread
                }
                if record.exc_info:
                    log_data['exception'] = self.formatException(record.exc_info)
                return json.dumps(log_data)

        formatter = JSONFormatter(datefmt='%Y-%m-%d %H:%M:%S')
    else:
        # Standard-Format (human-readable) with instance identification
        formatter = logging.Formatter(
            f'%(asctime)s - [{instance_name}] - %(name)s - %(levelname)s - [%(module)s:%(funcName)s:%(lineno)d] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

    # Security Filter (falls aktiviert)
    security_filter = SensitiveDataFilter() if filter_sensitive_data else None

    # Console Handler (stdout)
    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        if security_filter:
            console_handler.addFilter(security_filter)
        root_logger.addHandler(console_handler)

    # File Handler - app.log (alle Logs)
    if log_to_file:
        app_log = LOGS_DIR / "app.log"
        app_handler = logging.handlers.RotatingFileHandler(
            app_log,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,               # 5 Backups = max 60 MB
            encoding='utf-8'
        )
        app_handler.setLevel(logging.DEBUG)  # Alle Levels
        app_handler.setFormatter(formatter)
        if security_filter:
            app_handler.addFilter(security_filter)
        root_logger.addHandler(app_handler)

        # Error File Handler - error.log (nur ERROR und CRITICAL)
        error_log = LOGS_DIR / "error.log"
        error_handler = logging.handlers.RotatingFileHandler(
            error_log,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,               # 5 Backups
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        if security_filter:
            error_handler.addFilter(security_filter)
        root_logger.addHandler(error_handler)

    # Diagnostic Handler (optional) - diagnostic.log
    if enable_diagnostic:
        diagnostic_log = LOGS_DIR / "diagnostic.log"
        diagnostic_handler = logging.handlers.RotatingFileHandler(
            diagnostic_log,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=2,               # Nur 2 Backups (temporär)
            encoding='utf-8'
        )
        diagnostic_handler.setLevel(logging.ERROR)  # Diagnostic nutzt ERROR-Level

        # Nur Logs mit Emoji-Markern (🔴🟡🔵🟣)
        diagnostic_handler.addFilter(DiagnosticFilter())
        diagnostic_handler.setFormatter(formatter)
        # KEIN Security-Filter für Diagnostic (wir wollen alle Details sehen)
        root_logger.addHandler(diagnostic_handler)

    # Externe Libraries auf WARNING setzen (reduziert Noise)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("fastapi").setLevel(logging.WARNING)

    # Neue externe Libraries (aus Request Limiter)
    logging.getLogger("psutil").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)

    # Logging-Konfiguration bestätigen
    root_logger.info("=" * 70)
    root_logger.info(f"Logging configured:")
    root_logger.info(f"  Instance: {instance_name} (Port: {port})")
    root_logger.info(f"  Level: {log_level}")
    root_logger.info(f"  Console: {log_to_console}")
    root_logger.info(f"  File: {log_to_file}")
    root_logger.info(f"  Diagnostic: {enable_diagnostic}")
    root_logger.info(f"  JSON: {enable_json}")
    root_logger.info(f"  Security Filter: {filter_sensitive_data}")
    root_logger.info(f"  Logs Dir: {LOGS_DIR}")
    root_logger.info("=" * 70)


def get_logger(name: str) -> logging.Logger:
    """
    Holt einen Logger für ein bestimmtes Modul.

    Args:
        name: Name des Loggers (üblicherweise __name__)

    Returns:
        Konfigurierter Logger

    Example:
        # In jedem Modul
        from config.logging_config import get_logger
        logger = get_logger(__name__)

        logger.info("Processing started")
        logger.error("Error occurred", exc_info=True)
    """
    return logging.getLogger(name)
