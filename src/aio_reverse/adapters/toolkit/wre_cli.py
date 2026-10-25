"""Adapter for the Rust ``wre`` CLI.

The CLI is the process boundary to the toolkit crates. No crate is reimplemented
here: every method shells out with ``--json`` (except ``env script``, which
prints JavaScript on stdout) and fails loud on any error.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Sequence

from aio_reverse.domain.errors import ToolkitError, ToolkitNotFoundError
from aio_reverse.targets.web_target import TargetProbeConfig

BUNDLE_FILE = "bundle.json"
TEMPLATE_MIN_PAGES = 2
_REPO_ROOT = Path(__file__).resolve().parents[4]
_TOOLKIT_ROOT = _REPO_ROOT / "libs" / "web-re-toolkit"


def _decode(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def resolve_binary(explicit: Path | None = None) -> Path:
    """Resolve the wre binary, preferring an explicit path then local builds."""
    if explicit is not None:
        if not explicit.is_file():
            raise ToolkitNotFoundError(f"wre binary does not exist: {explicit}")
        if not os.access(explicit, os.X_OK):
            raise ToolkitNotFoundError(f"wre binary is not executable: {explicit}")
        return explicit

    from_env = os.getenv("WRE_BIN")
    if from_env:
        candidate = Path(from_env).expanduser()
        if not candidate.is_file() or not os.access(candidate, os.X_OK):
            raise ToolkitNotFoundError(
                f"WRE_BIN is set to {candidate}, but it is not an executable file"
            )
        return candidate

    for profile in ("release", "debug"):
        candidate = _TOOLKIT_ROOT / "target" / profile / "wre"
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate

    found = shutil.which("wre")
    if found:
        return Path(found)

    raise ToolkitNotFoundError(
        "wre binary not found; build it once with:\n"
        f"  cd {_TOOLKIT_ROOT} && cargo build --release -p wre-cli"
    )


class WreToolkit:
    """Thin, fail-loud wrapper around crate-backed CLI commands."""

    def __init__(self, workspace: Path, binary: Path | None = None) -> None:
        self.workspace = workspace.expanduser().resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.binary = resolve_binary(binary)

    def version(self) -> str:
        result = self._run(["--version"], json_output=False, timeout_s=10)
        text = result.stdout.strip()
        if not text:
            raise ToolkitError(
                "wre --version produced no output",
                command=result.args,
                returncode=result.returncode,
                stderr=result.stderr,
            )
        return text

    def start_browser(
        self,
        port: int,
        headless: bool = False,
        profile: Path | None = None,
    ) -> dict[str, Any]:
        # Without --status the CLI prints nothing when Chrome is already
        # running, which would leave no JSON to parse for a reused profile.
        args = ["browser", "--port", str(port), "--start", "--status"]
        if headless:
            args.append("--headless")
        if profile is not None:
            args.extend(["--profile", str(profile)])
        return self._json(args, timeout_s=30)

    def stop_browser(self, port: int) -> dict[str, Any]:
        return self._json(["browser", "--port", str(port), "--stop"], timeout_s=30)

    def browser_status(self, port: int) -> dict[str, Any]:
        return self._json(["browser", "--port", str(port), "--status"], timeout_s=30)

    def emit_probe(
        self,
        probe: TargetProbeConfig,
        name: str = "__WRE",
    ) -> str:
        args = ["probe", "emit", "--name", name, "--preset", probe.preset]
        for value in probe.properties:
            args.extend(["--property", value])
        for value in probe.methods:
            args.extend(["--method", value])
        for value in probe.events:
            args.extend(["--event", value])
        if not probe.network:
            args.append("--no-network")
        if probe.workers:
            args.append("--workers")
        if not probe.stealth:
            args.append("--no-stealth")
        if not probe.call_sites:
            args.append("--no-call-sites")
        if not probe.sse:
            args.append("--no-sse")
        if not probe.websocket:
            args.append("--no-websocket")

        value = self._json(args, timeout_s=30)
        if not isinstance(value, dict):
            raise ToolkitError(
                f"wre probe emit returned {type(value).__name__}, expected an object",
                command=[str(self.binary), *args],
                stdout=json.dumps(value),
            )
        source = value.get("source")
        if not isinstance(source, str) or not source.strip():
            raise ToolkitError(
                "wre probe emit returned no JavaScript source",
                command=[str(self.binary), *args],
                stdout=json.dumps(value),
            )
        if value.get("name") != name:
            raise ToolkitError(
                f"wre probe emit returned name {value.get('name')!r}, expected {name!r}",
                command=[str(self.binary), *args],
                stdout=json.dumps(value),
            )
        return source

    def capture(
        self,
        url: str,
        out_dir: Path,
        port: int,
        *,
        wait_s: int = 20,
        keep_storage: bool = True,
        scripts: bool = True,
        profile: Path | None = None,
    ) -> dict[str, Any]:
        out_dir.parent.mkdir(parents=True, exist_ok=True)
        args = [
            "capture",
            "--url",
            url,
            "--port",
            str(port),
            "--wait",
            str(wait_s),
            "--out",
            str(out_dir),
        ]
        if keep_storage:
            args.append("--keep-storage")
        if scripts:
            args.append("--scripts")
        if profile is not None:
            args.extend(["--profile", str(profile)])
        return self._json(args, timeout_s=wait_s + 60)

    def template_diff(
        self,
        pages: Sequence[Path],
        *,
        xpath: bool = False,
    ) -> dict[str, Any]:
        if len(pages) < TEMPLATE_MIN_PAGES:
            raise ValueError(
                f"template diff needs at least {TEMPLATE_MIN_PAGES} HTML pages, "
                f"got {len(pages)}"
            )

        args = ["template", "diff"]
        if xpath:
            args.append("--xpath")
        args.extend(str(page) for page in pages)

        value = self._json(args, timeout_s=60)
        command = [str(self.binary), *args]
        if not isinstance(value, dict):
            raise ToolkitError(
                f"wre template diff returned {type(value).__name__}, expected an object",
                command=command,
                stdout=json.dumps(value),
            )

        pages_count = value.get("pages")
        if not isinstance(pages_count, int) or isinstance(pages_count, bool):
            raise ToolkitError(
                "wre template diff returned a non-integer pages count",
                command=command,
                stdout=json.dumps(value),
            )
        if pages_count < TEMPLATE_MIN_PAGES:
            raise ToolkitError(
                f"wre template diff analyzed {pages_count} pages, expected at least "
                f"{TEMPLATE_MIN_PAGES}",
                command=command,
                stdout=json.dumps(value),
            )

        skeleton = value.get("skeleton")
        if not isinstance(skeleton, str) or not skeleton.strip():
            raise ToolkitError(
                "wre template diff returned an empty skeleton",
                command=command,
                stdout=json.dumps(value),
            )

        slots = value.get("slots")
        if not isinstance(slots, list):
            raise ToolkitError(
                f"wre template diff returned slots as {type(slots).__name__}, "
                "expected a list",
                command=command,
                stdout=json.dumps(value),
            )

        reduction = value.get("reduction_ratio")
        if not isinstance(reduction, (int, float)) or isinstance(reduction, bool):
            raise ToolkitError(
                "wre template diff returned a non-numeric reduction_ratio",
                command=command,
                stdout=json.dumps(value),
            )
        if not 0.0 <= reduction <= 1.0:
            raise ToolkitError(
                f"wre template diff returned reduction_ratio {reduction!r}, "
                "expected 0.0..1.0",
                command=command,
                stdout=json.dumps(value),
            )

        return value

    def env_script(self, depth: int) -> str:
        # ``wre env script`` prints the JavaScript in plain mode; --json would
        # replace it with a byte-count object.
        result = self._run(["env", "script", "--depth", str(depth)], json_output=False)
        source = result.stdout.strip()
        if not source:
            raise ToolkitError(
                "wre env script produced no JavaScript",
                command=result.args,
                returncode=result.returncode,
                stderr=result.stderr,
            )
        return source

    def markers(self, kind: str | None = None, group: str | None = None) -> list[dict[str, Any]]:
        args = ["markers"]
        if kind is not None:
            args.extend(["--kind", kind])
        if group is not None:
            args.extend(["--group", group])
        value = self._json(args)
        if not isinstance(value, list):
            raise ToolkitError(
                f"wre markers returned {type(value).__name__}, expected a list",
                command=[str(self.binary), *args],
                stdout=json.dumps(value),
            )
        return value

    def pools(self, group: str | None = None, one_at_a_time: bool = False) -> dict[str, Any]:
        args = ["pools"]
        if group is not None:
            args.extend(["--group", group])
        if one_at_a_time:
            args.append("--one-at-a-time")
        value = self._json(args)
        if not isinstance(value, dict) or "markers" not in value or "pools" not in value:
            raise ToolkitError(
                "wre pools returned a design without markers/pools",
                command=[str(self.binary), *args],
                stdout=json.dumps(value),
            )
        return value

    def sweep(
        self,
        baselines: Sequence[Path],
        arms: Sequence[tuple[str, Path]],
    ) -> dict[str, Any]:
        if len(baselines) < 2:
            raise ValueError("sweep needs at least two baseline payloads")
        if not arms:
            raise ValueError("sweep needs at least one arm")

        args = ["sweep"]
        for baseline in baselines:
            args.extend(["--baseline", str(baseline)])
        for name, path in arms:
            args.extend(["--arm", f"{name}={path}"])
        return self._json(args, timeout_s=60)

    def show(
        self,
        bundle_dir: Path,
        *,
        requests: bool = False,
        scripts: bool = False,
        probes: bool = False,
    ) -> dict[str, Any]:
        args = ["show", str(self.bundle_file(bundle_dir))]
        if requests:
            args.append("--requests")
        if scripts:
            args.append("--scripts")
        if probes:
            args.append("--probes")
        return self._json(args)

    def bundle_file(self, bundle_dir: Path) -> Path:
        return bundle_dir / BUNDLE_FILE

    def _json(self, args: Sequence[str], timeout_s: int = 30) -> Any:
        result = self._run(args, json_output=True, timeout_s=timeout_s)
        text = result.stdout.strip()
        if not text:
            raise ToolkitError(
                f"wre {' '.join(args)} produced no JSON",
                command=result.args,
                returncode=result.returncode,
                stderr=result.stderr,
            )
        try:
            return json.loads(text)
        except json.JSONDecodeError as error:
            raise ToolkitError(
                f"wre {' '.join(args)} returned invalid JSON: {error}",
                command=result.args,
                returncode=result.returncode,
                stderr=result.stderr,
                stdout=text,
            ) from error

    def _run(
        self,
        args: Sequence[str],
        *,
        json_output: bool,
        timeout_s: int = 30,
    ) -> subprocess.CompletedProcess[str]:
        command = [str(self.binary)]
        if args[:1] != ["--version"]:
            command.extend(["--root", str(self.workspace)])
        if json_output:
            command.append("--json")
        command.extend(args)

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise ToolkitError(
                f"wre {' '.join(args)} timed out after {timeout_s}s",
                command=command,
                stdout=_decode(error.stdout),
                stderr=_decode(error.stderr),
            ) from error

        if result.returncode != 0:
            raise ToolkitError(
                f"wre {' '.join(args)} failed with exit code {result.returncode}: "
                f"{result.stderr.strip()}",
                command=command,
                returncode=result.returncode,
                stderr=result.stderr,
                stdout=result.stdout,
            )
        return result
