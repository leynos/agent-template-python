"""Shared test helpers."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse


def _resolved_socket_from_docker_host(
    docker_host: str, allowed_dirs: tuple[Path, ...]
) -> Path | None:
    parsed = urlparse(docker_host)
    if parsed.scheme != "unix" or parsed.netloc or not parsed.path:
        return None
    try:
        socket_path = Path(parsed.path).expanduser().resolve()
    except OSError:
        return None
    if not socket_path.exists():
        return None
    if not any(socket_path.is_relative_to(allowed_dir) for allowed_dir in allowed_dirs):
        return None
    return socket_path


def _user_podman_socket() -> Path | None:
    socket_path = Path(f"/run/user/{os.getuid()}/podman/podman.sock")
    if not socket_path.exists():
        return None
    resolved = socket_path.resolve()
    expected_prefix = Path(f"/run/user/{os.getuid()}").resolve()
    if resolved.is_relative_to(expected_prefix):
        return resolved
    return None


def local_socket_dirs() -> tuple[Path, ...]:
    """Return local socket directories accepted for Docker-compatible runtimes."""
    return (
        Path("/run").resolve(),
        Path("/var/run").resolve(),
        Path(f"/run/user/{os.getuid()}/podman").resolve(),
    )


def user_runtime_socket_dirs() -> tuple[Path, ...]:
    """Return user runtime directories accepted for act socket forwarding."""
    return (Path(f"/run/user/{os.getuid()}").resolve(),)


def docker_environment() -> dict[str, str]:
    """Return an environment that points act at a usable container socket."""
    env = os.environ.copy()
    docker_host = env.get("DOCKER_HOST")
    if docker_host is not None:
        socket_path = _resolved_socket_from_docker_host(docker_host, local_socket_dirs())
        if socket_path is None:
            env.pop("DOCKER_HOST", None)
        else:
            env["DOCKER_HOST"] = f"unix://{socket_path}"
    if "DOCKER_HOST" not in env:
        socket_path = _user_podman_socket()
        if socket_path is not None:
            env["DOCKER_HOST"] = f"unix://{socket_path}"
    return env


def container_daemon_socket(env: dict[str, str]) -> str | None:
    """Return a validated act container daemon socket from an environment."""
    docker_host = env.get("DOCKER_HOST")
    if docker_host is None:
        return None
    socket_path = _resolved_socket_from_docker_host(
        docker_host, user_runtime_socket_dirs()
    )
    if socket_path is None:
        return None
    return f"unix://{socket_path}"
