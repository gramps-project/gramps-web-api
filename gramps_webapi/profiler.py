#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2025      David Straub
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#

"""API endpoint profiling utilities."""

import json
import os
import statistics
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import click

# Timeout for HTTP requests in seconds.
# Set to 2 minutes to accommodate slow Gramps Web installations.
REQUEST_TIMEOUT = 120


def fetch_installation_info(
    client, headers: Dict[str, str], url: Optional[str]
) -> Dict:
    """Fetch installation information from the metadata endpoint.

    Returns a dictionary with database backend, object counts, and other metadata.
    """
    try:
        if url:
            # Remote HTTP
            import requests

            response = requests.get(
                f"{url.rstrip('/')}/api/metadata/",
                headers=headers,
                timeout=30,
            )
            if response.status_code != 200:
                return {
                    "error": f"Failed to fetch metadata (status {response.status_code})"
                }
            metadata = response.json()
        else:
            # Local test client
            rv = client.get("/api/metadata/", headers=headers)
            if rv.status_code != 200:
                return {"error": f"Failed to fetch metadata (status {rv.status_code})"}
            metadata = rv.json

        # Extract relevant information
        info = {
            "database": metadata.get("database", {}),
            "object_counts": metadata.get("object_counts", {}),
            "gramps_version": metadata.get("gramps", {}).get("version", "unknown"),
            "webapi_version": metadata.get("gramps_webapi", {}).get(
                "version", "unknown"
            ),
            "server": metadata.get("server", {}),
            "default_person_handle": metadata.get("default_person"),
        }
        return info
    except Exception as e:
        return {"error": f"Failed to fetch installation info: {e}"}


def print_installation_info(info: Dict):
    """Print installation information in a formatted way."""
    click.echo()
    click.echo("=" * 90)
    click.echo("INSTALLATION INFORMATION")
    click.echo("=" * 90)
    click.echo()

    if "error" in info:
        click.echo(f"⚠ Warning: {info['error']}")
        click.echo()
        return

    # Database information
    db_info = info.get("database", {})
    click.echo("Database:")
    click.echo(f"  Backend:     {db_info.get('type', 'unknown')}")
    if "version" in db_info:
        click.echo(f"  Version:     {db_info.get('version')}")
    click.echo()

    # Object counts
    counts = info.get("object_counts", {})
    if counts:
        click.echo("Object Counts:")
        click.echo(f"  People:       {counts.get('people', 0):,}")
        click.echo(f"  Families:     {counts.get('families', 0):,}")
        click.echo(f"  Events:       {counts.get('events', 0):,}")
        click.echo(f"  Places:       {counts.get('places', 0):,}")
        click.echo(f"  Sources:      {counts.get('sources', 0):,}")
        click.echo(f"  Citations:    {counts.get('citations', 0):,}")
        click.echo(f"  Repositories: {counts.get('repositories', 0):,}")
        click.echo(f"  Media:        {counts.get('media', 0):,}")
        click.echo(f"  Notes:        {counts.get('notes', 0):,}")
        click.echo(f"  Tags:         {counts.get('tags', 0):,}")

        # Calculate total
        total = sum(counts.values())
        click.echo(f"  Total:        {total:,}")
        click.echo()

    # Software versions
    click.echo("Software:")
    click.echo(f"  Gramps:       {info.get('gramps_version', 'unknown')}")
    click.echo(f"  Gramps WebAPI: {info.get('webapi_version', 'unknown')}")
    click.echo()

    # Server features
    server = info.get("server", {})
    if server:
        features = []
        if server.get("multi_tree"):
            features.append("multi-tree")
        if server.get("task_queue"):
            features.append("task queue")
        if server.get("semantic_search"):
            features.append("semantic search")
        if server.get("chat"):
            features.append("AI chat")
        if server.get("ocr"):
            features.append("OCR")

        if features:
            click.echo(f"Features:      {', '.join(features)}")
            click.echo()


def get_default_person_gramps_id(
    client, headers: Dict[str, str], url: Optional[str], person_handle: Optional[str]
) -> Optional[str]:
    """Fetch the Gramps ID for a person handle.

    Returns the gramps_id or None if not found.
    """
    if not person_handle:
        return None

    try:
        if url:
            # Remote HTTP
            import requests

            response = requests.get(
                f"{url.rstrip('/')}/api/people/{person_handle}?keys=gramps_id",
                headers=headers,
                timeout=30,
            )
            if response.status_code != 200:
                return None
            data = response.json()
        else:
            # Local test client
            rv = client.get(
                f"/api/people/{person_handle}?keys=gramps_id", headers=headers
            )
            if rv.status_code != 200:
                return None
            data = rv.json

        return data.get("gramps_id")
    except Exception:
        return None


def get_default_endpoints(
    default_person_gramps_id: Optional[str] = None,
) -> List[Dict[str, str]]:
    """Get the default list of endpoints to profile.

    Returns a list of endpoint definitions with 'name', 'method', and 'path'.
    You can customize this list to add or remove endpoints.
    """
    endpoints = [
        {"name": "Ready", "method": "GET", "path": "/ready"},
        {"name": "Metadata", "method": "GET", "path": "/api/metadata/"},
    ]

    # Add person endpoints if we have a default person
    if default_person_gramps_id:
        endpoints.extend(
            [
                {
                    "name": "Person (minimal)",
                    "method": "GET",
                    "path": f"/api/people/?gramps_id={default_person_gramps_id}&keys=gramps_id",
                },
                {
                    "name": "Person (full)",
                    "method": "GET",
                    "path": f"/api/people/?gramps_id={default_person_gramps_id}&locale=en&profile=all&extend=all",
                },
                {
                    "name": "Ancestor Tree (3 gen)",
                    "method": "GET",
                    "path": f"/api/people/?rules=%7B%22function%22%3A%22or%22%2C%22rules%22%3A%5B%7B%22name%22%3A%22IsLessThanNthGenerationAncestorOf%22%2C%22values%22%3A%5B%22{default_person_gramps_id}%22%2C4%5D%7D%2C%7B%22name%22%3A%22IsLessThanNthGenerationDescendantOf%22%2C%22values%22%3A%5B%22{default_person_gramps_id}%22%2C2%5D%7D%5D%7D&locale=de&profile=self&extend=event_ref_list%2Cprimary_parent_family%2Cfamily_list",
                },
                {
                    "name": "Ancestor Tree (8 gen)",
                    "method": "GET",
                    "path": f"/api/people/?rules=%7B%22function%22%3A%22or%22%2C%22rules%22%3A%5B%7B%22name%22%3A%22IsLessThanNthGenerationAncestorOf%22%2C%22values%22%3A%5B%22{default_person_gramps_id}%22%2C9%5D%7D%2C%7B%22name%22%3A%22IsLessThanNthGenerationDescendantOf%22%2C%22values%22%3A%5B%22{default_person_gramps_id}%22%2C2%5D%7D%5D%7D&locale=de&profile=self&extend=event_ref_list%2Cprimary_parent_family%2Cfamily_list",
                },
            ]
        )

    # Add remaining endpoints
    endpoints.extend(
        [
            {
                "name": "People List",
                "method": "GET",
                "path": "/api/people/?locale=de&profile=self&keys=gramps_id,profile,change&page=1&pagesize=50",
            },
            {
                "name": "Events by Date",
                "method": "GET",
                "path": "/api/events/?dates=*/6/*&profile=all&sort=-date&locale=en&pagesize=10&page=1",
            },
            {
                "name": "Places List",
                "method": "GET",
                "path": "/api/places/?locale=de&profile=self&backlinks=1",
            },
            {
                "name": "Search",
                "method": "GET",
                "path": "/api/search/?query=birth&locale=de&profile=all&page=1&pagesize=20",
            },
            {
                "name": "Recent Changes",
                "method": "GET",
                "path": "/api/search/?query=*&sort=-change&locale=en&profile=all&page=1&pagesize=50",
            },
        ]
    )

    return endpoints


def profile_endpoint_with_test_client(
    client,
    headers: Dict[str, str],
    method: str,
    path: str,
    iterations: int,
    warmup: int,
) -> Tuple[List[float], List[int], Optional[int]]:
    """Profile an endpoint using Flask test client.

    Returns (response_times, status_codes, object_count).
    """
    response_times = []
    status_codes = []
    object_count = None

    # Warmup runs
    for _ in range(warmup):
        if method == "GET":
            client.get(path, headers=headers)
        else:
            client.post(path, headers=headers)

    # Actual profiling runs
    for _ in range(iterations):
        start_time = time.perf_counter()
        if method == "GET":
            rv = client.get(path, headers=headers)
        else:
            rv = client.post(path, headers=headers)
        end_time = time.perf_counter()

        response_times.append(end_time - start_time)
        status_codes.append(rv.status_code)

        # Count objects in response (only from first successful request)
        if object_count is None and rv.status_code == 200:
            try:
                data = rv.json
                if isinstance(data, list):
                    object_count = len(data)
                elif isinstance(data, dict) and "results" in data:
                    object_count = len(data["results"])
            except Exception:
                # Best-effort object counting only; ignore any errors when
                # parsing or inspecting the response so profiling can proceed.
                pass

    return response_times, status_codes, object_count


def profile_endpoint_with_http(
    url: str,
    headers: Dict[str, str],
    method: str,
    path: str,
    iterations: int,
    warmup: int,
) -> Tuple[List[float], List[int], Optional[int]]:
    """Profile an endpoint using HTTP requests.

    Returns (response_times, status_codes, object_count).
    """
    try:
        import requests
    except ImportError:
        click.echo(
            "Error: 'requests' library is required for remote profiling. "
            "Install it with: pip install requests"
        )
        sys.exit(1)

    response_times = []
    status_codes = []
    object_count = None
    full_url = f"{url.rstrip('/')}{path}"

    # Warmup runs
    for _ in range(warmup):
        try:
            if method == "GET":
                requests.get(full_url, headers=headers, timeout=REQUEST_TIMEOUT)
            else:
                requests.post(full_url, headers=headers, timeout=REQUEST_TIMEOUT)
        except requests.exceptions.Timeout:
            click.echo(
                f"\nWarning: Warmup request timed out after {REQUEST_TIMEOUT}s. "
                "Continuing with profiling..."
            )
        except requests.exceptions.RequestException as e:
            click.echo(f"\nWarning: Warmup request failed: {e}")

    # Actual profiling runs
    for _ in range(iterations):
        start_time = time.perf_counter()
        try:
            if method == "GET":
                response = requests.get(
                    full_url, headers=headers, timeout=REQUEST_TIMEOUT
                )
            else:
                response = requests.post(
                    full_url, headers=headers, timeout=REQUEST_TIMEOUT
                )
            end_time = time.perf_counter()
            response_times.append(end_time - start_time)
            status_codes.append(response.status_code)

            # Count objects in response (only from first successful request)
            if object_count is None and response.status_code == 200:
                try:
                    data = response.json()
                    if isinstance(data, list):
                        object_count = len(data)
                    elif isinstance(data, dict) and "results" in data:
                        object_count = len(data["results"])
                except Exception:
                    # Best-effort object counting: ignore JSON/structure issues so profiling can continue.
                    pass
        except requests.exceptions.Timeout:
            end_time = time.perf_counter()
            response_times.append(end_time - start_time)
            status_codes.append(504)  # Gateway Timeout
            click.echo(
                f"\nWarning: Request timed out after {REQUEST_TIMEOUT}s (recorded as 504)"
            )
        except requests.exceptions.RequestException as e:
            end_time = time.perf_counter()
            response_times.append(end_time - start_time)
            status_codes.append(500)  # Internal Server Error
            click.echo(f"\nWarning: Request failed: {e} (recorded as 500)")

    return response_times, status_codes, object_count


def authenticate_remote(url: str, username: str, password: str) -> str:
    """Authenticate with a remote server and return access token."""
    try:
        import requests
    except ImportError:
        click.echo(
            "Error: 'requests' library is required for remote profiling.\n"
            "Install it with: pip install requests"
        )
        sys.exit(1)

    auth_url = f"{url.rstrip('/')}/api/token/"
    try:
        response = requests.post(
            auth_url,
            json={"username": username, "password": password},
            timeout=30,  # Authentication should be quick
        )
        if response.status_code != 200:
            click.echo(f"Error: Authentication failed (status {response.status_code})")
            click.echo(response.text)
            sys.exit(1)
        try:
            data = response.json()
        except ValueError as e:
            click.echo(f"Error: Failed to parse authentication response as JSON: {e}")
            click.echo(response.text)
            sys.exit(1)
        token = data.get("access_token")
        if not token:
            click.echo("Error: Authentication response did not contain 'access_token'.")
            click.echo(response.text)
            sys.exit(1)
        return token
    except requests.exceptions.Timeout:
        click.echo(
            f"Error: Authentication request timed out after 30 seconds. "
            f"Check that the server at {url} is responding."
        )
        sys.exit(1)
    except requests.exceptions.ConnectionError as e:
        click.echo(f"Error: Failed to connect to {url}: {e}")
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        click.echo(f"Error: Failed to authenticate: {e}")
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: Unexpected error during authentication: {e}")
        sys.exit(1)


def authenticate_local(username: str, password: str) -> Tuple[Any, str]:
    """Authenticate with test client and return (client, token)."""
    # Ensure caches are disabled
    os.environ["DISABLE_CACHES"] = "1"

    # Import here to avoid circular dependency
    from .app import create_app

    # Create app with caching disabled
    app = create_app()
    client = app.test_client()

    # Authenticate
    rv = client.post("/api/token/", json={"username": username, "password": password})
    if rv.status_code != 200:
        click.echo(f"Error: Authentication failed (status {rv.status_code})")
        click.echo(rv.data.decode())
        sys.exit(1)

    token = rv.json.get("access_token")
    if not token:
        click.echo("Error: Authentication response did not contain 'access_token'.")
        click.echo(rv.data.decode())
        sys.exit(1)

    return client, token


def calculate_statistics(response_times: List[float], status_codes: List[int]) -> Dict:
    """Calculate statistics from profiling results."""
    if not response_times:
        return {
            "mean_ms": 0.0,
            "median_ms": 0.0,
            "stddev_ms": 0.0,
            "min_ms": 0.0,
            "max_ms": 0.0,
            "all_success": False,
        }

    mean_time = statistics.mean(response_times)
    median_time = statistics.median(response_times)
    stddev_time = statistics.stdev(response_times) if len(response_times) > 1 else 0.0
    min_time = min(response_times)
    max_time = max(response_times)
    all_success = all(code == 200 for code in status_codes)

    return {
        "mean_ms": mean_time * 1000,
        "median_ms": median_time * 1000,
        "stddev_ms": stddev_time * 1000,
        "min_ms": min_time * 1000,
        "max_ms": max_time * 1000,
        "all_success": all_success,
    }


def print_results_table(results: List[Dict]):
    """Print profiling results in a formatted table."""
    click.echo()
    click.echo("=" * 105)
    click.echo("PROFILING RESULTS")
    click.echo("=" * 105)
    click.echo()
    click.echo(
        f"{'Endpoint':<25} {'Objects':<9} {'Median (ms)':<12} {'Mean (ms)':<12} {'Std Dev':<10} {'Min (ms)':<10} {'Max (ms)':<10}"
    )
    click.echo("-" * 105)

    for result in results:
        status_marker = "✓" if result["all_success"] else "✗"
        obj_count = result.get("object_count")
        obj_str = str(obj_count) if obj_count is not None else "-"
        click.echo(
            f"{status_marker} {result['name']:<23} "
            f"{obj_str:<9} "
            f"{result['median_ms']:<12.2f} {result['mean_ms']:<12.2f} "
            f"{result['stddev_ms']:<10.2f} {result['min_ms']:<10.2f} {result['max_ms']:<10.2f}"
        )

    click.echo()

    # Calculate and show totals
    total_median = sum(r["median_ms"] for r in results)
    total_mean = sum(r["mean_ms"] for r in results)
    click.echo(f"Total median time: {total_median:.2f} ms")
    click.echo(f"Total mean time:   {total_mean:.2f} ms")
    click.echo()

    # Show warnings if any requests failed
    failed_endpoints = [r for r in results if not r["all_success"]]
    if failed_endpoints:
        click.echo("⚠ Warning: Some requests failed:")
        for result in failed_endpoints:
            unique_codes = set(result["status_codes"])
            timeout_count = sum(1 for code in result["status_codes"] if code == 504)
            error_count = sum(
                1 for code in result["status_codes"] if code not in [200, 504]
            )

            error_parts = [f"status codes {unique_codes}"]
            if timeout_count > 0:
                error_parts.append(f"{timeout_count} timeout(s)")
            if error_count > 0:
                error_parts.append(f"{error_count} error(s)")

            click.echo(f"  - {result['name']}: {', '.join(error_parts)}")
        click.echo()


def save_results_json(
    results: List[Dict],
    output_path: str,
    tree: str,
    url: Optional[str],
    iterations: int,
    warmup: int,
    installation_info: Dict,
):
    """Save profiling results to a JSON file."""
    output_data = {
        "tree": tree,
        "mode": "remote" if url else "local",
        "url": url,
        "iterations": iterations,
        "warmup": warmup,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "installation": installation_info,
        "results": results,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)

    click.echo(f"Results saved to: {output_path}")
    click.echo()


def run_profiler(
    tree: str,
    username: str,
    password: str,
    url: Optional[str],
    iterations: int,
    warmup: int,
    output: Optional[str],
):
    """Run the profiler with the given parameters."""
    click.echo(f"Tree: {tree}")
    click.echo(f"Mode: {'Remote HTTP' if url else 'Local test client'}")
    click.echo(f"Warmup runs: {warmup}")
    click.echo()

    # Authenticate and get token
    if url:
        token = authenticate_remote(url, username, password)
        client = None
    else:
        client, token = authenticate_local(username, password)

    headers = {"Authorization": f"Bearer {token}"}

    # Fetch installation information
    click.echo("Fetching installation information...")
    installation_info = fetch_installation_info(client, headers, url)
    print_installation_info(installation_info)

    # Get default person's Gramps ID for detailed person profile
    default_person_handle = installation_info.get("default_person_handle")
    default_person_gramps_id = None
    if default_person_handle:
        default_person_gramps_id = get_default_person_gramps_id(
            client, headers, url, default_person_handle
        )
        if not default_person_gramps_id:
            click.echo("Warning: Could not fetch default person Gramps ID")
        click.echo()

    # Get list of endpoints to profile
    endpoints = get_default_endpoints(default_person_gramps_id)

    click.echo(
        f"Profiling {len(endpoints)} endpoints with {iterations} iterations each..."
    )
    click.echo()

    # Profile each endpoint
    results = []

    for endpoint in endpoints:
        click.echo(f"Profiling: {endpoint['name']}...", nl=False)

        if url:
            response_times, status_codes, object_count = profile_endpoint_with_http(
                url, headers, endpoint["method"], endpoint["path"], iterations, warmup
            )
        else:
            response_times, status_codes, object_count = (
                profile_endpoint_with_test_client(
                    client,
                    headers,
                    endpoint["method"],
                    endpoint["path"],
                    iterations,
                    warmup,
                )
            )

        # Calculate statistics
        stats = calculate_statistics(response_times, status_codes)

        result = {
            "name": endpoint["name"],
            "method": endpoint["method"],
            "path": endpoint["path"],
            "iterations": iterations,
            "status_codes": status_codes,
            "object_count": object_count,
            **stats,
        }
        results.append(result)

        click.echo(f" {stats['mean_ms']:.2f} ± {stats['stddev_ms']:.2f} ms")

    # Print summary table
    print_results_table(results)

    # Save to JSON if requested
    if output:
        save_results_json(
            results, output, tree, url, iterations, warmup, installation_info
        )
