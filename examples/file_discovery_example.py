#!/usr/bin/env python3
"""
Example: Using X-Claude-File-Discovery Header

Demonstrates how to enable file discovery for non-research requests
that create files via Write tool.
"""

import asyncio
import httpx


async def example_with_file_discovery():
    """Example: Enable file discovery for a coding task."""

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/v1/chat/completions",
            json={
                "model": "claude-sonnet-4-5-20250929",
                "messages": [
                    {
                        "role": "user",
                        "content": "Erstelle eine einfache FastAPI App mit main.py und models.py"
                    }
                ],
                "stream": False,
                "enable_tools": True  # REQUIRED: Enable tools
            },
            headers={
                "X-Claude-Max-Turns": "10",
                "X-Claude-Allowed-Tools": "*",
                "X-Claude-File-Discovery": "enabled"  # ← Enable file discovery
            },
            timeout=300.0
        )

        response.raise_for_status()
        data = response.json()

        # Check for file metadata
        if "x_claude_metadata" in data:
            metadata = data["x_claude_metadata"]
            files = metadata.get("files_created", [])

            print(f"✅ Files discovered: {len(files)}")

            for file_info in files:
                print(f"\n📄 {file_info['relative_path']}")
                print(f"   Size: {file_info['size_bytes']} bytes")
                print(f"   MIME: {file_info['mime_type']}")

                # Decode content
                if "content_base64" in file_info:
                    import base64
                    content = base64.b64decode(file_info["content_base64"]).decode('utf-8')
                    print(f"   Content preview: {content[:100]}...")
        else:
            print("ℹ️  No files created (or file discovery disabled)")

        # Print assistant response
        print(f"\n🤖 Assistant: {data['choices'][0]['message']['content'][:200]}...")


async def example_without_file_discovery():
    """Example: Normal request without file discovery."""

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/v1/chat/completions",
            json={
                "model": "claude-sonnet-4-5-20250929",
                "messages": [
                    {
                        "role": "user",
                        "content": "Erstelle eine einfache FastAPI App mit main.py"
                    }
                ],
                "stream": False,
                "enable_tools": True
            },
            headers={
                "X-Claude-Max-Turns": "10",
                "X-Claude-Allowed-Tools": "*"
                # NO X-Claude-File-Discovery header
            },
            timeout=300.0
        )

        response.raise_for_status()
        data = response.json()

        # No x_claude_metadata expected
        print(f"✅ Response received (no file metadata)")
        print(f"🤖 Assistant: {data['choices'][0]['message']['content'][:200]}...")


async def main():
    print("=" * 70)
    print("Example 1: WITH File Discovery")
    print("=" * 70)
    await example_with_file_discovery()

    print("\n")
    print("=" * 70)
    print("Example 2: WITHOUT File Discovery")
    print("=" * 70)
    await example_without_file_discovery()


if __name__ == "__main__":
    asyncio.run(main())
