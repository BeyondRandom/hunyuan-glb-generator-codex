# Hunyuan GLB Generator Plugin

Codex plugin that exposes a local Hunyuan3D portable install as MCP tools for image-to-GLB generation.

## What It Does

- Starts and stops the local Hunyuan3D API.
- Generates one `.glb` from one local reference image.
- Enqueues background batches of reference images.
- Polls job status and reports generated paths, failures, and file sizes.
- Writes metadata next to generated assets.

The plugin uses the backend API. The Hunyuan/Gradio frontend does not need to stay open.

## Configure

Normal installs should write per-user config:

```powershell
python .\scripts\configure_plugin.py --hunyuan-root "C:\path\to\Hunyuan3D2_WinPortable"
```

Optional default output folder:

```powershell
python .\scripts\configure_plugin.py `
  --hunyuan-root "C:\path\to\Hunyuan3D2_WinPortable" `
  --default-output "C:\path\to\project\GLB_Models\use"
```

This writes:

```text
%LOCALAPPDATA%\Codex\hunyuan-glb-generator\config.json
```

Use `--plugin-local` only for development clones where config should live beside the plugin.

## Use From Codex

After installing/enabling the plugin in Codex, start a new thread and ask:

```text
Use Hunyuan GLB Generator to make a low-poly GLB from C:\path\reference.png.
```

For batches:

```text
Use Hunyuan GLB Generator to enqueue this manifest, wait for completion, and summarize generated GLB paths and sizes: C:\path\batch.json
```

## Direct CLI

These commands work without MCP:

```powershell
python .\scripts\hy3d_asset_controller.py status
python .\scripts\hy3d_asset_controller.py start --version 2.0
python .\scripts\hy3d_asset_controller.py start --version 2.0 --texture --reset
python .\scripts\hy3d_asset_controller.py generate --image "C:\path\reference.png" --name "asset_name"
python .\scripts\hy3d_asset_controller.py generate --image "C:\path\reference.png" --name "asset_name" --texture --reset
python .\scripts\hy3d_asset_controller.py enqueue --manifest "C:\path\batch.json"
python .\scripts\hy3d_asset_controller.py batch-status --job-id "hy3d-..."
```

## Small GLB Settings

Start with:

- `texture: false`
- `octree_resolution: 64`
- `num_inference_steps: 3`
- `guidance_scale: 4.0`
- `face_count: 8000`

Raise those settings only when the model is too weak.

For colored/textured low-poly GLBs, use `texture: true` and `reset: true` in the manifest, or add `--texture --reset` to CLI calls when changing an existing API from untextured mode. A good compact starting point is:

- `texture: true`
- `reset: true`
- `octree_resolution: 64`
- `num_inference_steps: 5`
- `guidance_scale: 4.5`
- `face_count: 8000`

## Examples

- `examples/reference_images/` contains simple sample inputs.
- `examples/batch_manifest.low-poly.json` runs a tiny low-poly batch.
- `examples/batch_manifest.textured-low-poly.json` runs the same sample with texture generation enabled.
- `examples/batch_manifest.example.json` is a template for real project batches.

Run from this plugin folder:

```powershell
python .\scripts\hy3d_asset_controller.py enqueue --manifest .\examples\batch_manifest.low-poly.json
```

Textured sample:

```powershell
python .\scripts\hy3d_asset_controller.py enqueue --manifest .\examples\batch_manifest.textured-low-poly.json
```

## Safety Notes

This plugin controls local processes and can use substantial GPU/VRAM. Keep it local to machines where the user has intentionally installed Hunyuan3D. It only stops Python processes whose command line points inside the configured Hunyuan root.

## License

The plugin code is MIT licensed. Hunyuan3D itself is not included in this repository and is governed by Tencent's own license terms.
