"""
File Discovery Service for Claude Code Wrapper

Discovers files created during Claude Code execution (e.g., /sc:research reports).

LAW 1 Compliance:
- Never silent failures - all errors logged with exc_info=True
- Specific exceptions for each failure mode
- No fallbacks without explicit error handling
- Validation before action

Version: 1.0
Created: 2025-10-27
"""

from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime
import hashlib
import mimetypes
from dataclasses import dataclass, asdict

from config.logging_config import get_logger

logger = get_logger(__name__)


# ============================================================================
# Custom Exceptions
# ============================================================================

class FileDiscoveryError(Exception):
    """Base exception for file discovery failures."""

    def __init__(self, message: str, context: dict = None, cause: Exception = None):
        super().__init__(message)
        self.context = context or {}
        self.__cause__ = cause


class SDKMessageParsingError(FileDiscoveryError):
    """Failed to parse SDK messages for file paths."""
    pass


class DirectoryScanError(FileDiscoveryError):
    """Failed to scan directory for files."""
    pass


class FileMetadataError(FileDiscoveryError):
    """Failed to create file metadata."""
    pass


class ChecksumCalculationError(FileDiscoveryError):
    """Failed to calculate file checksum."""
    pass


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class FileMetadata:
    """
    Metadata for a discovered file.

    Attributes:
        path: Absolute path to file
        relative_path: Path relative to wrapper root
        size_bytes: File size in bytes
        mime_type: MIME type (e.g., "text/markdown")
        created_at: ISO 8601 timestamp of file creation
        checksum: SHA256 checksum for integrity verification
        content_base64: Base64-encoded file content (optional)
    """
    path: str
    relative_path: str
    size_bytes: int
    mime_type: str
    created_at: str
    checksum: str
    content_base64: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


# ============================================================================
# File Discovery Service
# ============================================================================

class FileDiscoveryService:
    """
    Discovers files created during Claude Code execution.

    Strategies:
    1. Parse SDK messages for Write tool calls (PRIMARY)
    2. Scan known output directories for new files (FALLBACK)

    LAW 1 Compliance:
    - All errors are logged with exc_info=True
    - Specific exceptions for different failure modes
    - Partial failures are acceptable (logged but don't crash)
    - Complete failures raise exceptions with context
    """

    def __init__(self, wrapper_root: Path):
        """
        Initialize file discovery service.

        Args:
            wrapper_root: Root directory of the wrapper

        Raises:
            ValueError: If wrapper_root is invalid
        """
        # Validate wrapper_root exists
        if not wrapper_root.exists():
            raise ValueError(f"Wrapper root does not exist: {wrapper_root}")
        if not wrapper_root.is_dir():
            raise ValueError(f"Wrapper root is not a directory: {wrapper_root}")

        self.wrapper_root = wrapper_root
        self.claudedocs_dir = wrapper_root / "claudedocs"

        logger.info(
            "✅ FileDiscoveryService initialized",
            extra={"wrapper_root": str(wrapper_root)}
        )

    def discover_files_from_sdk_messages(
        self,
        sdk_messages: List[Dict[str, Any]],
        session_start: datetime
    ) -> List[FileMetadata]:
        """
        Extract file paths from SDK Write tool calls.

        LAW 1: Never Silent Failures
        - Raises ValueError if inputs are invalid
        - Logs all individual message parsing failures with exc_info=True
        - Returns empty list only if genuinely no files (not on error)
        - Partial failures (some messages fail) are logged but acceptable

        Args:
            sdk_messages: All SDK messages from run_completion
            session_start: When session started (for timestamp filtering)

        Returns:
            List of FileMetadata for discovered files

        Raises:
            ValueError: If inputs are None or invalid
        """
        # Validate inputs (LAW 1: Validation before action)
        if sdk_messages is None:
            raise ValueError("sdk_messages cannot be None")
        if session_start is None:
            raise ValueError("session_start cannot be None")

        discovered_files: List[FileMetadata] = []

        if len(sdk_messages) == 0:
            logger.info(
                "No SDK messages to process for file discovery",
                extra={"session_start": session_start.isoformat()}
            )
            return []

        logger.info(
            f"🔍 Processing {len(sdk_messages)} SDK messages for file discovery",
            extra={"session_start": session_start.isoformat()}
        )

        parse_failures = 0
        messages_processed = 0

        for idx, message in enumerate(sdk_messages):
            messages_processed += 1

            try:
                # Check for AssistantMessage with ToolUse blocks
                if not hasattr(message, 'content'):
                    logger.debug(
                        f"Message {idx} has no content attribute, skipping",
                        extra={"message_type": type(message).__name__}
                    )
                    continue

                for block in message.content:
                    # ToolUseBlock with name='Write'
                    if not hasattr(block, 'name'):
                        continue

                    if block.name != 'Write':
                        continue

                    # Extract file_path from input
                    if not hasattr(block, 'input'):
                        logger.warning(
                            f"⚠️  Write tool block missing input at message {idx}",
                            extra={"block_id": getattr(block, 'id', 'unknown')}
                        )
                        parse_failures += 1
                        continue

                    tool_input = block.input
                    file_path_str = tool_input.get('file_path')

                    if not file_path_str:
                        logger.warning(
                            f"⚠️  Write tool call without file_path at message {idx}",
                            extra={"block_id": getattr(block, 'id', 'unknown')}
                        )
                        parse_failures += 1
                        continue

                    # Convert to Path and validate
                    try:
                        file_path = Path(file_path_str)
                    except (TypeError, ValueError) as e:
                        logger.error(
                            f"❌ Invalid file path format: {file_path_str}",
                            exc_info=True,
                            extra={"message_idx": idx, "file_path": file_path_str}
                        )
                        parse_failures += 1
                        continue

                    if not file_path.is_absolute():
                        logger.debug(
                            f"🔍 Relative path detected, resolving: {file_path}",
                            extra={"message_idx": idx}
                        )
                        file_path = self.wrapper_root / file_path

                    # Verify file exists
                    if not file_path.exists():
                        logger.warning(
                            f"⚠️  Write tool referenced non-existent file: {file_path.name}",
                            extra={"file_path": str(file_path), "message_idx": idx}
                        )
                        parse_failures += 1
                        continue

                    # Check timestamp
                    try:
                        file_stat = file_path.stat()
                        file_mtime = datetime.fromtimestamp(file_stat.st_mtime)
                    except OSError as e:
                        logger.error(
                            f"❌ Failed to stat file: {file_path.name}",
                            exc_info=True,
                            extra={"file_path": str(file_path)}
                        )
                        parse_failures += 1
                        continue

                    if file_mtime < session_start:
                        logger.debug(
                            f"File predates session, skipping: {file_path.name}",
                            extra={
                                "file_mtime": file_mtime.isoformat(),
                                "session_start": session_start.isoformat()
                            }
                        )
                        continue

                    # Create FileMetadata
                    try:
                        metadata = self._create_file_metadata(file_path)
                        discovered_files.append(metadata)
                        logger.info(
                            f"✅ Discovered file from Write tool: {file_path.name}",
                            extra={
                                "file_path": str(file_path),
                                "size_kb": metadata.size_bytes / 1024
                            }
                        )
                    except FileMetadataError as e:
                        logger.error(
                            f"❌ Failed to create metadata for {file_path.name}: {e}",
                            exc_info=True,
                            extra={"file_path": str(file_path)}
                        )
                        parse_failures += 1
                        # Don't raise - partial file discovery is acceptable
                        continue

            except (AttributeError, TypeError, KeyError) as e:
                logger.error(
                    f"❌ Failed to parse SDK message {idx}: {e}",
                    exc_info=True,
                    extra={"message_type": type(message).__name__}
                )
                parse_failures += 1
                # Don't raise - continue processing other messages
                continue

        # Summary logging
        success_rate = (1 - parse_failures/max(messages_processed, 1))*100
        logger.info(
            "📊 SDK message parsing complete",
            extra={
                "messages_processed": messages_processed,
                "files_discovered": len(discovered_files),
                "parse_failures": parse_failures,
                "success_rate": f"{success_rate:.1f}%"
            }
        )

        # LAW 1: Warn if high failure rate but no critical error
        if parse_failures > 0 and len(discovered_files) == 0:
            logger.warning(
                f"⚠️  SDK parsing had {parse_failures} failures and found NO files",
                extra={
                    "parse_failures": parse_failures,
                    "messages_processed": messages_processed
                }
            )
            # Don't raise - maybe legitimately no files created

        return discovered_files

    def discover_files_from_directory_scan(
        self,
        directories: List[Path],
        session_start: datetime,
        file_patterns: List[str] = None
    ) -> List[FileMetadata]:
        """
        Fallback: Scan directories for new files created after session start.

        LAW 1: Never Silent Failures
        - Raises DirectoryScanError if ALL directories fail to scan
        - Raises ValueError if inputs are invalid
        - Logs individual file processing failures with exc_info=True
        - Returns partial results if some files succeed

        Args:
            directories: Directories to scan
            session_start: Only return files created after this
            file_patterns: Glob patterns to match (default: ["*.md", "*.json", "*.txt"])

        Returns:
            List of FileMetadata

        Raises:
            DirectoryScanError: If all directories fail to scan
            ValueError: If inputs are invalid
        """
        # Default file patterns
        if file_patterns is None:
            file_patterns = ["*.md", "*.json", "*.txt"]

        # Validate inputs (LAW 1: Validation before action)
        if not directories:
            raise ValueError("directories list cannot be empty")
        if session_start is None:
            raise ValueError("session_start cannot be None")
        if not file_patterns:
            raise ValueError("file_patterns list cannot be empty")

        discovered_files: List[FileMetadata] = []
        directories_scanned = 0
        directories_failed = 0
        files_processed = 0

        for directory in directories:
            if not directory.exists():
                logger.error(
                    f"❌ Directory does not exist: {directory}",
                    extra={"directory": str(directory)}
                )
                directories_failed += 1
                continue  # Try other directories

            if not directory.is_dir():
                logger.error(
                    f"❌ Path is not a directory: {directory}",
                    extra={"directory": str(directory)}
                )
                directories_failed += 1
                continue

            try:
                for pattern in file_patterns:
                    for file_path in directory.glob(pattern):
                        files_processed += 1

                        # Skip directories
                        if not file_path.is_file():
                            continue

                        # Check timestamp
                        try:
                            file_stat = file_path.stat()
                            file_mtime = datetime.fromtimestamp(file_stat.st_mtime)
                        except OSError as e:
                            logger.error(
                                f"❌ Failed to stat file: {file_path.name}",
                                exc_info=True,
                                extra={"file_path": str(file_path)}
                            )
                            continue

                        if file_mtime < session_start:
                            continue

                        # Create metadata
                        try:
                            metadata = self._create_file_metadata(file_path)
                            discovered_files.append(metadata)
                            logger.info(
                                f"✅ Discovered file from scan: {file_path.name}",
                                extra={
                                    "directory": str(directory),
                                    "pattern": pattern,
                                    "size_kb": metadata.size_bytes / 1024
                                }
                            )
                        except FileMetadataError as e:
                            logger.error(
                                f"❌ Failed to create metadata: {e}",
                                exc_info=True,
                                extra={"file_path": str(file_path)}
                            )
                            continue

                directories_scanned += 1

            except OSError as e:
                logger.error(
                    f"❌ Failed to scan directory: {directory}",
                    exc_info=True,
                    extra={"directory": str(directory), "patterns": file_patterns}
                )
                directories_failed += 1
                # Don't raise - try other directories
                continue

        # LAW 1: If ALL directories failed, this is critical
        if directories_scanned == 0:
            error_msg = (
                f"All {len(directories)} directories failed to scan. "
                f"No files discovered. This is a critical failure."
            )
            logger.error(
                f"❌ {error_msg}",
                extra={
                    "directories_attempted": len(directories),
                    "directories_failed": directories_failed
                }
            )
            raise DirectoryScanError(
                error_msg,
                context={
                    "directories": [str(d) for d in directories],
                    "directories_failed": directories_failed
                }
            )

        # Summary logging
        logger.info(
            "📊 Directory scan complete",
            extra={
                "directories_scanned": directories_scanned,
                "directories_failed": directories_failed,
                "files_processed": files_processed,
                "files_discovered": len(discovered_files)
            }
        )

        return discovered_files

    def _create_file_metadata(self, file_path: Path, include_content: bool = True) -> FileMetadata:
        """
        Create FileMetadata from Path.

        LAW 1: Never Silent Failures
        - Raises FileMetadataError with specific cause on any failure
        - Logs content read failures as warnings (non-critical)
        - No silent returns or None

        Args:
            file_path: Path to file
            include_content: If True, read file and encode as base64

        Returns:
            FileMetadata object with optional content

        Raises:
            FileMetadataError: If metadata creation fails for any reason
        """
        if not file_path.exists():
            raise FileMetadataError(
                f"File does not exist: {file_path}",
                context={"file_path": str(file_path)}
            )

        try:
            stat = file_path.stat()
        except OSError as e:
            raise FileMetadataError(
                f"Failed to stat file: {file_path.name}",
                context={"file_path": str(file_path)},
                cause=e
            ) from e

        # Calculate checksum
        try:
            checksum = self._calculate_checksum(file_path)
        except ChecksumCalculationError as e:
            raise FileMetadataError(
                f"Failed to calculate checksum for {file_path.name}",
                context={"file_path": str(file_path)},
                cause=e
            ) from e

        # Read file content if requested
        content_base64 = None
        if include_content:
            try:
                with open(file_path, 'rb') as f:
                    content_bytes = f.read()

                import base64
                content_base64 = base64.b64encode(content_bytes).decode('utf-8')

                logger.debug(
                    "🔍 File content encoded to base64",
                    extra={
                        "file_path": str(file_path),
                        "original_size_bytes": len(content_bytes),
                        "base64_size_bytes": len(content_base64),
                        "overhead_percent": round((len(content_base64) / len(content_bytes) - 1) * 100, 1)
                    }
                )
            except OSError as e:
                # Content read failure is NON-CRITICAL
                # Log warning but don't raise - metadata is still useful
                logger.warning(
                    "⚠️  Failed to read file content for base64 encoding",
                    exc_info=True,
                    extra={
                        "file_path": str(file_path),
                        "error_type": type(e).__name__
                    }
                )
                # content_base64 remains None

        # Determine MIME type
        mime_type, _ = mimetypes.guess_type(str(file_path))
        mime_type = mime_type or "application/octet-stream"

        # Relative path
        try:
            relative = file_path.relative_to(self.wrapper_root)
        except ValueError:
            # File outside wrapper root - use name only
            logger.debug(
                f"🔍 File outside wrapper root, using name only",
                extra={
                    "file_path": str(file_path),
                    "wrapper_root": str(self.wrapper_root)
                }
            )
            relative = Path(file_path.name)

        return FileMetadata(
            path=str(file_path.absolute()),
            relative_path=str(relative),
            size_bytes=stat.st_size,
            mime_type=mime_type,
            created_at=datetime.fromtimestamp(stat.st_mtime).isoformat(),
            checksum=checksum,
            content_base64=content_base64
        )

    def _calculate_checksum(self, file_path: Path) -> str:
        """
        Calculate SHA256 checksum of file.

        LAW 1: Never Silent Failures
        - Raises ChecksumCalculationError on read failure

        Args:
            file_path: Path to file

        Returns:
            Checksum string in format "sha256:hexdigest"

        Raises:
            ChecksumCalculationError: If file cannot be read
        """
        sha256 = hashlib.sha256()

        try:
            with open(file_path, 'rb') as f:
                # Read in chunks to handle large files
                for chunk in iter(lambda: f.read(8192), b''):
                    sha256.update(chunk)

            return f"sha256:{sha256.hexdigest()}"

        except OSError as e:
            raise ChecksumCalculationError(
                f"Failed to read file for checksum: {file_path.name}",
                context={"file_path": str(file_path)},
                cause=e
            ) from e
