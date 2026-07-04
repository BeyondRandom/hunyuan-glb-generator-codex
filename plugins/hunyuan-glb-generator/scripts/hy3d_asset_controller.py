#!/usr/bin/env python3
"""Control the local Hunyuan3D portable API and save generated GLB assets.

This script is intentionally Windows-first because it targets the user's local
portable Hunyuan3D bundle. It uses only the Python standard library so it can run
from Codex's system Python or from ordinary PowerShell.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PLUGIN_ROOT = Path(os.environ.get("HUNYUAN_GLB_PLUGIN_ROOT", Path(__file__).resolve().parents[1])).expanduser().resolve()
STATE_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Codex" / "hunyuan-glb-generator"
USER_CONFIG_PATH = STATE_DIR / "config.json"
PLUGIN_LOCAL_CONFIG_PATH = PLUGIN_ROOT / "config.local.json"
CONFIG_PATH = Path(os.environ.get("HUNYUAN_GLB_CONFIG", USER_CONFIG_PATH)).expanduser()
HUNYUAN_REPO_URL = "https://github.com/Tencent-Hunyuan/Hunyuan3D-2"


def load_local_config() -> dict[str, Any]:
    for path in (CONFIG_PATH, PLUGIN_LOCAL_CONFIG_PATH):
        if not path.exists():
            continue
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
    return {}


LOCAL_CONFIG = load_local_config()


def configured_text(env_name: str, config_key: str, default: str | None = None) -> str | None:
    value = os.environ.get(env_name)
    if value:
        return value
    config_value = LOCAL_CONFIG.get(config_key)
    if isinstance(config_value, str) and config_value.strip():
        return config_value
    return default


def configured_int(env_name: str, config_key: str, default: int) -> int:
    value = os.environ.get(env_name)
    if value is None:
        value = LOCAL_CONFIG.get(config_key)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def looks_like_hunyuan_root(path: Path) -> bool:
    return (
        (path / "python_standalone" / "python.exe").exists()
        and (path / "Hunyuan3D-2" / "api_server.py").exists()
    )


def candidate_hunyuan_paths() -> list[Path]:
    home = Path.home()
    candidates = [
        Path("C:/AI/HY3D2/Hunyuan3D2_WinPortable_cu129/Hunyuan3D2_WinPortable"),
        Path("C:/AI/HY3D2/Hunyuan3D2_WinPortable"),
        Path("C:/AI/Hunyuan3D2_WinPortable"),
        Path("C:/AI/Hunyuan3D-2"),
        home / "AI" / "Hunyuan3D2_WinPortable",
        home / "Downloads" / "Hunyuan3D2_WinPortable",
        home / "Desktop" / "Hunyuan3D2_WinPortable",
    ]
    search_roots = [Path("C:/AI"), Path("D:/AI"), home / "AI", home / "Downloads", home / "Desktop"]
    seen = {str(path).lower() for path in candidates}

    def add(path: Path) -> None:
        key = str(path).lower()
        if key not in seen:
            candidates.append(path)
            seen.add(key)

    def walk_limited(base: Path, depth: int) -> None:
        if depth < 0 or not base.exists() or not base.is_dir():
            return
        try:
            children = list(base.iterdir())
        except OSError:
            return
        for child in children:
            if not child.is_dir():
                continue
            lowered = child.name.lower()
            if "hunyuan" in lowered or "hy3d" in lowered:
                add(child)
                walk_limited(child, depth - 1)

    for root in search_roots:
        walk_limited(root, 3)
    return candidates


def find_hunyuan_roots() -> list[Path]:
    roots: list[Path] = []
    seen: set[str] = set()
    for candidate in candidate_hunyuan_paths():
        try:
            resolved = candidate.expanduser().resolve()
        except OSError:
            continue
        key = str(resolved).lower()
        if key in seen or not looks_like_hunyuan_root(resolved):
            continue
        roots.append(resolved)
        seen.add(key)
    return roots


def configured_hunyuan_root() -> str | None:
    return configured_text("HY3D_PORTABLE_ROOT", "hunyuan_root")


def discover_hunyuan_root() -> str | None:
    configured = configured_hunyuan_root()
    if configured:
        return configured
    roots = find_hunyuan_roots()
    if roots:
        return str(roots[0])
    return None


HUNYUAN_ROOT_TEXT = discover_hunyuan_root()
HUNYUAN_ROOT = Path(HUNYUAN_ROOT_TEXT).expanduser() if HUNYUAN_ROOT_TEXT else Path("__configure_hy3d_portable_root__")
DEFAULT_OUTPUT_TEXT = configured_text("HUNYUAN_GLB_DEFAULT_OUTPUT", "default_output_dir")
STATE_PATH = STATE_DIR / "state.json"
PID_PATH = STATE_DIR / "hunyuan-api.pid"
LOG_PATH = STATE_DIR / "hunyuan-api.log"
JOBS_DIR = STATE_DIR / "jobs"

DEFAULT_HOST = str(LOCAL_CONFIG.get("host") or "127.0.0.1")
DEFAULT_PORT = int(LOCAL_CONFIG.get("port") or 8081)
READY_TIMEOUT_SEC = 900
REQUEST_TIMEOUT_SEC = configured_int("HUNYUAN_GLB_REQUEST_TIMEOUT_SEC", "request_timeout_sec", 3600)
BACKEND_CHOICES = ("auto", "api", "api_low_vram")


class ControllerError(RuntimeError):
    """Expected controller error with user-facing text."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_state_dir() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def job_path(job_id: str) -> Path:
    safe_id = re.sub(r"[^A-Za-z0-9._-]+", "_", job_id)
    return JOBS_DIR / f"{safe_id}.json"


def job_log_path(job_id: str) -> Path:
    safe_id = re.sub(r"[^A-Za-z0-9._-]+", "_", job_id)
    return JOBS_DIR / f"{safe_id}.log"


def read_job(job_id: str) -> dict[str, Any]:
    payload = read_json(job_path(job_id))
    if not payload:
        raise ControllerError(f"Batch job not found: {job_id}")
    return payload


def write_job(payload: dict[str, Any]) -> None:
    payload["updated_at"] = now_iso()
    write_json(job_path(str(payload["job_id"])), payload)


def load_launcher_config() -> dict[str, Any]:
    return read_json(HUNYUAN_ROOT / "launcher_config.json")


def portable_python() -> Path:
    path = HUNYUAN_ROOT / "python_standalone" / "python.exe"
    if not path.exists():
        raise ControllerError(f"Portable Python not found: {path}")
    return path


def normalize_asset_name(name: str | None, image_path: Path | None = None) -> str:
    if not name:
        name = image_path.stem if image_path else "hunyuan_asset"
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip())
    name = re.sub(r"_+", "_", name).strip("._-")
    return name or "hunyuan_asset"


def default_output_dir() -> Path:
    if DEFAULT_OUTPUT_TEXT:
        return Path(DEFAULT_OUTPUT_TEXT)
    cwd = Path.cwd()
    candidate = cwd / "GLB_Models" / "use"
    if candidate.exists():
        return candidate
    return cwd


def pid_is_hunyuan(pid: int) -> bool:
    if os.name != "nt":
        return True
    script = f"""
$p = Get-CimInstance Win32_Process -Filter "ProcessId = {pid}" -ErrorAction SilentlyContinue
if ($null -eq $p) {{ exit 2 }}
$cmd = [string]$p.CommandLine
$exe = [string]$p.ExecutablePath
$root = "{str(HUNYUAN_ROOT).replace('"', '""')}"
if ($cmd.Contains($root) -or $exe.Contains($root)) {{ exit 0 }}
exit 1
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def terminate_pid_tree(pid: int) -> bool:
    if not pid:
        return False
    if not pid_is_hunyuan(pid):
        raise ControllerError(f"Refusing to stop PID {pid}; it does not look like a Hunyuan process.")
    if os.name == "nt":
        result = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return result.returncode == 0
    try:
        os.kill(pid, 15)
        return True
    except OSError:
        return False


def stop_hunyuan_processes() -> dict[str, Any]:
    """Stop only Python processes whose command line points inside the Hunyuan bundle."""
    stopped: list[int] = []
    pid = read_pid()
    if pid:
        try:
            if terminate_pid_tree(pid):
                stopped.append(pid)
        except ControllerError:
            raise
        except Exception:
            pass

    if os.name == "nt":
        root = str(HUNYUAN_ROOT).replace("'", "''")
        script = f"""
$root = '{root}'
$procs = Get-CimInstance Win32_Process | Where-Object {{
  $_.CommandLine -and $_.CommandLine.Contains($root) -and
  ($_.CommandLine.Contains('api_server.py') -or $_.CommandLine.Contains('gradio_app.py') -or $_.CommandLine.Contains('launcher.en.py') -or $_.CommandLine.Contains('launcher.zh.py'))
}}
foreach ($p in $procs) {{
  try {{
    Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
    Write-Output $p.ProcessId
  }} catch {{}}
}}
"""
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            check=False,
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.isdigit():
                pid_value = int(line)
                if pid_value not in stopped:
                    stopped.append(pid_value)

    clear_pid()
    state = read_json(STATE_PATH)
    state.update({"running": False, "stopped_at": now_iso(), "stopped_pids": stopped})
    write_json(STATE_PATH, state)
    return {"stopped_pids": stopped, "state_path": str(STATE_PATH)}


def read_pid() -> int | None:
    if not PID_PATH.exists():
        return None
    text = PID_PATH.read_text(encoding="utf-8").strip()
    return int(text) if text.isdigit() else None


def clear_pid() -> None:
    try:
        PID_PATH.unlink()
    except FileNotFoundError:
        pass


def socket_ready(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def wait_for_ready(host: str, port: int, timeout_sec: int = READY_TIMEOUT_SEC) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if socket_ready(host, port):
            return
        time.sleep(2)
    raise ControllerError(f"Hunyuan API did not become ready on {host}:{port} within {timeout_sec}s.")


def base_url(host: str, port: int) -> str:
    return f"http://{host}:{port}"


def build_env() -> dict[str, str]:
    env = os.environ.copy()
    path_parts = [
        str(HUNYUAN_ROOT / "MinGit" / "cmd"),
        str(HUNYUAN_ROOT / "python_standalone" / "Scripts"),
    ]
    env["PATH"] = os.pathsep.join(path_parts + [env.get("PATH", "")])
    env["PYTHONPYCACHEPREFIX"] = str(HUNYUAN_ROOT / "pycache")
    env["HF_HUB_CACHE"] = str(HUNYUAN_ROOT / "HuggingFaceHub")
    env["HY3DGEN_MODELS"] = str(HUNYUAN_ROOT / "HuggingFaceHub")
    return env


def copy_u2net_if_needed() -> None:
    bundled = HUNYUAN_ROOT / "extras" / "u2net.onnx"
    target = Path.home() / ".u2net" / "u2net.onnx"
    if bundled.exists() and not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bundled, target)


def normalize_backend(version: str, texture: bool, backend: str = "auto") -> str:
    backend = (backend or "auto").strip().lower()
    if backend not in BACKEND_CHOICES:
        raise ControllerError(f"Unknown backend '{backend}'. Use one of: {', '.join(BACKEND_CHOICES)}.")
    if backend == "auto":
        if version == "2.0" and texture:
            return "api_low_vram"
        return "api"
    return backend


def default_profile(version: str = "2.0") -> str:
    config = load_launcher_config()
    program_config = config.get("Hunyuan3D-2.1" if version == "2.1" else "Hunyuan3D-2", {})
    return str(program_config.get("--profile", "2" if version == "2.0" else "5"))


def write_low_vram_api_server(program_dir: Path) -> Path:
    source_path = program_dir / "api_server.py"
    source = source_path.read_text(encoding="utf-8-sig")
    if "Hunyuan3DPaintPipeline.from_pretrained(tex_model_path)" not in source:
        raise ControllerError(f"Could not patch low-VRAM API server; expected texture loader not found in {source_path}")

    patched = source
    if "from pathlib import Path" not in patched:
        patched = patched.replace("import uuid\n", "import uuid\nfrom pathlib import Path\n", 1)
    patched = patched.replace(
        "from hy3dgen.rembg import BackgroundRemover\n",
        (
            f"PROGRAM_DIR = Path(r'''{str(program_dir)}''')\n"
            "if str(PROGRAM_DIR) not in sys.path:\n"
            "    sys.path.insert(0, str(PROGRAM_DIR))\n\n"
            "from hy3dgen.rembg import BackgroundRemover\n"
        ),
        1,
    )
    patched = patched.replace(
        "from hy3dgen.text2image import HunyuanDiTPipeline\n",
        "from hy3dgen.text2image import HunyuanDiTPipeline\nfrom mmgp import offload\n",
        1,
    )
    patched = patched.replace(
        "                 device='cuda',\n                 enable_tex=False):",
        "                 device='cuda',\n                 enable_tex=False,\n                 low_vram_mode=False,\n                 profile='2'):",
        1,
    )
    patched = patched.replace(
        "        if enable_tex:\n            self.pipeline_tex = Hunyuan3DPaintPipeline.from_pretrained(tex_model_path)\n",
        """        if enable_tex:
            self.pipeline_tex = Hunyuan3DPaintPipeline.from_pretrained(tex_model_path)
            if low_vram_mode:
                self.pipeline_tex.enable_model_cpu_offload()

        if low_vram_mode:
            profile_no = int(profile)
            pipe = offload.extract_models("i23d_worker", self.pipeline)
            if enable_tex:
                pipe.update(offload.extract_models("texgen_worker", self.pipeline_tex))
                try:
                    self.pipeline_tex.models["multiview_model"].pipeline.vae.use_slicing = True
                except Exception as error:
                    logger.warning(f"Could not enable texture VAE slicing: {error}")
            kwargs = {}
            if profile_no < 5:
                kwargs["pinnedMemory"] = "i23d_worker/model"
            if profile_no != 1 and profile_no != 3:
                kwargs["budgets"] = {"*": 2200}
            offload.default_verboseLevel = 1
            offload.profile(pipe, profile_no=profile_no, verboseLevel=1, **kwargs)
            logger.info(f"Enabled low-VRAM offload profile {profile_no}.")
""",
        1,
    )
    patched = patched.replace(
        "    parser.add_argument('--enable_tex', action='store_true')\n",
        "    parser.add_argument('--enable_tex', action='store_true')\n    parser.add_argument('--low_vram_mode', action='store_true')\n    parser.add_argument('--profile', type=str, default='2')\n",
        1,
    )
    patched = re.sub(
        r"worker = ModelWorker\(model_path=args\.model_path, device=args\.device, enable_tex=args\.enable_tex,\s*tex_model_path=args\.tex_model_path\)",
        (
            "worker = ModelWorker(model_path=args.model_path, device=args.device, enable_tex=args.enable_tex,\n"
            "                         tex_model_path=args.tex_model_path, low_vram_mode=args.low_vram_mode, profile=args.profile)"
        ),
        patched,
        count=1,
    )
    if "low_vram_mode=args.low_vram_mode" not in patched:
        raise ControllerError("Could not patch low-VRAM API server; ModelWorker startup call was not updated.")

    target_dir = STATE_DIR / "patched-api"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / "api_server_low_vram.py"
    target_path.write_text(patched, encoding="utf-8")
    return target_path


def api_command(
    version: str,
    host: str,
    port: int,
    texture: bool,
    backend: str = "auto",
    profile: str | None = None,
) -> tuple[Path, list[str], dict[str, Any]]:
    config = load_launcher_config()
    py = portable_python()
    resolved_backend = normalize_backend(version, texture, backend)
    resolved_profile = str(profile or default_profile(version))

    if version == "2.1":
        api_config = config.get("API-Hunyuan3D-2.1", {})
        program_dir = HUNYUAN_ROOT / "Hunyuan3D-2.1"
        command = [
            str(py),
            "-s",
            "api_server.py",
            "--host",
            host,
            "--port",
            str(port),
            "--model_path",
            str(api_config.get("--model_path", "tencent/Hunyuan3D-2.1")),
            "--subfolder",
            str(api_config.get("--subfolder", "hunyuan3d-dit-v2-1")),
            "--cache-path",
            str(STATE_DIR / "hy3d21_cache"),
        ]
        if api_config.get("--low_vram_mode", True):
            command.append("--low_vram_mode")
        settings = {
            "version": version,
            "texture": True,
            "backend": resolved_backend,
            "low_vram_mode": True,
            "profile": resolved_profile,
            "program_dir": str(program_dir),
        }
        return program_dir, command, settings

    api_config = config.get("API-Hunyuan3D-2", {})
    program_dir = HUNYUAN_ROOT / "Hunyuan3D-2"
    model_path = str(api_config.get("--model_path", "tencent/Hunyuan3D-2mini"))
    tex_model_path = str(api_config.get("--tex_model_path", api_config.get("--texgen_model_path", "tencent/Hunyuan3D-2")))
    script_name = "api_server.py"
    if resolved_backend == "api_low_vram":
        if not texture:
            raise ControllerError("api_low_vram backend is only useful when texture generation is enabled.")
        script_name = str(write_low_vram_api_server(program_dir))
    command = [
        str(py),
        "-s",
        script_name,
        "--host",
        host,
        "--port",
        str(port),
        "--model_path",
        model_path,
        "--tex_model_path",
        tex_model_path,
    ]
    if texture:
        command.append("--enable_tex")
    if resolved_backend == "api_low_vram":
        command.extend(["--low_vram_mode", "--profile", resolved_profile])
    settings = {
        "version": "2.0",
        "texture": texture,
        "backend": resolved_backend,
        "low_vram_mode": resolved_backend == "api_low_vram",
        "profile": resolved_profile,
        "model_path": model_path,
        "tex_model_path": tex_model_path,
        "program_dir": str(program_dir),
    }
    return program_dir, command, settings


def current_status(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> dict[str, Any]:
    state = read_json(STATE_PATH)
    pid = read_pid()
    ready = socket_ready(host, port)
    return {
        "ready": ready,
        "host": host,
        "port": port,
        "url": base_url(host, port),
        "pid": pid,
        "plugin_root": str(PLUGIN_ROOT),
        "config_path": str(CONFIG_PATH),
        "hunyuan_root": str(HUNYUAN_ROOT) if HUNYUAN_ROOT_TEXT else None,
        "default_output_dir": str(default_output_dir()),
        "state": state,
        "state_path": str(STATE_PATH),
        "log_path": str(LOG_PATH),
    }


def start_api(
    version: str = "2.0",
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    texture: bool = False,
    backend: str = "auto",
    profile: str | None = None,
    reset: bool = False,
    wait: bool = True,
) -> dict[str, Any]:
    if not HUNYUAN_ROOT.exists():
        raise ControllerError(f"Hunyuan portable root not found: {HUNYUAN_ROOT}")
    ensure_state_dir()
    copy_u2net_if_needed()

    existing = current_status(host, port)
    existing_state = existing.get("state") or {}
    if reset:
        stop_hunyuan_processes()
    elif existing["ready"]:
        resolved_backend = normalize_backend(version, texture, backend)
        same_version = existing_state.get("version") == version
        same_texture = bool(existing_state.get("texture")) == bool(texture or version == "2.1")
        same_backend = existing_state.get("backend", "api") == resolved_backend
        same_profile = str(existing_state.get("profile", default_profile(version))) == str(profile or default_profile(version))
        if same_version and same_texture and same_backend and same_profile:
            return {**existing, "message": "Hunyuan API is already running with matching settings."}
        stop_hunyuan_processes()

    program_dir, command, settings = api_command(version, host, port, texture, backend=backend, profile=profile)
    if not program_dir.exists():
        raise ControllerError(f"Hunyuan program directory not found: {program_dir}")

    log_file = LOG_PATH.open("a", encoding="utf-8")
    log_file.write(f"\n[{now_iso()}] Starting: {' '.join(command)}\n")
    log_file.flush()
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

    proc = subprocess.Popen(
        command,
        cwd=program_dir,
        env=build_env(),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    PID_PATH.write_text(str(proc.pid), encoding="utf-8")
    state = {
        **settings,
        "running": True,
        "pid": proc.pid,
        "host": host,
        "port": port,
        "url": base_url(host, port),
        "started_at": now_iso(),
        "command": command,
        "log_path": str(LOG_PATH),
    }
    write_json(STATE_PATH, state)
    if wait:
        wait_for_ready(host, port)
    return current_status(host, port)


def post_generate(host: str, port: int, payload: dict[str, Any], timeout_sec: int = REQUEST_TIMEOUT_SEC) -> bytes:
    timeout_sec = max(1, int(timeout_sec))
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url(host, port)}/generate",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise ControllerError(f"Hunyuan API returned HTTP {error.code}: {body}") from error
    except (TimeoutError, socket.timeout) as error:
        raise ControllerError(f"Hunyuan API timed out after {timeout_sec}s waiting for GLB output.") from error
    except urllib.error.URLError as error:
        if isinstance(error.reason, (TimeoutError, socket.timeout)):
            raise ControllerError(f"Hunyuan API timed out after {timeout_sec}s waiting for GLB output.") from error
        raise ControllerError(f"Could not reach Hunyuan API: {error}") from error
    except OSError as error:
        raise ControllerError(f"Hunyuan API connection failed while waiting for GLB output: {error}") from error


def generate_from_image(
    image: Path,
    output_dir: Path | None = None,
    asset_name: str | None = None,
    version: str = "2.0",
    texture: bool = False,
    seed: int = 1234,
    octree_resolution: int = 128,
    num_inference_steps: int = 5,
    guidance_scale: float = 5.0,
    face_count: int = 40000,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    backend: str = "auto",
    profile: str | None = None,
    reset: bool = False,
    request_timeout_sec: int = REQUEST_TIMEOUT_SEC,
) -> dict[str, Any]:
    image = image.expanduser().resolve()
    if not image.exists():
        raise ControllerError(f"Reference image not found: {image}")

    output_dir = (output_dir or default_output_dir()).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_name = normalize_asset_name(asset_name, image)
    output_path = output_dir / f"{safe_name}.glb"
    metadata_path = output_dir / f"{safe_name}.hy3d.json"

    resolved_backend = normalize_backend(version, texture, backend)
    resolved_profile = str(profile or default_profile(version))
    start_api(
        version=version,
        host=host,
        port=port,
        texture=texture,
        backend=resolved_backend,
        profile=resolved_profile,
        reset=reset,
        wait=True,
    )
    image_b64 = base64.b64encode(image.read_bytes()).decode("ascii")
    payload: dict[str, Any] = {
        "image": image_b64,
        "texture": bool(texture),
        "seed": seed,
        "octree_resolution": octree_resolution,
        "num_inference_steps": num_inference_steps,
        "guidance_scale": guidance_scale,
        "face_count": face_count,
        "type": "glb",
    }
    body = post_generate(host, port, payload, timeout_sec=request_timeout_sec)
    if body.lstrip().startswith(b"{"):
        raise ControllerError(f"Hunyuan API returned JSON instead of GLB: {body[:500].decode('utf-8', errors='replace')}")
    output_path.write_bytes(body)
    metadata = {
        "created_at": now_iso(),
        "source_image": str(image),
        "output_glb": str(output_path),
        "hunyuan": {
            "version": version,
            "texture": texture,
            "backend": resolved_backend,
            "profile": resolved_profile,
            "seed": seed,
            "octree_resolution": octree_resolution,
            "num_inference_steps": num_inference_steps,
            "guidance_scale": guidance_scale,
            "face_count": face_count,
            "request_timeout_sec": request_timeout_sec,
            "api": base_url(host, port),
        },
    }
    write_json(metadata_path, metadata)
    return {"output_glb": str(output_path), "metadata": str(metadata_path), "bytes": len(body)}


def normalize_batch_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not items:
        raise ControllerError("Batch must include at least one item.")
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        image_text = item.get("image_path") or item.get("image")
        if not image_text:
            raise ControllerError(f"Batch item {index} is missing image_path.")
        image_path = Path(str(image_text)).expanduser().resolve()
        if not image_path.exists():
            raise ControllerError(f"Batch item {index} image not found: {image_path}")
        normalized.append(
            {
                "index": index,
                "image_path": str(image_path),
                "asset_name": normalize_asset_name(item.get("asset_name") or item.get("name"), image_path),
                "prompt": item.get("prompt"),
                "status": "queued",
            }
        )
    return normalized


def enqueue_batch(
    items: list[dict[str, Any]],
    output_dir: Path | None = None,
    version: str = "2.0",
    texture: bool = False,
    seed: int = 1234,
    octree_resolution: int = 128,
    num_inference_steps: int = 5,
    guidance_scale: float = 5.0,
    face_count: int = 40000,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    backend: str = "auto",
    profile: str | None = None,
    reset: bool = False,
    continue_on_error: bool = True,
    request_timeout_sec: int = REQUEST_TIMEOUT_SEC,
    stop_api_on_item_error: bool = True,
) -> dict[str, Any]:
    ensure_state_dir()
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    normalized_items = normalize_batch_items(items)
    job_id = f"hy3d-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    resolved_output_dir = (output_dir or default_output_dir()).expanduser().resolve()
    resolved_backend = normalize_backend(version, texture, backend)
    resolved_profile = str(profile or default_profile(version))
    payload = {
        "job_id": job_id,
        "status": "queued",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "started_at": None,
        "finished_at": None,
        "pid": None,
        "log_path": str(job_log_path(job_id)),
        "status_path": str(job_path(job_id)),
        "output_dir": str(resolved_output_dir),
        "options": {
            "version": version,
            "texture": texture,
            "seed": seed,
            "octree_resolution": octree_resolution,
            "num_inference_steps": num_inference_steps,
            "guidance_scale": guidance_scale,
            "face_count": face_count,
            "host": host,
            "port": port,
            "backend": resolved_backend,
            "profile": resolved_profile,
            "reset": reset,
            "continue_on_error": continue_on_error,
            "request_timeout_sec": request_timeout_sec,
            "stop_api_on_item_error": stop_api_on_item_error,
        },
        "totals": {"queued": len(normalized_items), "running": 0, "completed": 0, "failed": 0},
        "items": normalized_items,
    }
    write_job(payload)

    log_file = job_log_path(job_id).open("a", encoding="utf-8")
    command = [sys.executable, str(Path(__file__).resolve()), "run-batch", "--job-id", job_id]
    creationflags = 0
    if os.name == "nt":
        creationflags = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )
    proc = subprocess.Popen(
        command,
        cwd=str(PLUGIN_ROOT),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    log_file.close()
    payload["pid"] = proc.pid
    payload["status"] = "running"
    payload["started_at"] = now_iso()
    write_job(payload)
    return {
        "job_id": job_id,
        "status": payload["status"],
        "pid": proc.pid,
        "status_path": payload["status_path"],
        "log_path": payload["log_path"],
        "items": len(normalized_items),
        "output_dir": str(resolved_output_dir),
    }


def recompute_totals(payload: dict[str, Any]) -> None:
    totals = {"queued": 0, "running": 0, "completed": 0, "failed": 0}
    for item in payload.get("items", []):
        status = item.get("status", "queued")
        if status in totals:
            totals[status] += 1
    payload["totals"] = totals


def run_batch_job(job_id: str) -> dict[str, Any]:
    payload = read_job(job_id)
    options = payload.get("options") or {}
    output_dir = Path(payload["output_dir"])
    payload["status"] = "running"
    payload["started_at"] = payload.get("started_at") or now_iso()
    write_job(payload)

    for item in payload.get("items", []):
        if item.get("status") == "completed":
            continue
        item["status"] = "running"
        item["started_at"] = now_iso()
        item.pop("error", None)
        recompute_totals(payload)
        write_job(payload)

        try:
            result = generate_from_image(
                image=Path(item["image_path"]),
                output_dir=output_dir,
                asset_name=item.get("asset_name"),
                version=str(options.get("version", "2.0")),
                texture=bool(options.get("texture", False)),
                seed=int(options.get("seed", 1234)),
                octree_resolution=int(options.get("octree_resolution", 128)),
                num_inference_steps=int(options.get("num_inference_steps", 5)),
                guidance_scale=float(options.get("guidance_scale", 5.0)),
                face_count=int(options.get("face_count", 40000)),
                host=str(options.get("host", DEFAULT_HOST)),
                port=int(options.get("port", DEFAULT_PORT)),
                backend=str(options.get("backend", "auto")),
                profile=str(options.get("profile", default_profile(str(options.get("version", "2.0"))))),
                reset=bool(options.get("reset", False)) and item.get("index") == 1,
                request_timeout_sec=int(options.get("request_timeout_sec", REQUEST_TIMEOUT_SEC)),
            )
            item["status"] = "completed"
            item["finished_at"] = now_iso()
            item["result"] = result
        except Exception as error:
            item["status"] = "failed"
            item["finished_at"] = now_iso()
            item["error"] = str(error)
            if bool(options.get("stop_api_on_item_error", True)):
                try:
                    item["recovery"] = {
                        "action": "stop_api_after_item_error",
                        "result": stop_hunyuan_processes(),
                    }
                except Exception as recovery_error:
                    item["recovery_error"] = str(recovery_error)
            if not bool(options.get("continue_on_error", True)):
                recompute_totals(payload)
                payload["status"] = "failed"
                payload["finished_at"] = now_iso()
                write_job(payload)
                raise

        recompute_totals(payload)
        write_job(payload)

    recompute_totals(payload)
    failed = payload["totals"]["failed"]
    payload["status"] = "completed_with_errors" if failed else "completed"
    payload["finished_at"] = now_iso()
    write_job(payload)
    return payload


def batch_status(job_id: str | None = None) -> dict[str, Any]:
    ensure_state_dir()
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    if job_id:
        return read_job(job_id)
    jobs = []
    for path in sorted(JOBS_DIR.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        payload = read_json(path)
        if payload:
            jobs.append(
                {
                    "job_id": payload.get("job_id"),
                    "status": payload.get("status"),
                    "created_at": payload.get("created_at"),
                    "updated_at": payload.get("updated_at"),
                    "totals": payload.get("totals"),
                    "status_path": str(path),
                }
            )
    return {"jobs": jobs[:20], "jobs_dir": str(JOBS_DIR)}


def diagnose() -> dict[str, Any]:
    config = load_launcher_config()
    has_hy3d20 = (HUNYUAN_ROOT / "Hunyuan3D-2" / "api_server.py").exists()
    has_hy3d21 = (HUNYUAN_ROOT / "Hunyuan3D-2.1" / "api_server.py").exists()
    hy3d20_config = config.get("Hunyuan3D-2", {})
    api20_config = config.get("API-Hunyuan3D-2", {})
    recommended_backend = "api_low_vram" if has_hy3d20 else "api"
    recommended_profile = str(hy3d20_config.get("--profile", "2"))
    configured_root = configured_hunyuan_root()
    discovered_roots = [str(path) for path in find_hunyuan_roots()]
    root_ready = bool(HUNYUAN_ROOT_TEXT and HUNYUAN_ROOT.exists() and has_hy3d20)
    return {
        "hunyuan_root": str(HUNYUAN_ROOT) if HUNYUAN_ROOT_TEXT else None,
        "root_source": "configured" if configured_root else ("auto_discovered" if HUNYUAN_ROOT_TEXT else "not_found"),
        "discovered_roots": discovered_roots,
        "available_versions": {
            "2.0": has_hy3d20,
            "2.1": has_hy3d21,
        },
        "launcher_texture_enabled": bool(hy3d20_config.get("_enable_texture_gen", False)),
        "launcher_model_select": hy3d20_config.get("_model_select", "--mini"),
        "launcher_turbo": bool(hy3d20_config.get("--turbo", True)),
        "launcher_profile": recommended_profile,
        "api_texture_model": api20_config.get("--tex_model_path", api20_config.get("--texgen_model_path", "tencent/Hunyuan3D-2")),
        "recommendation": {
            "version": "2.0",
            "backend": recommended_backend,
            "profile": recommended_profile,
            "texture": True,
            "reason": "Hunyuan3D-2 UI profile uses low-VRAM texture offload; the plain API backend does not.",
        },
        "manual_options": {
            "backend": list(BACKEND_CHOICES),
            "profile": ["1", "2", "3", "4", "5"],
        },
        "setup": {
            "ready": root_ready,
            "official_hunyuan_repo": HUNYUAN_REPO_URL,
            "expected_root_files": [
                "python_standalone\\python.exe",
                "Hunyuan3D-2\\api_server.py",
            ],
            "agent_next_step": (
                "Use the configured or auto-discovered Hunyuan root."
                if root_ready
                else "Ask the user for their Hunyuan3D portable root, or help them install Hunyuan3D from the official repo before running generation."
            ),
        },
    }


def load_batch_manifest(path: Path) -> dict[str, Any]:
    path = path.expanduser().resolve()
    payload = read_json(path)
    if not payload:
        raise ControllerError(f"Batch manifest is empty or invalid JSON: {path}")
    if isinstance(payload, list):
        return {"items": payload}
    return payload


def add_common_server_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--version", choices=["2.0", "2.1"], default="2.0")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--backend", choices=BACKEND_CHOICES, default="auto")
    parser.add_argument("--profile", default=None, help="Low-VRAM/offload profile. Hunyuan 2.0 UI default is 2.")
    parser.add_argument("--texture", action="store_true", help="Load/use texture generation where the selected API supports it.")
    parser.add_argument("--reset", action="store_true", help="Stop existing Hunyuan processes before starting.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Automate local Hunyuan3D GLB generation.")
    sub = parser.add_subparsers(dest="command", required=True)

    status_parser = sub.add_parser("status", help="Show API status.")
    status_parser.add_argument("--host", default=DEFAULT_HOST)
    status_parser.add_argument("--port", type=int, default=DEFAULT_PORT)

    start_parser = sub.add_parser("start", help="Start the Hunyuan API.")
    add_common_server_args(start_parser)
    start_parser.add_argument("--no-wait", action="store_true")

    stop_parser = sub.add_parser("stop", help="Stop Hunyuan API processes.")
    stop_parser.add_argument("--all", action="store_true", help="Accepted for readability; only Hunyuan processes are stopped.")

    gen_parser = sub.add_parser("generate", help="Generate a GLB from a reference image.")
    add_common_server_args(gen_parser)
    gen_parser.add_argument("--image", required=True, type=Path)
    gen_parser.add_argument("--output-dir", type=Path)
    gen_parser.add_argument("--name")
    gen_parser.add_argument("--seed", type=int, default=1234)
    gen_parser.add_argument("--octree-resolution", type=int, default=128)
    gen_parser.add_argument("--num-inference-steps", type=int, default=5)
    gen_parser.add_argument("--guidance-scale", type=float, default=5.0)
    gen_parser.add_argument("--face-count", type=int, default=40000)
    gen_parser.add_argument("--request-timeout-sec", type=int, default=REQUEST_TIMEOUT_SEC)

    enqueue_parser = sub.add_parser("enqueue", help="Start a background batch from a JSON manifest.")
    add_common_server_args(enqueue_parser)
    enqueue_parser.add_argument("--manifest", required=True, type=Path)
    enqueue_parser.add_argument("--output-dir", type=Path)
    enqueue_parser.add_argument("--seed", type=int, default=1234)
    enqueue_parser.add_argument("--octree-resolution", type=int, default=128)
    enqueue_parser.add_argument("--num-inference-steps", type=int, default=5)
    enqueue_parser.add_argument("--guidance-scale", type=float, default=5.0)
    enqueue_parser.add_argument("--face-count", type=int, default=40000)
    enqueue_parser.add_argument("--request-timeout-sec", type=int, default=REQUEST_TIMEOUT_SEC)
    enqueue_parser.add_argument("--stop-on-error", action="store_true")
    enqueue_parser.add_argument("--keep-api-on-error", action="store_true")

    batch_status_parser = sub.add_parser("batch-status", help="Show one batch job or recent batch jobs.")
    batch_status_parser.add_argument("--job-id")

    sub.add_parser("diagnose", help="Inspect the local Hunyuan install and recommend backend/profile settings.")

    run_batch_parser = sub.add_parser("run-batch", help=argparse.SUPPRESS)
    run_batch_parser.add_argument("--job-id", required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "status":
            result = current_status(args.host, args.port)
        elif args.command == "start":
            result = start_api(
                version=args.version,
                host=args.host,
                port=args.port,
                backend=args.backend,
                profile=args.profile,
                texture=args.texture,
                reset=args.reset,
                wait=not args.no_wait,
            )
        elif args.command == "stop":
            result = stop_hunyuan_processes()
        elif args.command == "generate":
            result = generate_from_image(
                image=args.image,
                output_dir=args.output_dir,
                asset_name=args.name,
                version=args.version,
                texture=args.texture,
                seed=args.seed,
                octree_resolution=args.octree_resolution,
                num_inference_steps=args.num_inference_steps,
                guidance_scale=args.guidance_scale,
                face_count=args.face_count,
                host=args.host,
                port=args.port,
                backend=args.backend,
                profile=args.profile,
                reset=args.reset,
                request_timeout_sec=args.request_timeout_sec,
            )
        elif args.command == "enqueue":
            manifest = load_batch_manifest(args.manifest)
            manifest_options = manifest.get("options") or {}
            result = enqueue_batch(
                items=manifest.get("items", []),
                output_dir=args.output_dir or (Path(manifest["output_dir"]) if manifest.get("output_dir") else None),
                version=str(manifest_options.get("version", args.version)),
                texture=bool(manifest_options.get("texture", args.texture)),
                seed=int(manifest_options.get("seed", args.seed)),
                octree_resolution=int(manifest_options.get("octree_resolution", args.octree_resolution)),
                num_inference_steps=int(manifest_options.get("num_inference_steps", args.num_inference_steps)),
                guidance_scale=float(manifest_options.get("guidance_scale", args.guidance_scale)),
                face_count=int(manifest_options.get("face_count", args.face_count)),
                host=str(manifest_options.get("host", args.host)),
                port=int(manifest_options.get("port", args.port)),
                backend=str(manifest_options.get("backend", args.backend)),
                profile=str(manifest_options.get("profile", args.profile or default_profile(str(manifest_options.get("version", args.version))))),
                reset=bool(manifest_options.get("reset", args.reset)),
                continue_on_error=not args.stop_on_error and bool(manifest_options.get("continue_on_error", True)),
                request_timeout_sec=int(manifest_options.get("request_timeout_sec", args.request_timeout_sec)),
                stop_api_on_item_error=not args.keep_api_on_error
                and bool(manifest_options.get("stop_api_on_item_error", True)),
            )
        elif args.command == "batch-status":
            result = batch_status(args.job_id)
        elif args.command == "diagnose":
            result = diagnose()
        elif args.command == "run-batch":
            result = run_batch_job(args.job_id)
        else:
            raise ControllerError(f"Unknown command: {args.command}")
    except ControllerError as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2), file=sys.stderr)
        return 2

    print(json.dumps({"ok": True, "result": result}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
