"""
Request Limiter Middleware - Prevent Memory Overload

Limits concurrent requests to prevent memory exhaustion.
Monitors system memory and rejects requests when unsafe.
"""

import asyncio
import psutil
from datetime import datetime
from typing import Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from config.logging_config import get_logger

logger = get_logger(__name__)


class RequestLimiter:
    """
    Tracks active requests and enforces concurrency limits.
    Monitors system memory to prevent overload.
    """

    def __init__(self, max_concurrent: int = 3, memory_threshold_percent: float = 90.0):
        """
        Args:
            max_concurrent: Maximum concurrent requests allowed (default: 3)
            memory_threshold_percent: Reject requests if memory usage exceeds this % (default: 90%)
        """
        self.max_concurrent = max_concurrent
        self.memory_threshold = memory_threshold_percent
        self.active_requests = 0
        self.total_requests = 0
        self.rejected_requests = 0
        self.lock = asyncio.Lock()

        logger.info("ℹ️  Request Limiter initialized:")
        logger.info(f"   Max concurrent: {max_concurrent}")
        logger.info(f"   Memory threshold: {memory_threshold_percent}%")

    async def can_accept_request(self) -> tuple[bool, Optional[str]]:
        """
        Check if new request can be accepted.

        Returns:
            (can_accept, reason_if_rejected)
        """
        async with self.lock:
            # Check concurrent limit
            if self.active_requests >= self.max_concurrent:
                reason = f"Max concurrent requests reached ({self.active_requests}/{self.max_concurrent})"
                logger.warning(f"🚫 {reason}")
                return False, reason

            # Check memory usage
            memory = psutil.virtual_memory()
            if memory.percent >= self.memory_threshold:
                reason = f"Memory threshold exceeded ({memory.percent:.1f}% > {self.memory_threshold}%)"
                logger.warning(f"🚫 {reason}")
                logger.warning(f"   Used: {memory.used / 1024**3:.1f}GB / {memory.total / 1024**3:.1f}GB")
                return False, reason

            return True, None

    async def acquire(self):
        """Mark request as active"""
        async with self.lock:
            self.active_requests += 1
            self.total_requests += 1

            memory = psutil.virtual_memory()
            logger.info(f"ℹ️  Request started (active: {self.active_requests}/{self.max_concurrent}, mem: {memory.percent:.1f}%)")

    async def release(self):
        """Mark request as completed"""
        async with self.lock:
            self.active_requests = max(0, self.active_requests - 1)

            memory = psutil.virtual_memory()
            logger.info(f"🟢 Request completed (active: {self.active_requests}/{self.max_concurrent}, mem: {memory.percent:.1f}%)")

    def get_stats(self) -> dict:
        """Get current limiter statistics"""
        memory = psutil.virtual_memory()
        return {
            'active_requests': self.active_requests,
            'max_concurrent': self.max_concurrent,
            'total_requests': self.total_requests,
            'rejected_requests': self.rejected_requests,
            'memory_usage_percent': memory.percent,
            'memory_used_gb': memory.used / 1024**3,
            'memory_total_gb': memory.total / 1024**3,
            'memory_threshold': self.memory_threshold
        }


class RequestLimiterMiddleware(BaseHTTPMiddleware):
    """
    FastAPI/Starlette middleware for request limiting.
    """

    def __init__(self, app, limiter: RequestLimiter):
        super().__init__(app)
        self.limiter = limiter

    async def dispatch(self, request, call_next):
        # Skip health checks and metrics
        if request.url.path in ['/health', '/metrics', '/stats']:
            return await call_next(request)

        # Check if request can be accepted
        can_accept, reason = await self.limiter.can_accept_request()

        if not can_accept:
            self.limiter.rejected_requests += 1
            logger.error(f"❌ Request rejected: {reason}")

            return JSONResponse(
                status_code=503,  # Service Unavailable
                content={
                    'error': 'Service Temporarily Unavailable',
                    'reason': reason,
                    'retry_after_seconds': 30,
                    'stats': self.limiter.get_stats()
                }
            )

        # Accept request
        await self.limiter.acquire()

        try:
            response = await call_next(request)
            return response
        finally:
            await self.limiter.release()


# Global limiter instance
limiter: Optional[RequestLimiter] = None


def get_limiter(max_concurrent: int = 3, memory_threshold: float = 90.0) -> RequestLimiter:
    """Get or create global limiter instance"""
    global limiter
    if limiter is None:
        limiter = RequestLimiter(max_concurrent, memory_threshold)
    return limiter
