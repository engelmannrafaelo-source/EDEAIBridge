import asyncio
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from threading import Lock
import uuid

from config.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class CLISession:
    """Represents a running Claude CLI call (e.g., /sc:research)."""
    cli_session_id: str
    prompt: str  # The prompt/command being executed
    started_at: datetime = field(default_factory=datetime.utcnow)
    model: Optional[str] = None
    status: str = "running"  # running, completed, cancelled, failed
    cancellation_token: Optional[asyncio.Event] = field(default=None)
    task: Optional[asyncio.Task] = field(default=None)

    def __post_init__(self):
        """Initialize cancellation token if not provided."""
        if self.cancellation_token is None:
            try:
                # Create event in the current loop if running
                loop = asyncio.get_running_loop()
                self.cancellation_token = asyncio.Event()
            except RuntimeError:
                # No running loop, will be created later when needed
                pass

    def to_dict(self) -> Dict:
        """Convert to dictionary for API responses."""
        return {
            "cli_session_id": self.cli_session_id,
            "prompt": self.prompt[:200] + "..." if len(self.prompt) > 200 else self.prompt,
            "started_at": self.started_at.isoformat(),
            "model": self.model,
            "status": self.status,
            "duration_seconds": (datetime.utcnow() - self.started_at).total_seconds()
        }

    def cancel(self):
        """Signal cancellation to the running task."""
        if self.cancellation_token:
            self.cancellation_token.set()
        self.status = "cancelled"
        logger.info(f"Cancelled CLI session: {self.cli_session_id}")


class CLISessionManager:
    """Manages running Claude CLI calls with cancellation support."""

    def __init__(self):
        self.sessions: Dict[str, CLISession] = {}
        self.lock = Lock()

    def create_session(
        self,
        prompt: str,
        model: Optional[str] = None,
        task: Optional[asyncio.Task] = None
    ) -> CLISession:
        """Create and register a new CLI session."""
        with self.lock:
            cli_session_id = str(uuid.uuid4())

            # Create cancellation token
            try:
                cancellation_token = asyncio.Event()
            except RuntimeError:
                cancellation_token = None

            session = CLISession(
                cli_session_id=cli_session_id,
                prompt=prompt,
                model=model,
                cancellation_token=cancellation_token,
                task=task
            )

            self.sessions[cli_session_id] = session
            logger.info(f"Created CLI session: {cli_session_id} - {prompt[:100]}...")

            return session

    def get_session(self, cli_session_id: str) -> Optional[CLISession]:
        """Get a CLI session by ID."""
        with self.lock:
            return self.sessions.get(cli_session_id)

    def list_sessions(self, status_filter: Optional[str] = None) -> List[Dict]:
        """List all CLI sessions, optionally filtered by status."""
        with self.lock:
            sessions = list(self.sessions.values())

            if status_filter:
                sessions = [s for s in sessions if s.status == status_filter]

            return [s.to_dict() for s in sessions]

    def cancel_session(self, cli_session_id: str) -> bool:
        """Cancel a running CLI session."""
        with self.lock:
            session = self.sessions.get(cli_session_id)
            if not session:
                return False

            if session.status != "running":
                logger.warning(f"Cannot cancel session {cli_session_id} - status: {session.status}")
                return False

            session.cancel()

            # Cancel the asyncio task if it exists
            if session.task and not session.task.done():
                session.task.cancel()

            return True

    def complete_session(self, cli_session_id: str, status: str = "completed"):
        """Mark a session as completed or failed."""
        with self.lock:
            session = self.sessions.get(cli_session_id)
            if session:
                session.status = status
                logger.info(f"CLI session {cli_session_id} {status}")

    def cleanup_old_sessions(self, max_age_hours: int = 24):
        """Remove old completed/cancelled/failed sessions."""
        with self.lock:
            now = datetime.utcnow()
            to_remove = []

            for session_id, session in self.sessions.items():
                age_hours = (now - session.started_at).total_seconds() / 3600
                if session.status in ["completed", "cancelled", "failed"] and age_hours > max_age_hours:
                    to_remove.append(session_id)

            for session_id in to_remove:
                del self.sessions[session_id]
                logger.info(f"Cleaned up old CLI session: {session_id}")

            return len(to_remove)

    def get_stats(self) -> Dict[str, int]:
        """Get CLI session statistics."""
        with self.lock:
            stats = {
                "total": len(self.sessions),
                "running": sum(1 for s in self.sessions.values() if s.status == "running"),
                "completed": sum(1 for s in self.sessions.values() if s.status == "completed"),
                "cancelled": sum(1 for s in self.sessions.values() if s.status == "cancelled"),
                "failed": sum(1 for s in self.sessions.values() if s.status == "failed")
            }
            return stats


# Global CLI session manager instance
cli_session_manager = CLISessionManager()
