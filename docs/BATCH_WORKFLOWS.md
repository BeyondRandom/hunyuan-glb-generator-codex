# Batch Workflows

The plugin is image-first: collect reference images, enqueue them, then let Codex poll the batch status until GLBs are written.

## Good Reference Images

Use images that are:

- one object or tile per image
- centered with the whole object visible
- bright and high contrast
- simple background
- three-quarter or front-facing view for objects
- top-down or isometric view for tiles
- named with stable game-friendly file names

Avoid:

- busy scenes with multiple objects
- cropped objects
- tiny subjects surrounded by empty space
- heavy shadows or dark backgrounds
- text labels or UI overlays
- multiple candidate views in one image

## Low-Poly Test Batch

From `plugins/hunyuan-glb-generator`:

```powershell
python .\scripts\hy3d_asset_controller.py enqueue --manifest .\examples\batch_manifest.low-poly.json
```

Then check status:

```powershell
python .\scripts\hy3d_asset_controller.py batch-status --job-id "hy3d-..."
```

The sample manifest writes output to:

```text
plugins\hunyuan-glb-generator\examples\output
```

## Codex Agent Prompt

After installing the plugin, a user can ask Codex:

```text
Use Hunyuan GLB Generator to enqueue plugins\hunyuan-glb-generator\examples\batch_manifest.low-poly.json, wait for completion, and summarize generated GLB paths and sizes.
```

For a project asset folder:

```text
Use Hunyuan GLB Generator to turn every PNG in C:\path\to\reference_queue into small low-poly GLBs in C:\path\to\GLB_Models\use. Use texture off, face_count 8000, octree_resolution 64, and continue on error.
```

For colored/textured output:

```text
Use Hunyuan GLB Generator to turn every PNG in C:\path\to\reference_queue into textured low-poly GLBs in C:\path\to\generated_textured_glbs. Use texture on, reset the API into texture mode, face_count 8000, octree_resolution 64, num_inference_steps 5, guidance_scale 4.5, and continue on error.
```

## Recommended Small-GLB Settings

Smallest untextured geometry:

```json
{
  "version": "2.0",
  "texture": false,
  "seed": 1234,
  "octree_resolution": 64,
  "num_inference_steps": 3,
  "guidance_scale": 4.0,
  "face_count": 8000,
  "continue_on_error": true
}
```

Increase `face_count`, `octree_resolution`, or `num_inference_steps` only when the output does not read clearly enough.

Colored/textured low-poly output:

```json
{
  "version": "2.0",
  "texture": true,
  "reset": true,
  "seed": 1234,
  "octree_resolution": 64,
  "num_inference_steps": 5,
  "guidance_scale": 4.5,
  "face_count": 8000,
  "continue_on_error": true
}
```

Use `reset: true` when switching an already-running Hunyuan API from untextured to textured mode so the API restarts with `--enable_tex`.
