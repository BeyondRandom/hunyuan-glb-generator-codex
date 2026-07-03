# Publishing

This project should be published as a Codex plugin marketplace repository.

## Recommended Repository Shape

```text
.
├── .agents/plugins/marketplace.json
├── docs/
├── install.ps1
├── plugins/
│   └── hunyuan-glb-generator/
│       ├── .codex-plugin/plugin.json
│       ├── .mcp.json
│       ├── README.md
│       ├── examples/
│       ├── scripts/
│       └── skills/
└── README.md
```

## Before Publishing

- Confirm no personal paths are present.
- Confirm no `config.local.json`, `.pyc`, or `__pycache__` files are present.
- Run plugin validation.
- Run a local install from a clean clone.
- Include `LICENSE`.
- Include `NOTICE` clarifying that Hunyuan3D and model weights are not bundled.
- Decide whether the repository is public or private.
- Add screenshots or short demo GIFs if you want a more polished GitHub landing page.

## GitHub Release Checklist

1. Create a repository, for example `hunyuan-glb-generator-codex`.
2. Push this folder as the repository root.
3. Add a license file.
4. Add topics such as `codex`, `mcp`, `hunyuan3d`, `glb`, `3d-assets`.
5. Test the install command from a fresh clone.
6. Create a release once the install path is verified.

## Codex Install From GitHub

Once published:

```powershell
codex plugin marketplace add OWNER/REPO
codex plugin add hunyuan-glb-generator@hunyuan-glb-generator-marketplace
```

Users still need to run configuration on their machine so the plugin knows where Hunyuan3D is installed:

```powershell
python .\plugins\hunyuan-glb-generator\scripts\configure_plugin.py --hunyuan-root "C:\path\to\Hunyuan3D2_WinPortable"
```

The root `install.ps1` combines marketplace registration, plugin install, and configuration for local clones.

## Public App Store Path

For a public ChatGPT app-style listing, this would need to become an Apps SDK app with a hosted MCP server or secure local-connection story, privacy policy, terms, and review-ready safety documentation. The Codex plugin marketplace/GitHub path is the clean first release.
