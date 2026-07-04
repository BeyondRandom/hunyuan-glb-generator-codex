#!/usr/bin/env python3
"""Configure the Hunyuan GLB Generator plugin for this machine."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Codex" / "hunyuan-glb-generator"
USER_CONFIG_PATH = STATE_DIR / "config.json"
PLUGIN_CONFIG_PATH = PLUGIN_ROOT / "config.local.json"
MCP_PATH = PLUGIN_ROOT / ".mcp.json"
HUNYUAN_REPO_URL = "https://github.com/Tencent-Hunyuan/Hunyuan3D-2"


def default_hunyuan_root() -> Path | None:
    roots = find_hunyuan_roots()
    return roots[0] if roots else None


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


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Configure the Hunyuan GLB Generator Codex plugin.")
    parser.add_argument(
        "--hunyuan-root",
        type=Path,
        help="Path to the portable Hunyuan3D root that contains python_standalone and Hunyuan3D-2.",
    )
    parser.add_argument(
        "--python",
        type=Path,
        default=Path(sys.executable),
        help="Python executable Codex should use to start the plugin MCP server.",
    )
    parser.add_argument("--default-output", type=Path, help="Optional default folder for generated GLB files.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8081)
    parser.add_argument(
        "--plugin-local",
        action="store_true",
        help="Write config.local.json inside the plugin folder instead of the per-user Codex config.",
    )
    parser.add_argument(
        "--write-local-mcp",
        action="store_true",
        help="Rewrite this clone's .mcp.json with absolute local paths. Not needed for normal GitHub installs.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print config without writing files.")
    args = parser.parse_args(argv)

    hunyuan_root = (args.hunyuan_root or default_hunyuan_root())
    if not hunyuan_root:
        print("Could not auto-detect Hunyuan3D. Pass --hunyuan-root.", file=sys.stderr)
        print(f"Official Hunyuan3D repo: {HUNYUAN_REPO_URL}", file=sys.stderr)
        print("Expected portable root files: python_standalone\\python.exe and Hunyuan3D-2\\api_server.py", file=sys.stderr)
        return 2
    hunyuan_root = hunyuan_root.expanduser().resolve()
    if not looks_like_hunyuan_root(hunyuan_root):
        print(f"Path does not look like a supported Hunyuan3D portable root: {hunyuan_root}", file=sys.stderr)
        return 2

    python_path = args.python.expanduser().resolve()
    if not python_path.exists():
        print(f"Python executable not found: {python_path}", file=sys.stderr)
        return 2

    config: dict[str, Any] = {
        "hunyuan_root": str(hunyuan_root),
        "host": args.host,
        "port": args.port,
    }
    if args.default_output:
        config["default_output_dir"] = str(args.default_output.expanduser().resolve())

    mcp = {
        "mcpServers": {
            "hunyuan-glb-generator": {
                "command": str(python_path),
                "args": [str(PLUGIN_ROOT / "scripts" / "hunyuan_mcp_server.py")],
                "env": {
                    "HUNYUAN_GLB_PLUGIN_ROOT": str(PLUGIN_ROOT),
                    "HUNYUAN_GLB_CONFIG": str(USER_CONFIG_PATH),
                    "HY3D_PORTABLE_ROOT": str(hunyuan_root),
                },
                "startup_timeout_sec": 30,
            }
        }
    }
    if args.default_output:
        mcp["mcpServers"]["hunyuan-glb-generator"]["env"]["HUNYUAN_GLB_DEFAULT_OUTPUT"] = str(
            args.default_output.expanduser().resolve()
        )

    if args.dry_run:
        print(json.dumps({"config": config, ".mcp.json": mcp}, indent=2))
        return 0

    config_path = PLUGIN_CONFIG_PATH if args.plugin_local else USER_CONFIG_PATH
    config_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(config_path, config)
    result = {"ok": True, "config_path": str(config_path)}
    if args.write_local_mcp:
        write_json(MCP_PATH, mcp)
        result["mcp_path"] = str(MCP_PATH)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
