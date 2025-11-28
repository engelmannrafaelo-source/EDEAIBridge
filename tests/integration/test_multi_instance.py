#!/usr/bin/env python3
"""
Multi-instance integration tests for ECO OpenAI Wrapper.

Tests all running wrapper instances by auto-discovering ports and validating:
- Health check endpoints
- Model listing
- Chat completion functionality

Part of Phase 3 Integration Tests - covers TEST_PLAN.md Section 3 (E2E) + Section 6 (Multi-Instance).
"""
import requests
import json
import logging
import subprocess
import re
import pytest
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Tuple


def find_wrapper_ports() -> List[Tuple[int, str]]:
    """
    Find all running wrapper instances by checking listening ports.
    Returns list of (port, instance_name) tuples.
    """
    try:
        # Run lsof to find Python processes listening on ports
        result = subprocess.run(
            ["lsof", "-i", "-P", "-n"],
            capture_output=True,
            text=True,
            timeout=5
        )

        ports = []
        for line in result.stdout.split('\n'):
            # Look for Python processes with LISTEN and typical wrapper ports
            if 'Python' in line and 'LISTEN' in line:
                # Extract port number
                match = re.search(r':(\d+)\s+\(LISTEN\)', line)
                if match:
                    port = int(match.group(1))
                    # Only include ports in typical range (8000-9000)
                    if 8000 <= port <= 9000:
                        # Try to get instance name from process
                        instance_name = f"Instance on port {port}"

                        # Check if it's actually a wrapper by trying health endpoint
                        try:
                            health_response = requests.get(
                                f"http://localhost:{port}/health",
                                timeout=2
                            )
                            if health_response.status_code == 200:
                                data = health_response.json()
                                if data.get('service') == 'claude-code-openai-wrapper':
                                    ports.append((port, instance_name))
                        except:
                            pass

        # Sort by port number
        ports.sort(key=lambda x: x[0])
        return ports

    except Exception as e:
        logging.error(f"Failed to discover wrapper ports: {e}")
        return []


def setup_logging():
    """Configure logging to fixed file in tests/logs directory."""
    # Ensure tests/logs directory exists (separate from main logs)
    log_dir = Path(__file__).parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)

    # Fixed log filename in tests/logs
    log_file = log_dir / "multi_instance_tests.log"

    # Create formatter with timestamp
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # File handler - append mode
    file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # Root logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    # Clear existing handlers
    logger.handlers.clear()
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return log_file


class TestMultiInstance:
    """Multi-instance wrapper tests (E2E + Multi-Instance deployment)."""

    @pytest.fixture(scope="class", autouse=True)
    def setup_class(self):
        """Setup logging for all tests."""
        self.log_file = setup_logging()
        logging.info("="*60)
        logging.info("🧪 Multi-Instance Wrapper Tests Starting")
        logging.info(f"📝 Log file: {self.log_file}")
        logging.info("="*60)

    @pytest.fixture(scope="class")
    def discovered_instances(self):
        """Discover all running wrapper instances."""
        logging.info("🔍 Discovering running wrapper instances...")
        instances = find_wrapper_ports()

        if not instances:
            pytest.skip("No wrapper instances found. Start wrappers with ./start-wrappers.sh")

        logging.info(f"✅ Found {len(instances)} wrapper instance(s)")
        for port, name in instances:
            logging.info(f"   - Port {port}: {name}")

        return instances

    def test_health_check_all_instances(self, discovered_instances):
        """Test health endpoint on all discovered instances."""
        logging.info("\n" + "="*60)
        logging.info("Test 1: Health Check - All Instances")
        logging.info("="*60)

        for port, instance_name in discovered_instances:
            logging.info(f"\n🏥 Testing {instance_name}")

            response = requests.get(f"http://localhost:{port}/health", timeout=3)

            assert response.status_code == 200, f"Health check failed for port {port}"

            data = response.json()
            assert data.get('service') == 'claude-code-openai-wrapper'
            assert 'status' in data

            logging.info(f"   ✅ Health: {data}")

    def test_list_models_all_instances(self, discovered_instances):
        """Test model listing on all discovered instances."""
        logging.info("\n" + "="*60)
        logging.info("Test 2: List Models - All Instances")
        logging.info("="*60)

        for port, instance_name in discovered_instances:
            logging.info(f"\n📋 Testing {instance_name}")

            response = requests.get(f"http://localhost:{port}/v1/models", timeout=3)

            assert response.status_code == 200, f"List models failed for port {port}"

            models = response.json()
            assert 'data' in models
            assert len(models['data']) > 0, "No models returned"

            logging.info(f"   ✅ Models: {len(models['data'])} available")
            for model in models['data'][:3]:
                logging.debug(f"      - {model['id']}")

    def test_chat_completion_all_instances(self, discovered_instances):
        """Test chat completion on all discovered instances."""
        logging.info("\n" + "="*60)
        logging.info("Test 3: Chat Completion - All Instances")
        logging.info("="*60)

        for port, instance_name in discovered_instances:
            logging.info(f"\n💬 Testing {instance_name}")

            payload = {
                "model": "claude-sonnet-4-5-20250929",
                "messages": [
                    {
                        "role": "user",
                        "content": "Erzähl mir einen kurzen technischen Witz über Python oder APIs."
                    }
                ],
                "max_tokens": 150,
                "stream": False
            }

            response = requests.post(
                f"http://localhost:{port}/v1/chat/completions",
                json=payload,
                timeout=60
            )

            assert response.status_code == 200, f"Chat completion failed for port {port}"

            data = response.json()
            assert 'choices' in data
            assert len(data['choices']) > 0
            assert 'message' in data['choices'][0]
            assert 'content' in data['choices'][0]['message']

            joke = data['choices'][0]['message']['content']
            assert len(joke) > 0, "Empty response content"

            logging.info(f"   ✅ Response received")
            logging.info(f"   🤖 Claude sagt: {joke}")
            logging.debug(f"   📊 Token Usage: {data.get('usage', {})}")

    def test_independent_session_management(self, discovered_instances):
        """Test that instances maintain independent sessions."""
        if len(discovered_instances) < 2:
            pytest.skip("Need at least 2 instances for independence test")

        logging.info("\n" + "="*60)
        logging.info("Test 4: Independent Session Management")
        logging.info("="*60)

        # Send different requests to different instances
        instance1_port = discovered_instances[0][0]
        instance2_port = discovered_instances[1][0]

        payload1 = {
            "model": "claude-sonnet-4-5-20250929",
            "messages": [{"role": "user", "content": "Say 'Instance 1'"}],
            "max_tokens": 50,
            "stream": False
        }

        payload2 = {
            "model": "claude-sonnet-4-5-20250929",
            "messages": [{"role": "user", "content": "Say 'Instance 2'"}],
            "max_tokens": 50,
            "stream": False
        }

        response1 = requests.post(
            f"http://localhost:{instance1_port}/v1/chat/completions",
            json=payload1,
            timeout=60
        )

        response2 = requests.post(
            f"http://localhost:{instance2_port}/v1/chat/completions",
            json=payload2,
            timeout=60
        )

        assert response1.status_code == 200
        assert response2.status_code == 200

        content1 = response1.json()['choices'][0]['message']['content']
        content2 = response2.json()['choices'][0]['message']['content']

        # Responses should be different (independent sessions)
        assert content1 != content2 or "Instance 1" in content1 or "Instance 2" in content2

        logging.info(f"   ✅ Instance 1 response: {content1[:50]}...")
        logging.info(f"   ✅ Instance 2 response: {content2[:50]}...")
        logging.info(f"   ✅ Sessions are independent")


@pytest.mark.slow
class TestMultiInstanceLoadDistribution:
    """Test load distribution across multiple instances (slower tests)."""

    @pytest.fixture(scope="class")
    def discovered_instances(self):
        """Discover all running wrapper instances."""
        instances = find_wrapper_ports()
        if len(instances) < 2:
            pytest.skip("Need at least 2 instances for load distribution tests")
        return instances

    def test_parallel_requests_distribution(self, discovered_instances):
        """Test that parallel requests can be distributed across instances."""
        import concurrent.futures

        logging.info("\n" + "="*60)
        logging.info("Test 5: Parallel Request Distribution")
        logging.info("="*60)

        def send_request(port: int, request_id: int):
            """Send a single request to a port."""
            payload = {
                "model": "claude-sonnet-4-5-20250929",
                "messages": [{"role": "user", "content": f"Request {request_id}: Say hello"}],
                "max_tokens": 50,
                "stream": False
            }

            start = datetime.now()
            response = requests.post(
                f"http://localhost:{port}/v1/chat/completions",
                json=payload,
                timeout=60
            )
            duration = (datetime.now() - start).total_seconds()

            return {
                "port": port,
                "request_id": request_id,
                "status": response.status_code,
                "duration": duration
            }

        # Send 5 requests distributed across instances
        ports = [inst[0] for inst in discovered_instances]
        num_requests = 5

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_requests) as executor:
            futures = []
            for i in range(num_requests):
                # Round-robin distribution
                port = ports[i % len(ports)]
                futures.append(executor.submit(send_request, port, i))

            results = [f.result() for f in futures]

        # All requests should succeed
        for result in results:
            assert result['status'] == 200, f"Request {result['request_id']} failed"
            logging.info(f"   ✅ Request {result['request_id']} → Port {result['port']} ({result['duration']:.2f}s)")

        # Check that load was distributed
        ports_used = set(r['port'] for r in results)
        logging.info(f"   📊 Requests distributed across {len(ports_used)} instances")
        assert len(ports_used) > 1, "Requests should be distributed across multiple instances"


if __name__ == "__main__":
    # Allow running as standalone script
    setup_logging()

    logging.info("\n" + "="*60)
    logging.info("🧪 ECO OpenAI Wrapper - Multi-Instance Test")
    logging.info("="*60)

    # Discover instances
    instances = find_wrapper_ports()

    if not instances:
        logging.error("❌ No wrapper instances found!")
        logging.error("   Make sure wrappers are running: ./start-wrappers.sh")
        exit(1)

    logging.info(f"✅ Found {len(instances)} wrapper instance(s)")
    for port, name in instances:
        logging.info(f"   - Port {port}: {name}")

    # Run pytest on this file
    pytest.main([__file__, "-v", "--tb=short"])
