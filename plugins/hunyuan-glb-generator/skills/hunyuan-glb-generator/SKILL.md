---
name: hunyuan-glb-generator
description: Generate GLB assets from local reference images through a user's configured Hunyuan3D/Hunyuan3D-2 portable install. Use when Codex needs to start or stop a local Hunyuan API, create one image-to-GLB model, enqueue batch GLB generation, poll model generation status, or run an agentic asset-generation loop.
---

# Hunyuan GLB Generator

Use this skill when the user wants Codex to generate or automate GLB assets through a local Hunyuan3D setup.

## Requirements

- The plugin must be configured with `scripts/configure_plugin.py` or equivalent environment variables.
- `HY3D_PORTABLE_ROOT` or `config.local.json` must point at a Hunyuan3D portable root that contains `python_standalone\python.exe` and `Hunyuan3D-2\api_server.py`.
- The preferred backend is the Hunyuan3D API server. Do not use the Gradio/front-end UI unless the backend is unavailable and the user explicitly wants UI automation.

## Behavior

- Prefer backend API automation over clicking the UI.
- The front end does not need to be visible to save a GLB. The API returns GLB bytes, and the controller writes them directly.
- Do not kill all Python processes. Only stop Hunyuan processes whose command line points inside the configured Hunyuan root.
- Prompt-to-model is image-first: create or collect a reference image, save it locally, then call image-to-GLB generation.
- Use texture generation only when the user asks for it or quality requires it. Texture startup is heavier and may need more VRAM.
- For multiple assets, use the background batch queue. Do not run many GPU generations in parallel unless the user explicitly asks for a stress test.
- Batch jobs return a `job_id` immediately. Poll status to collect finished GLB paths and errors.

## Direct Controller

If MCP tools are unavailable, use the controller directly from the plugin root:

```powershell
python .\scripts\hy3d_asset_controller.py status
python .\scripts\hy3d_asset_controller.py start --version 2.0
python .\scripts\hy3d_asset_controller.py generate --image "C:\path\reference.png" --name "asset_name"
python .\scripts\hy3d_asset_controller.py enqueue --manifest "C:\path\batch.json"
python .\scripts\hy3d_asset_controller.py batch-status --job-id "hy3d-..."
```

Add `--texture` for textured output and `--reset` when changing API mode or clearing a stale run.

## Batch Manifest

Use this shape for queued generation:

```json
{
  "output_dir": "C:\\path\\to\\generated-glbs",
  "options": {
    "version": "2.0",
    "texture": false,
    "seed": 1234,
    "octree_resolution": 64,
    "num_inference_steps": 3,
    "guidance_scale": 4.0,
    "face_count": 8000,
    "continue_on_error": true
  },
  "items": [
    {
      "image_path": "C:\\path\\corn_reference.png",
      "asset_name": "corn_crop_tile",
      "prompt": "Low-poly corn crop tile"
    }
  ]
}
```

For smallest game-ready GLBs, start with `texture: false`, `octree_resolution: 64`, `num_inference_steps: 3`, `guidance_scale: 4.0`, and `face_count: 8000`. Increase only when the output is too weak.

## MCP Tools

When the plugin is installed in a fresh Codex thread, the MCP server should expose:

- `hunyuan_status`
- `hunyuan_start_api`
- `hunyuan_stop_api`
- `hunyuan_generate_from_image`
- `hunyuan_enqueue_image_batch`
- `hunyuan_batch_status`

Use `hunyuan_generate_from_image` for one asset when the user is okay waiting for completion. Use `hunyuan_enqueue_image_batch` when the user asks for multiple assets or an agentic generation loop.

## Agentic Loop

1. Make or collect reference images in a dedicated reference folder.
2. Name each planned asset with a game-safe file stem.
3. Enqueue the batch with one item per image.
4. Poll `hunyuan_batch_status` until `status` is `completed` or `completed_with_errors`.
5. Inspect generated `.glb` paths and metadata JSON.
6. If an asset is poor, improve the reference image or adjust settings, then enqueue only that item again.

Use stable, game-friendly names such as `corn_crop_tile`, `builder_ev_cart`, or `water_bucket_carry_item`. Avoid spaces. Generated metadata is written beside each `.glb` as `<asset>.hy3d.json`.
