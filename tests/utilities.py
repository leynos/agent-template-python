"""Provide shared helpers for container-aware test execution.

The helpers in this module prepare Docker-compatible environment variables for
tests that call ``act`` and validate local container socket paths before those
paths are forwarded to subprocesses.  The public helpers intentionally keep
socket policy in one module so conftest fixtures and integration tests do not
duplicate environment handling.

Public helpers include ``docker_environment`` for constructing a sanitized
subprocess environment, ``container_daemon_socket`` for selecting the
``act --container-daemon-socket`` value, and directory helpers describing the
accepted socket roots.

Constraints
-----------
Only canonical local Unix socket paths are accepted.  Remote Docker endpoints,
malformed ``DOCKER_HOST`` values, missing sockets, and sockets outside the
allowed runtime directories are removed or ignored.  Host GitHub authentication
tokens are removed so stale local credentials cannot break public action clones
inside ``act``.

Examples
--------
Prepare an environment for an act subprocess::

    env = docker_environment()
    socket = container_daemon_socket(env)
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

GITHUB_AUTH_ENV_VARS = ("GITHUB_TOKEN", "GH_TOKEN")


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
    """Return socket roots accepted for runtime availability probes.

    Parameters
    ----------
    None

    Returns
    -------
    tuple[pathlib.Path, ...]
        Canonical directories under which local Docker-compatible runtime
        sockets are trusted for ``DOCKER_HOST`` sanitisation.

    Raises
    ------
    OSError
        May be raised if resolving one of the fixed runtime directory paths
        fails unexpectedly.

    Examples
    --------
    Validate a resolved socket path against accepted local roots::

        roots = local_socket_dirs()
    """
    return (
        Path("/run").resolve(),
        Path("/var/run").resolve(),
        Path(f"/run/user/{os.getuid()}/podman").resolve(),
    )


def user_runtime_socket_dirs() -> tuple[Path, ...]:
    """Return user runtime roots accepted for act socket forwarding.

    Parameters
    ----------
    None

    Returns
    -------
    tuple[pathlib.Path, ...]
        Canonical current-user runtime directories accepted for
        ``--container-daemon-socket`` forwarding.

    Raises
    ------
    OSError
        May be raised if resolving the current user's runtime directory fails
        unexpectedly.

    Examples
    --------
    Use the roots when validating an act socket value::

        roots = user_runtime_socket_dirs()
    """
    return (Path(f"/run/user/{os.getuid()}").resolve(),)


def docker_environment() -> dict[str, str]:
    """Return a sanitized environment for Docker-compatible subprocesses.

    The helper copies ``os.environ``, canonicalises acceptable local Unix
    ``DOCKER_HOST`` values, removes unsafe or malformed values, and falls back
    to the current user's Podman socket when it exists and stays within the
    expected runtime directory.

    Parameters
    ----------
    None

    Returns
    -------
    dict[str, str]
        Environment mapping suitable for subprocesses that need Docker-
        compatible container access.

    Raises
    ------
    None
        Invalid socket values are removed rather than raised.

    Examples
    --------
    Pass the sanitized environment into a subprocess::

        subprocess.run(command, env=docker_environment(), check=False)
    """
    env = os.environ.copy()
    for variable in GITHUB_AUTH_ENV_VARS:
        env.pop(variable, None)
    docker_host = env.get("DOCKER_HOST")
    if docker_host is not None:
        socket_path = _resolved_socket_from_docker_host(
            docker_host, local_socket_dirs()
        )
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
    """Return a validated ``act`` container daemon socket value.

    Parameters
    ----------
    env
        Environment mapping that may contain a ``DOCKER_HOST`` value.

    Returns
    -------
    str | None
        Canonical ``unix://`` socket URL under the current user's runtime
        directory, or ``None`` when no safe value is available.

    Raises
    ------
    None
        Malformed, remote, missing, or out-of-bounds socket values are ignored.

    Examples
    --------
    Append the daemon socket flag only when a safe socket exists::

        socket = container_daemon_socket(env)
        if socket is not None:
            command.extend(["--container-daemon-socket", socket])
    """
    docker_host = env.get("DOCKER_HOST")
    if docker_host is None:
        return None
    socket_path = _resolved_socket_from_docker_host(
        docker_host, user_runtime_socket_dirs()
    )
    if socket_path is None:
        return None
    return f"unix://{socket_path}"
