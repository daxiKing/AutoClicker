"""GitHub release checks and asset downloads for AutoClicker.

The updater talks to the public GitHub REST API, compares semantic versions and
saves the newest installer into the user's Downloads folder. No credentials are
stored: public repositories work anonymously, and a token can be supplied at
runtime through ``GITHUB_TOKEN`` if a private mirror is used.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

DEFAULT_REPO = "daxiKing/AutoClicker"
USER_AGENT = "AutoClicker-Updater/2.5.0"
API_ROOT = "https://api.github.com"

_VERSION_RE = re.compile(r"(\d+(?:\.\d+){0,3})")
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class UpdateError(RuntimeError):
    """Raised for network, API or download failures."""


class ReleaseNotFound(UpdateError):
    """Raised when the repository has no published release yet."""


NO_RELEASE_MESSAGE = "No public release has been published yet."


def normalize_repo(value: str | None) -> str:
    """Accept ``owner/repo`` or a github.com URL and return ``owner/repo``."""
    text = str(value or "").strip()
    if not text:
        return DEFAULT_REPO
    if text.startswith("git@github.com:"):
        text = text.split(":", 1)[1]
    elif "github.com/" in text:
        text = text.split("github.com/", 1)[1]
    text = urllib.parse.urlparse(text).path if "://" in text else text
    text = text.strip("/")
    if text.endswith(".git"):
        text = text[:-4]
    parts = [part for part in text.split("/") if part]
    candidate = "/".join(parts[:2])
    return candidate if _REPO_RE.match(candidate) else DEFAULT_REPO


def parse_version(value: str | None) -> tuple[int, int, int, int]:
    """Turn ``v2.5.0`` (or a tag name) into a comparable four-part tuple."""
    match = _VERSION_RE.search(str(value or ""))
    if not match:
        return (0, 0, 0, 0)
    parts = [int(part) for part in match.group(1).split(".")]
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts[:4])


def is_newer(candidate: str | None, current: str | None) -> bool:
    """Return True when *candidate* is a newer semantic version."""
    return parse_version(candidate) > parse_version(current)


def format_version(value: str | None) -> str:
    match = _VERSION_RE.search(str(value or ""))
    return match.group(1) if match else "0.0.0"


def _headers() -> dict[str, str]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github+json",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _request_json(url: str, timeout: float = 12.0) -> Any:
    request = urllib.request.Request(url, headers=_headers())
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise UpdateError("Repository or release not found on GitHub.") from exc
        if exc.code == 403:
            raise UpdateError("GitHub rate limit reached — try again later.") from exc
        raise UpdateError(f"GitHub returned HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        raise UpdateError(f"Network unavailable: {exc.reason}") from exc
    except Exception as exc:
        raise UpdateError(str(exc)) from exc
    try:
        return json.loads(payload.decode("utf-8"))
    except Exception as exc:
        raise UpdateError("GitHub returned an unreadable response.") from exc


def fetch_repo(repo: str = DEFAULT_REPO, timeout: float = 12.0) -> dict[str, Any]:
    """Fetch public repository metadata used by the connection card."""
    repo = normalize_repo(repo)
    payload = _request_json(f"{API_ROOT}/repos/{repo}", timeout)
    if not isinstance(payload, dict):
        raise UpdateError("Unexpected repository payload.")
    return {
        "repo": repo,
        "full_name": payload.get("full_name", repo),
        "description": payload.get("description") or "",
        "stars": int(payload.get("stargazers_count") or 0),
        "forks": int(payload.get("forks_count") or 0),
        "language": payload.get("language") or "",
        "html_url": payload.get("html_url") or f"https://github.com/{repo}",
        "default_branch": payload.get("default_branch") or "main",
    }


def fetch_latest(repo: str = DEFAULT_REPO, timeout: float = 12.0) -> dict[str, Any]:
    """Fetch the newest published GitHub release."""
    repo = normalize_repo(repo)
    try:
        payload = _request_json(f"{API_ROOT}/repos/{repo}/releases/latest", timeout)
    except UpdateError as exc:
        if "not found" in str(exc).lower():
            raise ReleaseNotFound(NO_RELEASE_MESSAGE) from exc
        raise
    if not isinstance(payload, dict):
        raise UpdateError("Unexpected release payload.")
    assets: list[dict[str, Any]] = []
    for item in payload.get("assets") or []:
        if not isinstance(item, dict):
            continue
        download_url = item.get("browser_download_url")
        if not download_url:
            continue
        assets.append(
            {
                "name": str(item.get("name") or "release-asset"),
                "size": int(item.get("size") or 0),
                "browser_download_url": str(download_url),
                "content_type": str(item.get("content_type") or ""),
            }
        )
    tag = str(payload.get("tag_name") or payload.get("name") or "")
    return {
        "repo": repo,
        "tag": tag,
        "version": format_version(tag),
        "name": str(payload.get("name") or tag or "Latest release"),
        "body": str(payload.get("body") or ""),
        "published_at": str(payload.get("published_at") or ""),
        "html_url": str(payload.get("html_url") or f"https://github.com/{repo}/releases"),
        "prerelease": bool(payload.get("prerelease")),
        "assets": assets,
    }


def pick_installer(assets: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Choose the most suitable installer asset for this platform."""
    if not assets:
        return None
    windows = any(
        str(item.get("name", "")).lower().endswith((".exe", ".msi")) for item in assets
    )
    if sys_platform_is_windows() or windows:
        preferences = (
            lambda name: "setup" in name and name.endswith(".exe"),
            lambda name: name.endswith(".exe") and "setup" in name,
            lambda name: name.endswith(".exe"),
            lambda name: name.endswith(".msi"),
        )
    else:
        preferences = (
            lambda name: name.endswith(".appimage"),
            lambda name: "autoclicker" in name and name.endswith(".tar.gz"),
            lambda name: name.endswith(".deb"),
            lambda name: name.endswith(".zip"),
        )
    lowered = [
        (str(item.get("name", "")).lower(), item) for item in assets if item.get("name")
    ]
    for predicate in preferences:
        for name, item in lowered:
            if predicate(name):
                return item
    return assets[0]


def sys_platform_is_windows() -> bool:
    import sys

    return sys.platform.startswith("win")


def downloads_dir() -> Path:
    """Best-effort Downloads folder with a home-directory fallback."""
    candidate = Path.home() / "Downloads"
    try:
        candidate.mkdir(parents=True, exist_ok=True)
        return candidate
    except OSError:
        return Path(tempfile.gettempdir())


def download(
    url: str,
    destination: Path,
    *,
    timeout: float = 60.0,
    progress: Callable[[int, int], None] | None = None,
) -> Path:
    """Stream *url* into *destination* and return the final path."""
    destination = Path(destination)
    request = urllib.request.Request(url, headers=_headers())
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            total = int(response.headers.get("Content-Length") or 0)
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_suffix(destination.suffix + ".part")
            written = 0
            with temporary.open("wb") as handle:
                while True:
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
                    written += len(chunk)
                    if progress is not None:
                        try:
                            progress(written, total)
                        except Exception:
                            pass
            temporary.replace(destination)
            return destination
    except urllib.error.HTTPError as exc:
        raise UpdateError(f"Download failed with HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        raise UpdateError(f"Download failed: {exc.reason}") from exc
    except OSError as exc:
        raise UpdateError(f"Could not save the installer: {exc}") from exc


def download_installer(
    release: dict[str, Any],
    *,
    progress: Callable[[int, int], None] | None = None,
) -> Path:
    """Download the preferred asset of *release* into Downloads."""
    asset = pick_installer(list(release.get("assets") or []))
    if asset is None:
        raise UpdateError("This release has no downloadable asset yet.")
    name = Path(str(asset["name"])).name
    destination = downloads_dir() / name
    return download(
        str(asset["browser_download_url"]),
        destination,
        progress=progress,
    )


__all__ = [
    "DEFAULT_REPO",
    "NO_RELEASE_MESSAGE",
    "ReleaseNotFound",
    "UpdateError",
    "download",
    "download_installer",
    "downloads_dir",
    "fetch_latest",
    "fetch_repo",
    "format_version",
    "is_newer",
    "normalize_repo",
    "parse_version",
    "pick_installer",
]
