# Hunyuan GLB Generator for Codex

Turn local reference images into GLB assets from Codex using a local Hunyuan3D portable install.

This repository is a Codex plugin marketplace. It packages one plugin, `hunyuan-glb-generator`, with:

- a Codex skill that teaches the agent the image-to-GLB workflow
- an MCP server that exposes generation tools to Codex
- scripts for starting/stopping the local Hunyuan3D API
- background batch generation with status polling
- low-poly example manifests and reference images

## Why This Is Useful

Hunyuan3D can turn images into 3D models, but managing the local server, settings, output files, and repeated batches is tedious. This plugin lets Codex handle that loop:

1. collect or create reference images
2. start the local Hunyuan3D backend
3. enqueue image-to-GLB jobs
4. poll until they finish
5. save GLBs and metadata into a project asset folder
6. report results, errors, and file sizes

The Hunyuan/Gradio frontend does not need to be open. The plugin uses the backend API.

## Requirements

- Windows
- Codex with plugin support
- Python 3 on PATH
- Git, if installing from GitHub
- Local Hunyuan3D portable install containing:
  - `python_standalone\python.exe`
  - `Hunyuan3D-2\api_server.py`

## Quick Install

Clone the repository, then run:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Gui
```

The GUI installer asks for the Hunyuan3D portable root, writes per-user config, registers this folder as a Codex marketplace, and installs the plugin when the Codex CLI is available.

Noninteractive install:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 `
  -HunyuanRoot "C:\path\to\Hunyuan3D2_WinPortable"
```

After install, start a new Codex thread and ask:

```text
Use Hunyuan GLB Generator to generate a low-poly GLB from C:\path\to\reference.png.
```

## One-Line Clone And Install

After this repository is published, users can run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "git clone https://github.com/OWNER/REPO.git; Set-Location REPO; .\install.ps1 -Gui"
```

Replace `OWNER/REPO` and `REPO` with the published GitHub repository.

## What Codex Gets

Once installed, Codex can use these MCP tools:

- `hunyuan_status`
- `hunyuan_start_api`
- `hunyuan_stop_api`
- `hunyuan_generate_from_image`
- `hunyuan_enqueue_image_batch`
- `hunyuan_batch_status`

The bundled skill tells Codex when to use those tools, which settings are best for small GLBs, and how to run an agentic batch loop.

## Examples

The plugin includes sample reference images and batch manifests:

- `plugins/hunyuan-glb-generator/examples/reference_images/`
- `plugins/hunyuan-glb-generator/examples/batch_manifest.low-poly.json`
- `plugins/hunyuan-glb-generator/examples/batch_manifest.example.json`

Run the low-poly example from the plugin folder:

```powershell
cd .\plugins\hunyuan-glb-generator
python .\scripts\hy3d_asset_controller.py enqueue --manifest .\examples\batch_manifest.low-poly.json
```

See [Batch Workflows](docs/BATCH_WORKFLOWS.md) for reference-image guidance and batch prompts.

## Documentation

- [Install](docs/INSTALL.md)
- [Batch Workflows](docs/BATCH_WORKFLOWS.md)
- [Publishing](docs/PUBLISHING.md)
- [Plugin README](plugins/hunyuan-glb-generator/README.md)

## Safety

This plugin controls local Hunyuan3D processes and can use substantial GPU/VRAM. It only stops Python processes whose command line points inside the configured Hunyuan root. Machine-specific config is written to:

```text
%LOCALAPPDATA%\Codex\hunyuan-glb-generator\config.json
```

No local Hunyuan path needs to be committed to GitHub.

## License

This plugin is released under the [MIT License](LICENSE).

This repository does not include Hunyuan3D, Hunyuan3D model weights, Tencent source code, Tencent model files, or Tencent trademarks. Users must install Hunyuan3D separately and comply with the license terms that apply to their own use. Tencent is not affiliated with, associated with, sponsoring, or endorsing this plugin. See [NOTICE](NOTICE).
