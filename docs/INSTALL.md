# Install

This repository is a Codex plugin marketplace. It contains one plugin: Hunyuan GLB Generator.

## Fast Install With GUI

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Gui
```

The installer asks for the Hunyuan3D portable root, writes per-user plugin config, registers this folder as a Codex marketplace, and installs the plugin when the Codex CLI is available.
Before opening the folder picker, it tries to auto-detect Hunyuan in common Windows locations.

## Hunyuan3D Requirement

This plugin controls an existing local Hunyuan3D install; it does not bundle Hunyuan3D or model weights.

Install Hunyuan3D from the official project if it is not already present:

```text
https://github.com/Tencent-Hunyuan/Hunyuan3D-2
```

The plugin expects a portable root containing:

```text
python_standalone\python.exe
Hunyuan3D-2\api_server.py
```

The installer and `hunyuan_diagnose` check common folders including `C:\AI`, `D:\AI`, `%USERPROFILE%\AI`, `%USERPROFILE%\Downloads`, and the Desktop. If a valid root is found, agents can use it automatically. If none is found, ask the user for the Hunyuan root or help them install Hunyuan3D first.

## Fast Install Without GUI

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 `
  -HunyuanRoot "C:\path\to\Hunyuan3D2_WinPortable"
```

If Hunyuan is already in a common folder, `-HunyuanRoot` can be omitted:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
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
powershell -NoProfile -ExecutionPolicy Bypass -Command "git clone https://github.com/BeyondRandom/hunyuan-glb-generator-codex.git; Set-Location hunyuan-glb-generator-codex; .\install.ps1 -Gui"
```

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
