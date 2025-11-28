#!/usr/bin/env python3
"""
Silent Failure Detection Script

Detects CLI sessions that completed but have no corresponding EVENT log.
This indicates a silent failure where the wrapper crashed without logging.

Usage:
    python scripts/detect_silent_failures.py
    python scripts/detect_silent_failures.py --log-file logs/app.log
    python scripts/detect_silent_failures.py --time-window 3600  # Last hour
"""

import re
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class CLICompletion:
    """Represents a CLI session completion log entry."""
    timestamp: datetime
    session_id: str
    log_line: str


@dataclass
class EventLog:
    """Represents an EVENT log entry."""
    timestamp: datetime
    session_id: str
    has_error: bool
    log_line: str


@dataclass
class SilentFailure:
    """Represents a detected silent failure."""
    cli_completion: CLICompletion
    reason: str
    severity: str  # 'CRITICAL', 'WARNING'


def parse_timestamp(timestamp_str: str) -> Optional[datetime]:
    """Parse log timestamp to datetime."""
    try:
        # Format: 2025-10-20 14:27:29
        return datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def extract_cli_completions(log_file: Path, time_window: Optional[int] = None) -> List[CLICompletion]:
    """Extract all CLI session completion events from log file.

    Args:
        log_file: Path to app.log
        time_window: Optional time window in seconds (only include recent completions)

    Returns:
        List of CLI completion events
    """
    completions = []
    pattern = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*CLI session ([a-f0-9\-]+) completed')

    cutoff_time = None
    if time_window:
        cutoff_time = datetime.now() - timedelta(seconds=time_window)

    with open(log_file, 'r') as f:
        for line in f:
            match = pattern.match(line)
            if match:
                timestamp_str, session_id = match.groups()
                timestamp = parse_timestamp(timestamp_str)

                if timestamp and (not cutoff_time or timestamp >= cutoff_time):
                    completions.append(CLICompletion(
                        timestamp=timestamp,
                        session_id=session_id,
                        log_line=line.strip()
                    ))

    return completions


def extract_event_logs(log_file: Path, time_window: Optional[int] = None) -> List[EventLog]:
    """Extract all EVENT log entries from log file.

    Args:
        log_file: Path to app.log
        time_window: Optional time window in seconds

    Returns:
        List of EVENT logs
    """
    events = []
    pattern = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*EVENT:.*"session_id":\s*"([^"]+)".*')
    error_pattern = re.compile(r'"error":\s*"([^"]+)"')

    cutoff_time = None
    if time_window:
        cutoff_time = datetime.now() - timedelta(seconds=time_window)

    with open(log_file, 'r') as f:
        for line in f:
            match = pattern.match(line)
            if match:
                timestamp_str, session_id = match.groups()
                timestamp = parse_timestamp(timestamp_str)

                if timestamp and (not cutoff_time or timestamp >= cutoff_time):
                    has_error = error_pattern.search(line) is not None
                    events.append(EventLog(
                        timestamp=timestamp,
                        session_id=session_id,
                        has_error=has_error,
                        log_line=line.strip()
                    ))

    return events


def detect_silent_failures(
    completions: List[CLICompletion],
    events: List[EventLog],
    tolerance_seconds: int = 10
) -> List[SilentFailure]:
    """Detect CLI completions without corresponding EVENT logs.

    Args:
        completions: List of CLI completion events
        events: List of EVENT logs
        tolerance_seconds: Time tolerance for matching completion to event (default: 10s)

    Returns:
        List of detected silent failures
    """
    failures = []

    for completion in completions:
        # Look for EVENT within tolerance window
        has_event = False

        for event in events:
            # Check session ID match (handle "none" vs actual ID)
            session_match = (
                event.session_id == completion.session_id or
                (event.session_id == "none" and completion.session_id)
            )

            # Check timestamp proximity
            time_diff = abs((event.timestamp - completion.timestamp).total_seconds())
            time_match = time_diff <= tolerance_seconds

            if session_match and time_match:
                has_event = True
                break

        if not has_event:
            # CRITICAL: CLI completed but no EVENT logged
            failures.append(SilentFailure(
                cli_completion=completion,
                reason="CLI session completed but no EVENT log found within tolerance window",
                severity="CRITICAL"
            ))

    return failures


def print_report(failures: List[SilentFailure], verbose: bool = False):
    """Print silent failure detection report.

    Args:
        failures: List of detected failures
        verbose: Include detailed information
    """
    if not failures:
        print("✅ No silent failures detected!")
        return

    print(f"\n{'='*80}")
    print(f"🚨 SILENT FAILURE DETECTION REPORT")
    print(f"{'='*80}")
    print(f"\nDetected {len(failures)} silent failure(s):\n")

    for i, failure in enumerate(failures, 1):
        completion = failure.cli_completion

        print(f"{i}. [{failure.severity}] Session: {completion.session_id}")
        print(f"   Timestamp: {completion.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   Reason: {failure.reason}")

        if verbose:
            print(f"   Log line: {completion.log_line[:100]}...")

        print()

    print(f"{'='*80}")
    print(f"\n💡 Recommended Actions:")
    print(f"   1. Check error.log for exceptions around failure timestamps")
    print(f"   2. Review wrapper code for unhandled exceptions")
    print(f"   3. Verify HTTPException logging is enabled")
    print(f"   4. Check if SDK returned zero chunks")
    print(f"\n{'='*80}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Detect silent failures in ECO OpenAI Wrapper"
    )
    parser.add_argument(
        '--log-file',
        type=Path,
        default=Path(__file__).parent.parent / 'logs' / 'app.log',
        help='Path to app.log file (default: logs/app.log)'
    )
    parser.add_argument(
        '--time-window',
        type=int,
        default=None,
        help='Only analyze logs from last N seconds (default: all)'
    )
    parser.add_argument(
        '--tolerance',
        type=int,
        default=10,
        help='Time tolerance in seconds for matching completion to event (default: 10)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Show detailed information'
    )

    args = parser.parse_args()

    # Validate log file exists
    if not args.log_file.exists():
        print(f"❌ Error: Log file not found: {args.log_file}")
        return 1

    print(f"🔍 Analyzing logs from: {args.log_file}")
    if args.time_window:
        print(f"   Time window: Last {args.time_window} seconds")
    else:
        print(f"   Time window: All logs")
    print()

    # Extract completions and events
    print("📊 Extracting CLI completions...")
    completions = extract_cli_completions(args.log_file, args.time_window)
    print(f"   Found {len(completions)} CLI completions")

    print("📊 Extracting EVENT logs...")
    events = extract_event_logs(args.log_file, args.time_window)
    print(f"   Found {len(events)} EVENT logs")

    # Detect failures
    print("\n🔎 Detecting silent failures...")
    failures = detect_silent_failures(completions, events, args.tolerance)

    # Print report
    print_report(failures, verbose=args.verbose)

    # Exit with error code if failures detected
    return 1 if failures else 0


if __name__ == '__main__':
    exit(main())
