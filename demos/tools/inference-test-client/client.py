#!/usr/bin/env python3
"""
Inference Test Client

Tests AI inference services (both CPU and Gaudi paths) and measures performance metrics.

Usage:
    python client.py --url http://service-url --prompt "Hello world"
    python client.py --url http://service-url --benchmark
"""

import argparse
import json
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional
import statistics

try:
    import requests
except ImportError:
    print("Error: requests library not installed", file=sys.stderr)
    print("Install with: pip install requests", file=sys.stderr)
    sys.exit(1)


class InferenceClient:
    """Client for testing inference services"""

    def __init__(self, base_url: str, model: str, timeout: int = 60):
        """
        Initialize client

        Args:
            base_url: Base URL of inference service
            model: Model name
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.timeout = timeout

    def health_check(self) -> Dict:
        """
        Check service health

        Returns:
            Health check response
        """
        try:
            response = requests.get(
                f"{self.base_url}/health",
                timeout=10
            )
            response.raise_for_status()
            return {
                "status": "healthy",
                "status_code": response.status_code,
                "response": response.json() if response.content else {}
            }
        except requests.exceptions.RequestException as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }

    def list_models(self) -> Dict:
        """
        List available models

        Returns:
            Models list response
        """
        try:
            response = requests.get(
                f"{self.base_url}/v1/models",
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {
                "error": str(e)
            }

    def generate(
        self,
        prompt: str,
        max_tokens: int = 50,
        temperature: float = 0.7
    ) -> Dict:
        """
        Generate completion

        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature

        Returns:
            Result with metrics
        """
        payload = {
            "model": self.model,
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature
        }

        # Measure time to first token (TTFT)
        start_time = time.perf_counter()

        try:
            response = requests.post(
                f"{self.base_url}/v1/completions",
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()

            end_time = time.perf_counter()

            # Parse response
            result = response.json()

            # Calculate metrics
            duration = end_time - start_time
            usage = result.get('usage', {})
            prompt_tokens = usage.get('prompt_tokens', 0)
            completion_tokens = usage.get('completion_tokens', 0)
            total_tokens = usage.get('total_tokens', 0)

            # Tokens per second
            tokens_per_second = completion_tokens / duration if duration > 0 else 0

            # Time to first token (approximate)
            # For streaming this would be more accurate, but for completions
            # we use total duration as proxy
            ttft = duration

            generated_text = result['choices'][0]['text'] if result.get('choices') else ""

            return {
                "status": "success",
                "prompt": prompt,
                "generated_text": generated_text,
                "metrics": {
                    "ttft_seconds": round(ttft, 3),
                    "ttft_ms": round(ttft * 1000, 1),
                    "duration_seconds": round(duration, 3),
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                    "tokens_per_second": round(tokens_per_second, 2),
                    "throughput": f"{tokens_per_second:.2f} tok/s"
                },
                "timestamp": datetime.now().isoformat()
            }

        except requests.exceptions.Timeout:
            return {
                "status": "error",
                "error": "Request timeout",
                "prompt": prompt,
                "timestamp": datetime.now().isoformat()
            }
        except requests.exceptions.RequestException as e:
            return {
                "status": "error",
                "error": str(e),
                "prompt": prompt,
                "timestamp": datetime.now().isoformat()
            }
        except (KeyError, IndexError, ValueError) as e:
            return {
                "status": "error",
                "error": f"Failed to parse response: {e}",
                "prompt": prompt,
                "timestamp": datetime.now().isoformat()
            }

    def benchmark(
        self,
        prompts: Optional[List[str]] = None,
        num_requests: int = 10,
        max_tokens: int = 50
    ) -> Dict:
        """
        Run benchmark tests

        Args:
            prompts: List of prompts to use (optional)
            num_requests: Number of requests to make
            max_tokens: Maximum tokens per request

        Returns:
            Benchmark results with aggregated metrics
        """
        if prompts is None:
            # Default benchmark prompts
            prompts = [
                "The capital of France is",
                "Once upon a time in a land far away",
                "The quick brown fox jumps over",
                "In the beginning there was",
                "Hello, my name is"
            ]

        results = []
        latencies = []
        ttft_values = []
        throughput_values = []

        print(f"\nRunning benchmark: {num_requests} requests...", file=sys.stderr)

        for i in range(num_requests):
            # Cycle through prompts
            prompt = prompts[i % len(prompts)]

            result = self.generate(prompt, max_tokens=max_tokens)
            results.append(result)

            if result['status'] == 'success':
                metrics = result['metrics']
                latencies.append(metrics['duration_seconds'])
                ttft_values.append(metrics['ttft_seconds'])
                throughput_values.append(metrics['tokens_per_second'])

            # Progress indicator
            if (i + 1) % 5 == 0:
                print(f"  Completed {i + 1}/{num_requests} requests", file=sys.stderr)

        # Calculate statistics
        successful = len(latencies)
        failed = num_requests - successful

        if latencies:
            latencies_sorted = sorted(latencies)
            p50_idx = min(int(len(latencies_sorted) * 0.50), len(latencies_sorted) - 1)
            p95_idx = min(int(len(latencies_sorted) * 0.95), len(latencies_sorted) - 1)
            p99_idx = min(int(len(latencies_sorted) * 0.99), len(latencies_sorted) - 1)

            stats = {
                "requests_total": num_requests,
                "requests_successful": successful,
                "requests_failed": failed,
                "success_rate": round(successful / num_requests * 100, 1),
                "latency": {
                    "mean_seconds": round(statistics.mean(latencies), 3),
                    "median_seconds": round(statistics.median(latencies), 3),
                    "min_seconds": round(min(latencies), 3),
                    "max_seconds": round(max(latencies), 3),
                    "p50_seconds": round(latencies_sorted[p50_idx], 3),
                    "p95_seconds": round(latencies_sorted[p95_idx], 3),
                    "p99_seconds": round(latencies_sorted[p99_idx], 3)
                },
                "ttft": {
                    "mean_seconds": round(statistics.mean(ttft_values), 3),
                    "mean_ms": round(statistics.mean(ttft_values) * 1000, 1),
                    "median_seconds": round(statistics.median(ttft_values), 3),
                    "min_seconds": round(min(ttft_values), 3),
                    "max_seconds": round(max(ttft_values), 3)
                },
                "throughput": {
                    "mean_tokens_per_second": round(statistics.mean(throughput_values), 2),
                    "median_tokens_per_second": round(statistics.median(throughput_values), 2),
                    "min_tokens_per_second": round(min(throughput_values), 2),
                    "max_tokens_per_second": round(max(throughput_values), 2)
                }
            }
        else:
            stats = {
                "requests_total": num_requests,
                "requests_successful": 0,
                "requests_failed": num_requests,
                "success_rate": 0.0,
                "error": "All requests failed"
            }

        return {
            "benchmark": stats,
            "individual_results": results,
            "timestamp": datetime.now().isoformat()
        }


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Inference Test Client - Test AI inference services"
    )

    parser.add_argument(
        "--url",
        required=True,
        help="Base URL of inference service (e.g., http://localhost:8000)"
    )

    parser.add_argument(
        "--model",
        default="TinyLlama/TinyLlama-1.1B-Chat-v1.0",
        help="Model name (default: TinyLlama/TinyLlama-1.1B-Chat-v1.0)"
    )

    parser.add_argument(
        "--prompt",
        help="Prompt for single generation"
    )

    parser.add_argument(
        "--max-tokens",
        type=int,
        default=50,
        help="Maximum tokens to generate (default: 50)"
    )

    parser.add_argument(
        "--temperature",
        type=float,
        default=0.7,
        help="Sampling temperature (default: 0.7)"
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Request timeout in seconds (default: 60)"
    )

    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Run benchmark tests"
    )

    parser.add_argument(
        "--num-requests",
        type=int,
        default=10,
        help="Number of benchmark requests (default: 10)"
    )

    parser.add_argument(
        "--health-check",
        action="store_true",
        help="Check service health"
    )

    parser.add_argument(
        "--list-models",
        action="store_true",
        help="List available models"
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )

    args = parser.parse_args()

    # Create client
    client = InferenceClient(
        base_url=args.url,
        model=args.model,
        timeout=args.timeout
    )

    # Execute command
    if args.health_check:
        result = client.health_check()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            status = result.get('status', 'unknown')
            print(f"Health: {status}")
            if 'response' in result:
                print(f"Response: {json.dumps(result['response'], indent=2)}")

    elif args.list_models:
        result = client.list_models()
        print(json.dumps(result, indent=2))

    elif args.benchmark:
        result = client.benchmark(
            num_requests=args.num_requests,
            max_tokens=args.max_tokens
        )

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            # Human-readable output
            stats = result['benchmark']
            print("\n" + "=" * 60)
            print(" Benchmark Results")
            print("=" * 60)
            print(f"Total Requests:    {stats['requests_total']}")
            print(f"Successful:        {stats['requests_successful']}")
            print(f"Failed:            {stats['requests_failed']}")
            print(f"Success Rate:      {stats['success_rate']}%")

            if 'latency' in stats:
                print("\nLatency:")
                print(f"  Mean:    {stats['latency']['mean_seconds']}s")
                print(f"  Median:  {stats['latency']['median_seconds']}s")
                print(f"  P50:     {stats['latency']['p50_seconds']}s")
                print(f"  P95:     {stats['latency']['p95_seconds']}s")
                print(f"  P99:     {stats['latency']['p99_seconds']}s")

                print("\nTime to First Token (TTFT):")
                print(f"  Mean:    {stats['ttft']['mean_ms']}ms")
                print(f"  Median:  {stats['ttft']['median_seconds']}s")

                print("\nThroughput:")
                print(f"  Mean:    {stats['throughput']['mean_tokens_per_second']} tokens/s")
                print(f"  Median:  {stats['throughput']['median_tokens_per_second']} tokens/s")

    elif args.prompt:
        result = client.generate(
            prompt=args.prompt,
            max_tokens=args.max_tokens,
            temperature=args.temperature
        )

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if result['status'] == 'success':
                print(f"\nPrompt: {result['prompt']}")
                print(f"Generated: {result['generated_text']}")
                print(f"\nMetrics:")
                metrics = result['metrics']
                print(f"  TTFT:       {metrics['ttft_ms']}ms")
                print(f"  Duration:   {metrics['duration_seconds']}s")
                print(f"  Throughput: {metrics['throughput']}")
                print(f"  Tokens:     {metrics['completion_tokens']} generated")
            else:
                print(f"Error: {result['error']}", file=sys.stderr)
                sys.exit(1)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
