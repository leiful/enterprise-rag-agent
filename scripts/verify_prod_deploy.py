import argparse
import json
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass, field


EXPECTED_CONTAINERS = {
    "postgres": "ai-agent-postgres",
    "backend": "ai-agent-backend",
    "nginx": "ai-agent-nginx",
}


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass
class CheckResult:
    messages: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self):
        return not self.errors

    def extend(self, other):
        self.messages.extend(other.messages)
        self.errors.extend(other.errors)


def run_command(command):
    process = subprocess.run(command, text=True, capture_output=True, check=False)
    return CommandResult(returncode=process.returncode, stdout=process.stdout, stderr=process.stderr)


def check_compose_services(runner=run_command):
    result = CheckResult()
    command = ["docker", "compose", "--env-file", ".env.prod", "-f", "compose.prod.yml", "ps"]
    completed = runner(command)
    output = f"{completed.stdout}\n{completed.stderr}".strip()

    if completed.returncode != 0:
        result.errors.append("docker compose ps failed.")
        if output:
            result.messages.append(output)
        return result

    for container_name in EXPECTED_CONTAINERS.values():
        if container_name not in output:
            result.errors.append(f"compose ps output does not include {container_name}.")

    if result.ok:
        result.messages.append("compose ps includes expected production services.")
    return result


def check_container(service_name, container_name, runner=run_command):
    result = CheckResult()
    command = [
        "docker",
        "inspect",
        container_name,
        "--format",
        "{{json .State}}",
    ]
    completed = runner(command)
    if completed.returncode != 0:
        result.errors.append(f"{service_name} container inspect failed.")
        if completed.stderr.strip():
            result.messages.append(completed.stderr.strip())
        return result

    try:
        state = json.loads(completed.stdout.strip())
    except json.JSONDecodeError:
        result.errors.append(f"{service_name} container inspect returned invalid JSON.")
        return result

    status = state.get("Status")
    if status != "running":
        result.errors.append(f"{service_name} container status is {status or 'unknown'}.")
        return result

    health = state.get("Health")
    if health:
        health_status = health.get("Status")
        if health_status != "healthy":
            result.errors.append(f"{service_name} container health is {health_status or 'unknown'}.")
            return result
        result.messages.append(f"{service_name} container is running and healthy.")
    else:
        result.messages.append(f"{service_name} container is running.")
    return result


def check_http_health(url, timeout=10):
    result = CheckResult()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            status = response.status
    except (urllib.error.URLError, TimeoutError) as exc:
        result.errors.append(f"HTTP health check failed: {url}")
        result.messages.append(str(exc))
        return result

    if 200 <= status < 400:
        result.messages.append(f"HTTP health check passed: {url}")
    else:
        result.errors.append(f"HTTP health check returned status {status}: {url}")
    return result


def verify_deploy(public_url=None, runner=run_command):
    result = CheckResult()
    result.extend(check_compose_services(runner))
    for service_name, container_name in EXPECTED_CONTAINERS.items():
        result.extend(check_container(service_name, container_name, runner))
    if public_url:
        result.extend(check_http_health(public_url.rstrip("/") + "/health"))
    return result


def main():
    parser = argparse.ArgumentParser(description="Verify production containers after a manual deployment.")
    parser.add_argument(
        "--public-url",
        help="Optional production origin, for example https://example.com. The script checks /health.",
    )
    args = parser.parse_args()

    result = verify_deploy(public_url=args.public_url)
    for message in result.messages:
        print(message)
    for error in result.errors:
        print(f"ERROR: {error}")

    if result.ok:
        print("Production deployment verification passed.")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
