# Engine integration

The following are implementation entry points, not evidence that the engine was run. No .blend or Unreal project is committed.

## Blender

Install a compatible Blender distribution separately. Build and audit a public snapshot first. Run:

```bash
blender --background --python tools/blender_public_world.py -- --snapshot runs/tokyo --out runs/tokyo.blend --render runs/tokyo.png
```

The GLB is already in glTF Y-up metres; Blender imports it into Z-up. Do not apply an extra rotation or arbitrary 100x scale. Preserve the ENU origin, input hashes, textures and source credits. Inspect building/terrain alignment independently. The terrain surface is not a driving collision surface, especially below bridges and across underground roads.

## Unreal

Two distinct paths exist: Cesium for Unreal streams georeferenced 3D Tiles, while the PLATEAU SDK imports city models for authoring. Pin the engine/plugin versions in each integration project. References:

- https://cesium.com/learn/unreal/unreal-datasets/
- https://github.com/Project-PLATEAU/PLATEAU-SDK-for-Unreal

Keep appearance meshes, simulation road surfaces, lane topology, traffic controls and sensor labels separate. For static GLB authoring, local ENU metres map to Unreal coordinates in centimetres as `(100*x, -100*y, 100*z)`. Do not apply this local mapping again to georeferenced streaming tiles.

Before driving, provide control-point residuals, scale checks, normals/winding tests, collision sweeps, lane-width measurements, bridge/tunnel checks, and scene screenshots from ground level. A screenshot alone does not close these gates.

## CARLA legacy pilot

The included adapter targets matching CARLA 0.9.16 client/server and UE4, not unverified UE5 compatibility. Install the matching CARLA PythonAPI and agents separately.

```bash
python -m jevdrive.carla_bridge convert
python -m jevdrive.carla_bridge run --replace-world --mode baseline
```

`--replace-world` explicitly replaces the active simulator map: only use a dedicated simulator. It generates a road world from the bundled Kirchberg OpenDRIVE, not Tokyo. The public-world building GLB is not installed by this adapter. It uses simulator ground truth and a basic route controller, not camera perception. Source: https://carla.readthedocs.io/en/latest/tuto_G_openstreetmap/

Record exact client/server versions, map hash, seed, frame times, collision events and cleanup behavior. Shadow Jev evaluation must precede closed-loop Jev experiments. No interface to real vehicles is supported.
