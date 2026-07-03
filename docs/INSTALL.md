# Install

This repository is a Codex plugin marketplace. It contains one plugin: Hunyuan GLB Generator.

## Fast Install With GUI

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Gui
```

The installer asks for the Hunyuan3D portable root, writes per-user plugin config, registers this folder as a Codex marketplace, and installs the plugin when the Codex CLI is available.

## Fast Install Without GUI

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 `
  -HunyuanRoot "C:\path\to\Hunyuan3D2_WinPortable"
```

Optional default output folder:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 `
  -HunyuanRoot "C:\path\to\Hunyuan3D2_WinPortable" `
  -DefaultOutput "C:\path\to\project\GLB_Models\use"
```

## One-Line Clone And Install

After this repository is published, users can clone and start the GUI installer in one terminal command:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "git clone https://github.com/OWNER/REPO.git; Set-Location REPO; .\install.ps1 -Gui"
```

Replace `OWNER/REPO` and `REPO` with the published GitHub repository.

## Manual Install

```powershell
codex plugin marketplace add .
codex plugin add hunyuan-glb-generator@hunyuan-glb-generator-marketplace
cd .\plugins\hunyuan-glb-generator
python .\scripts\configure_plugin.py --hunyuan-root "C:\path\to\Hunyuan3D2_WinPortable"
```

Start a new Codex thread after installing or reconfiguring the plugin.

## What The Installer Writes

Machine-specific config is written outside the repository:

```text
%LOCALAPPDATA%\Codex\hunyuan-glb-generator\config.json
```

That keeps GitHub releases free of local paths while still letting the installed plugin find the user's Hunyuan3D setup.
