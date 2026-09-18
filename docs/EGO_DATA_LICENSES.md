# Derived ego-view images — source and processing notice

Reviewed 2026-09-18. This is an attribution record for the selected demonstration,
not legal advice or a blanket relicensing of arbitrary downloaded data.

## Public city model

Source: Tokyo / Project PLATEAU, Chiyoda-ku 2025, 3D Tiles/MVT v5.
Dataset: https://www.geospatial.jp/ckan/dataset/plateau-13101-chiyoda-ku-2025/resource/7f56c150-f6b2-4d1a-bab3-6452298356cc
The resource's license entry refers to PLATEAU Site Policy section 3.
https://www.mlit.go.jp/plateau/site-policy/

The currently published policy covers open city models hosted at G-Spatial,
requires attribution and marking alterations, and permits CC BY 4.0-compatible
reuse where separate rights notices do not apply. Model copyright belongs to
its municipal data owner. This demo is not an official MLIT/Tokyo product.

We convert source meshes and textures into a local ENU scene and render a
configured forward-facing virtual camera. Material shading and daylight are
inspection settings, not measured conditions. Geometry is not generatively
filled. Acquisition year, dataset edition and photography date are distinct.

## Ground imagery and terrain

Source: MLIT PLATEAU-Ortho 2023 delivery set and PLATEAU-Terrain.
https://docs.plateauview.mlit.go.jp/datasets/ortho/
https://docs.plateauview.mlit.go.jp/datasets/terrain/
Terrain retains the upstream attribution PLATEAU | Mapterhorn | GSI.
https://mapterhorn.com/  https://www.gsi.go.jp/
Source heights are provider ellipsoidal heights, not orthometric elevations.
Do not remove original source credits. This distribution contains derived
rendered images, not redistribution of the raw terrain database or city mesh.

## Camera path

Copyright OpenStreetMap contributors, ODbL 1.0.
https://www.openstreetmap.org/copyright
https://opendatacommons.org/licenses/odbl/1-0/
The inspection follows a clipped source centerline; it does not assert a lane,
traffic permission or surveyed road width. Attribution is embedded in frames.

## Evidence boundary

A moving virtual camera is not autonomous driving. No Jev action or vehicle
control is used in the public-world inspection video. No geometric-accuracy,
photorealism, sensor-recognition or driving-safety claim accompanies the video.
The video and frame sidecars identify actual Blender execution and camera poses.
Do not describe this output as real on-road camera footage.
