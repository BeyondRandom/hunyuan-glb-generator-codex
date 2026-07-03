#!/usr/bin/env python3
"""Tiny stdio MCP server for the local Hunyuan GLB controller.

It implements the MCP tool surface with no third-party dependencies. Codex can
also use the controller script directly if this server is not loaded yet.
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from hy3d_asset_controller import (  # noqa: E402
    DEFAULT_HOST,
    DEFAULT_PORT,
    ControllerError,
    batch_status,
    current_status,
    enqueue_batch,
    generate_from_image,
    start_api,
    stop_hunyuan_processes,
)


PROTOCOL_VERSION = "2024-11-05"


TOOLS: list[dict[str, Any]] = [
    {
        "name": "hunyuan_status",
        "description": "Check whether the local Hunyuan3D API is reachable and show the tracked PID/log paths.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "host": {"type": "string", "default": DEFAULT_HOST},
                "port": {"type": "integer", "default": DEFAULT_PORT},
            },
        },
    },
    {
        "name": "hunyuan_start_api",
        "description": "Start the local Hunyuan3D API server from the portable Windows bundle.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "version": {"type": "string", "enum": ["2.0", "2.1"], "default": "2.0"},
                "texture": {"type": "boolean", "default": False},
                "reset": {"type": "boolean", "default": False},
                "host": {"type": "string", "default": DEFAULT_HOST},
                "port": {"type": "integer", "default": DEFAULT_PORT},
            },
        },
    },
    {
        "name": "hunyuan_stop_api",
        "description": "Stop Hunyuan3D API/Gradio/launcher Python processes under the configured portable install.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "hunyuan_generate_from_image",
        "description": "Generate a GLB from a local reference image and save it into a project asset folder.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "image_path": {"type": "string", "description": "Local PNG/JPG reference image path."},
                "asset_name": {"type": "string", "description": "Output GLB base filename without extension."},
                "output_dir": {"type": "string", "description": "Destination folder. Defaults to the configured output folder or current project."},
                "version": {"type": "string", "enum": ["2.0", "2.1"], "default": "2.0"},
                "texture": {"type": "boolean", "default": False},
                "seed": {"type": "integer", "default": 1234},
                "octree_resolution": {"type": "integer", "default": 128},
                "num_inference_steps": {"type": "integer", "default": 5},
                "guidance_scale": {"type": "number", "default": 5.0},
                "face_count": {"type": "integer", "default": 40000},
                "reset": {"type": "boolean", "default": False},
                "host": {"type": "string", "default": DEFAULT_HOST},
                "port": {"type": "integer", "default": DEFAULT_PORT},
            },
            "required": ["image_path"],
        },
    },
    {
        "name": "hunyuan_enqueue_image_batch",
        "description": "Start a background queue that turns multiple local reference images into GLB files one at a time.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "description": "Items with image_path and optional asset_name/prompt.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "image_path": {"type": "string"},
                            "asset_name": {"type": "string"},
                            "prompt": {"type": "string"},
                        },
                        "required": ["image_path"],
                    },
                },
                "output_dir": {"type": "string", "description": "Destination folder. Defaults to the configured output folder or current project."},
                "version": {"type": "string", "enum": ["2.0", "2.1"], "default": "2.0"},
                "texture": {"type": "boolean", "default": False},
                "seed": {"type": "integer", "default": 1234},
                "octree_resolution": {"type": "integer", "default": 128},
                "num_inference_steps": {"type": "integer", "default": 5},
                "guidance_scale": {"type": "number", "default": 5.0},
                "face_count": {"type": "integer", "default": 40000},
                "reset": {"type": "boolean", "default": False},
                "continue_on_error": {"type": "boolean", "default": True},
                "host": {"type": "string", "default": DEFAULT_HOST},
                "port": {"type": "integer", "default": DEFAULT_PORT},
            },
            "required": ["items"],
        },
    },
    {
        "name": "hunyuan_batch_status",
        "description": "Read progress/results for a Hunyuan GLB batch job, or list recent jobs if no job_id is given.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
            },
        },
    },
]


def read_message() -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if line == b"":
            return None
        line = line.decode("ascii", errors="replace").strip()
        if not line:
            break
        key, _, value = line.partition(":")
        headers[key.lower()] = value.strip()
    length = int(headers.get("content-length", "0"))
    if length <= 0:
        return None
    raw = sys.stdin.buffer.read(length)
    return json.loads(raw.decode("utf-8"))


def write_message(payload: dict[str, Any]) -> None:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii"))
    sys.stdout.buffer.write(raw)
    sys.stdout.buffer.flush()


def text_result(payload: Any, is_error: bool = False) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(payload, indent=2) if not isinstance(payload, str) else payload,
            }
        ],
        "isError": is_error,
    }


def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "hunyuan_status":
        return text_result(current_status(arguments.get("host", DEFAULT_HOST), int(arguments.get("port", DEFAULT_PORT))))
    if name == "hunyuan_start_api":
        return text_result(
            start_api(
                version=arguments.get("version", "2.0"),
                texture=bool(arguments.get("texture", False)),
                reset=bool(arguments.get("reset", False)),
                host=arguments.get("host", DEFAULT_HOST),
                port=int(arguments.get("port", DEFAULT_PORT)),
            )
        )
    if name == "hunyuan_stop_api":
        return text_result(stop_hunyuan_processes())
    if name == "hunyuan_generate_from_image":
        output_dir = arguments.get("output_dir")
        return text_result(
            generate_from_image(
                image=Path(arguments["image_path"]),
                output_dir=Path(output_dir) if output_dir else None,
                asset_name=arguments.get("asset_name"),
                version=arguments.get("version", "2.0"),
                texture=bool(arguments.get("texture", False)),
                seed=int(arguments.get("seed", 1234)),
                octree_resolution=int(arguments.get("octree_resolution", 128)),
                num_inference_steps=int(arguments.get("num_inference_steps", 5)),
                guidance_scale=float(arguments.get("guidance_scale", 5.0)),
                face_count=int(arguments.get("face_count", 40000)),
                reset=bool(arguments.get("reset", False)),
                host=arguments.get("host", DEFAULT_HOST),
                port=int(arguments.get("port", DEFAULT_PORT)),
            )
        )
    if name == "hunyuan_enqueue_image_batch":
        output_dir = arguments.get("output_dir")
        return text_result(
            enqueue_batch(
                items=arguments.get("items") or [],
                output_dir=Path(output_dir) if output_dir else None,
                version=arguments.get("version", "2.0"),
                texture=bool(arguments.get("texture", False)),
                seed=int(arguments.get("seed", 1234)),
                octree_resolution=int(arguments.get("octree_resolution", 128)),
                num_inference_steps=int(arguments.get("num_inference_steps", 5)),
                guidance_scale=float(arguments.get("guidance_scale", 5.0)),
                face_count=int(arguments.get("face_count", 40000)),
                reset=bool(arguments.get("reset", False)),
                continue_on_error=bool(arguments.get("continue_on_error", True)),
                host=arguments.get("host", DEFAULT_HOST),
                port=int(arguments.get("port", DEFAULT_PORT)),
            )
        )
    if name == "hunyuan_batch_status":
        return text_result(batch_status(arguments.get("job_id")))
    raise ControllerError(f"Unknown tool: {name}")


def handle_request(message: dict[str, Any]) -> dict[str, Any] | None:
    if "id" not in message:
        return None
    request_id = message["id"]
    method = message.get("method")
    params = message.get("params") or {}
    try:
        if method == "initialize":
            result = {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "hunyuan-glb-generator", "version": "0.2.0"},
            }
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            result = call_tool(params["name"], params.get("arguments") or {})
        else:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    except Exception as error:
        message_text = str(error)
        if not isinstance(error, ControllerError):
            message_text = f"{message_text}\n{traceback.format_exc()}"
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": text_result(message_text, is_error=True),
        }


def main() -> int:
    while True:
        message = read_message()
        if message is None:
            return 0
        response = handle_request(message)
        if response is not None:
            write_message(response)


if __name__ == "__main__":
    raise SystemExit(main())
