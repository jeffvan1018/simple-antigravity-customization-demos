#!/usr/bin/env python3
"""PreToolUse hook to block installing Python packages created by Microsoft."""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

PYPI_URL_TEMPLATE = "https://pypi.org/pypi/{name}/json"
REQUEST_TIMEOUT_SECONDS = 5

MICROSOFT_GITHUB_RE = re.compile(
    r"https?://(?:www\.)?github\.com/(?:microsoft|azure|azuread|microsoftopensource)/",
    re.IGNORECASE,
)
MICROSOFT_WORD_RE = re.compile(r"\bmicrosoft\b", re.IGNORECASE)
MICROSOFT_EMAIL_RE = re.compile(r"@microsoft\.com\b", re.IGNORECASE)
MICROSOFT_URL_RE = re.compile(
    r"https?://(?:[a-z0-9-]+\.)*microsoft\.com\b", re.IGNORECASE
)
MICROSOFT_OWNERS = {"microsoft", "azure-sdk", "msft-oss"}

# Flags that consume the next argument token.
VALUE_FLAGS = {
    "-c",
    "--constraint",
    "-i",
    "--index-url",
    "--extra-index-url",
    "-f",
    "--find-links",
    "-t",
    "--target",
    "--python",
    "--python-version",
    "--platform",
    "--implementation",
    "--abi",
    "--only-binary",
    "--no-binary",
    "--prefix",
    "--root",
    "--src",
    "-G",
    "--group",
    "--optional",
    "-C",
    "--config-settings",
    "--global-option",
    "--install-option",
    "--build-option",
    "--progress-bar",
    "--cache-dir",
    "--log",
    "--proxy",
    "--retries",
    "--timeout",
    "--cert",
    "--client-cert",
    "--trusted-host",
    "-e",
    "--editable",
    "-n",
    "--name",
    "-p",
    "--path",
}

REQ_FLAGS = {"-r", "--requirement"}


def split_shell_segments(command_line: str) -> list[str]:
    """Split a shell command line on &&, ||, ;, |, and newlines outside quotes."""
    segments: list[str] = []
    buf: list[str] = []
    in_single = False
    in_double = False
    escaped = False
    i = 0
    n = len(command_line)

    while i < n:
        ch = command_line[i]
        if escaped:
            buf.append(ch)
            escaped = False
            i += 1
            continue

        if ch == "\\" and not in_single:
            buf.append(ch)
            escaped = True
            i += 1
            continue

        if ch == "'" and not in_double:
            in_single = not in_single
            buf.append(ch)
            i += 1
            continue

        if ch == '"' and not in_single:
            in_double = not in_double
            buf.append(ch)
            i += 1
            continue

        if not in_single and not in_double:
            if command_line[i : i + 2] in ("&&", "||"):
                seg = "".join(buf).strip()
                if seg:
                    segments.append(seg)
                buf.clear()
                i += 2
                continue
            if ch in (";", "|", "\n"):
                seg = "".join(buf).strip()
                if seg:
                    segments.append(seg)
                buf.clear()
                i += 1
                continue

        buf.append(ch)
        i += 1

    seg = "".join(buf).strip()
    if seg:
        segments.append(seg)
    return segments


def strip_env_and_wrappers(tokens: list[str]) -> list[str]:
    """Strip leading env vars (KEY=VAL) and wrapper commands (env, sudo, command)."""
    idx = 0
    while idx < len(tokens):
        tok = tokens[idx]
        if tok in ("env", "sudo", "command", "nohup"):
            idx += 1
            # Skip short flags on wrappers like sudo -u root or env -i
            while idx < len(tokens) and tokens[idx].startswith("-"):
                idx += 1
            continue
        if "=" in tok and not tok.startswith("-") and tok.split("=", 1)[0].isidentifier():
            idx += 1
            continue
        break
    return tokens[idx:]


def find_install_args(tokens: list[str]) -> list[str] | None:
    """Return package-install argument tokens if this command installs Python packages."""
    if not tokens:
        return None

    exe = os.path.basename(tokens[0]).lower()

    # pip / pip3 / pip3.x
    if re.fullmatch(r"pip(\d+(\.\d+)?)?", exe):
        if len(tokens) >= 2 and tokens[1] == "install":
            return tokens[2:]
        return None

    # python -m pip install ... / python3 -m uv pip install ...
    if re.fullmatch(r"python(\d+(\.\d+)?)?", exe):
        for i in range(1, len(tokens) - 2):
            if tokens[i] == "-m":
                mod = tokens[i + 1].lower()
                if mod == "pip" and i + 2 < len(tokens) and tokens[i + 2] == "install":
                    return tokens[i + 3 :]
                if mod == "uv":
                    return find_install_args(["uv", *tokens[i + 2 :]])
                break
        return None

    # uv pip install ... / uv add ... / uv tool install ...
    if exe == "uv":
        if len(tokens) >= 3 and tokens[1] == "pip" and tokens[2] == "install":
            return tokens[3:]
        if len(tokens) >= 2 and tokens[1] == "add":
            return tokens[2:]
        if len(tokens) >= 3 and tokens[1] == "tool" and tokens[2] == "install":
            return tokens[3:]
        return None

    # poetry add ... / pdm add ... / rye add ...
    if exe in ("poetry", "pdm", "rye"):
        if len(tokens) >= 2 and tokens[1] == "add":
            return tokens[2:]
        return None

    # pipenv install ... / conda install ... / mamba install ...
    if exe in ("pipenv", "conda", "mamba"):
        if len(tokens) >= 2 and tokens[1] == "install":
            return tokens[2:]
        return None

    return None


def extract_package_name(spec: str) -> str | None:
    """Extract normalized PyPI package name from a requirement specifier, or None."""
    spec = spec.strip()
    if not spec or spec.startswith("#"):
        return None

    # Handle PEP 508 direct URL: pkg @ https://...
    if " @ " in spec:
        spec = spec.split(" @ ", 1)[0].strip()

    # Skip local paths or direct URLs (URLs are checked separately)
    if spec.startswith((".", "/", "~")) or "://" in spec or spec.startswith("git+"):
        return None

    # Strip environment markers, extras, and version specifiers
    spec = spec.split(";", 1)[0].strip()
    spec = re.split(r"[\[=<>!~]", spec, maxsplit=1)[0].strip()
    if not spec:
        return None

    # Valid PEP 508 name characters
    if not re.fullmatch(r"[A-Za-z0-9._-]+", spec):
        return None
    return spec


def parse_requirements_file(path: Path) -> tuple[list[str], list[str]]:
    """Return (package_names, urls) from a requirements file."""
    packages: list[str] = []
    urls: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return packages, urls

    for raw_line in lines:
        line = raw_line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        if "://" in line or line.startswith("git+"):
            urls.append(line)
        pkg = extract_package_name(line)
        if pkg:
            packages.append(pkg)
    return packages, urls


def collect_targets(args: list[str], cwd: str) -> tuple[list[str], list[str]]:
    """Collect (package_names, urls) from package manager install arguments."""
    packages: list[str] = []
    urls: list[str] = []
    i = 0
    while i < len(args):
        tok = args[i]

        if tok in REQ_FLAGS:
            if i + 1 < len(args):
                req_path = Path(args[i + 1])
                if not req_path.is_absolute() and cwd:
                    req_path = Path(cwd) / req_path
                req_pkgs, req_urls = parse_requirements_file(req_path)
                packages.extend(req_pkgs)
                urls.extend(req_urls)
                i += 2
                continue
            i += 1
            continue

        if tok.startswith("--requirement="):
            req_path = Path(tok.split("=", 1)[1])
            if not req_path.is_absolute() and cwd:
                req_path = Path(cwd) / req_path
            req_pkgs, req_urls = parse_requirements_file(req_path)
            packages.extend(req_pkgs)
            urls.extend(req_urls)
            i += 1
            continue

        if tok in VALUE_FLAGS:
            if tok in ("-e", "--editable") and i + 1 < len(args):
                nxt = args[i + 1]
                if "://" in nxt or nxt.startswith("git+"):
                    urls.append(nxt)
            i += 2
            continue

        if tok.startswith("-"):
            i += 1
            continue

        if "://" in tok or tok.startswith("git+"):
            urls.append(tok)

        pkg = extract_package_name(tok)
        if pkg:
            packages.append(pkg)
        i += 1

    return packages, urls


def is_microsoft_metadata(data: dict[str, Any]) -> str | None:
    """Return a reason string if PyPI JSON metadata indicates Microsoft authorship."""
    ownership = data.get("ownership") or {}
    org = ownership.get("organization")
    if isinstance(org, str) and MICROSOFT_WORD_RE.search(org):
        return f"PyPI organization '{org}'"

    for role in ownership.get("roles") or []:
        user = (role.get("user") or "").lower()
        if user in MICROSOFT_OWNERS:
            return f"PyPI owner '{role.get('user')}'"

    info = data.get("info") or {}
    for field in ("author", "maintainer"):
        val = info.get(field)
        if isinstance(val, str) and MICROSOFT_WORD_RE.search(val):
            return f"{field} '{val}'"

    for field in ("author_email", "maintainer_email"):
        val = info.get(field)
        if isinstance(val, str) and (
            MICROSOFT_EMAIL_RE.search(val) or MICROSOFT_WORD_RE.search(val)
        ):
            return f"{field} '{val}'"

    urls_to_check: list[str] = []
    for field in ("home_page", "project_url"):
        val = info.get(field)
        if isinstance(val, str):
            urls_to_check.append(val)
    project_urls = info.get("project_urls")
    if isinstance(project_urls, dict):
        for val in project_urls.values():
            if isinstance(val, str):
                urls_to_check.append(val)

    for url in urls_to_check:
        if MICROSOFT_GITHUB_RE.search(url) or MICROSOFT_URL_RE.search(url):
            return f"project URL '{url}'"

    return None


def check_pypi_package(pkg: str) -> tuple[str, str | None]:
    """Check PyPI for package authorship.

    Returns (status, detail) where status is 'microsoft', 'ok', or 'unknown'.
    """
    url = PYPI_URL_TEMPLATE.format(name=pkg)
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "agy-hook-pypi-check/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return "ok", None
        return "unknown", f"HTTP {exc.code} from PyPI"
    except Exception as exc:
        return "unknown", str(exc)

    reason = is_microsoft_metadata(data)
    if reason:
        return "microsoft", reason
    return "ok", None


def check_command(command_line: str, cwd: str) -> dict[str, Any]:
    """Evaluate CommandLine and return a PreToolUse decision payload."""
    if not command_line.strip():
        return {"decision": "allow"}

    all_packages: list[str] = []
    all_urls: list[str] = []

    for segment in split_shell_segments(command_line):
        try:
            tokens = shlex.split(segment)
        except ValueError:
            tokens = segment.split()
        tokens = strip_env_and_wrappers(tokens)
        install_args = find_install_args(tokens)
        if install_args is None:
            continue
        pkgs, urls = collect_targets(install_args, cwd)
        all_packages.extend(pkgs)
        all_urls.extend(urls)

    for url in all_urls:
        if MICROSOFT_GITHUB_RE.search(url) or MICROSOFT_URL_RE.search(url):
            return {
                "decision": "deny",
                "reason": f"Blocked installing Python package from Microsoft URL: {url}",
            }

    seen: set[str] = set()
    unknown_errors: list[str] = []

    for pkg in all_packages:
        norm = pkg.lower().replace("_", "-")
        if norm in seen:
            continue
        seen.add(norm)

        status, detail = check_pypi_package(pkg)
        if status == "microsoft":
            return {
                "decision": "deny",
                "reason": f"Blocked installing Python package '{pkg}' created by Microsoft ({detail}).",
            }
        if status == "unknown":
            unknown_errors.append(f"{pkg}: {detail}")

    if unknown_errors:
        return {
            "decision": "ask",
            "reason": "Could not verify PyPI publisher for: " + "; ".join(unknown_errors),
        }

    return {"decision": "allow"}


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        print(json.dumps({"decision": "allow"}))
        return 0

    tool_call = payload.get("toolCall") or {}
    args = tool_call.get("args") or {}
    command_line = args.get("CommandLine") or ""
    cwd = payload.get("cwd") or ""

    result = check_command(command_line, cwd)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
