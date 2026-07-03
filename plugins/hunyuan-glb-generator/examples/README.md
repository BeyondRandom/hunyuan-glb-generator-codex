# Examples

This folder contains a tiny low-poly batch for testing the plugin after install.

## Reference Images

`reference_images/` contains three simple example inputs:

- `corn_crop_tile.png`
- `water_bucket_carry_item.png`

They are intentionally simple: one centered object, bright background, strong silhouette, no labels, no clutter.

## Run The Low-Poly Batch

From `plugins/hunyuan-glb-generator`:

```powershell
python .\scripts\hy3d_asset_controller.py enqueue --manifest .\examples\batch_manifest.low-poly.json
```

Then poll the returned job id:

```powershell
python .\scripts\hy3d_asset_controller.py batch-status --job-id "hy3d-..."
```

Outputs are written to:

```text
examples\output
```

## Template Manifest

Use `batch_manifest.example.json` as a copy-and-edit template for real projects. Prefer absolute image and output paths for project work.
