"""Render Genesis MPM state in Isaac Sim as a three-second close-up video."""
import argparse
import json
import os
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--state", type=Path, default=ROOT / "outputs" / "mpm-state.npz")
parser.add_argument("--surface", type=Path, default=ROOT / "outputs" / "mpm-surface.npz")
parser.add_argument("--output", type=Path, default=ROOT / "outputs" / "butter-spread.mp4")
parser.add_argument("--width", type=int, default=1280)
parser.add_argument("--height", type=int, default=720)
parser.add_argument("--frames", type=int, default=0, help="0 renders all frames")
parser.add_argument("--gui", action="store_true")
args = parser.parse_args()
data = np.load(args.state)
surface = np.load(args.surface)
particles = data["particles"]
knife_positions = data["knife_positions"]
if len(surface["vertex_offsets"]) != len(particles) + 1:
    raise ValueError("Surface/state frame counts differ; rebuild the surface from this state")
count = len(particles) if args.frames == 0 else min(args.frames, len(particles))
args.output.parent.mkdir(parents=True, exist_ok=True)

os.environ.setdefault("OMNI_KIT_ACCEPT_EULA", "YES")
from isaacsim import SimulationApp
app = SimulationApp({"headless": not args.gui, "width": args.width,
                     "height": args.height, "anti_aliasing": 3})

try:
    import omni.usd
    import omni.replicator.core as rep
    import imageio_ffmpeg
    from PIL import Image
    from pxr import Gf, Sdf, UsdGeom, UsdShade, UsdLux, Vt
    from scene_assets import make_scene_assets

    ctx = omni.usd.get_context()
    ctx.new_stage()
    stage = ctx.get_stage()
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1)
    root = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(root.GetPrim())

    def material(name, color, roughness=0.5, metallic=0.0):
        m = UsdShade.Material.Define(stage, f"/World/Looks/{name}")
        s = UsdShade.Shader.Define(stage, f"/World/Looks/{name}/Shader")
        s.CreateIdAttr("UsdPreviewSurface")
        s.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
        s.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(roughness)
        s.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(metallic)
        m.CreateSurfaceOutput().ConnectToSource(s.ConnectableAPI(), "surface")
        return m

    mats = {"butter": material("Butter", (0.96, 0.72, 0.22), 0.28)}

    def bind(prim, name):
        UsdShade.MaterialBindingAPI.Apply(prim).Bind(mats[name])

    set_knife_pose = make_scene_assets(
        stage, ROOT / "assets", knife_positions[0])

    butter = UsdGeom.Mesh.Define(stage, "/World/Butter/Surface")
    butter.CreateSubdivisionSchemeAttr("none")
    bind(butter.GetPrim(), "butter")
    dome = UsdLux.DomeLight.Define(stage, "/World/Lights/Dome")
    dome.CreateIntensityAttr(700)
    key = UsdLux.SphereLight.Define(stage, "/World/Lights/Key")
    key.CreateIntensityAttr(4200)
    key.CreateRadiusAttr(0.18)
    key_xf = UsdGeom.Xformable(key.GetPrim())
    key_xf.AddTranslateOp().Set(Gf.Vec3d(-0.15, -0.12, 0.30))
    cam = UsdGeom.Camera.Define(stage, "/World/Camera")
    eye, target = Gf.Vec3d(0.018, -0.32, 0.25), Gf.Vec3d(0, 0.015, 0.020)
    matrix = Gf.Matrix4d()
    matrix.SetLookAt(eye, target, Gf.Vec3d(0, 0, 1))
    UsdGeom.Xformable(cam.GetPrim()).AddTransformOp().Set(matrix.GetInverse())
    cam.CreateFocalLengthAttr(40)
    cam.CreateHorizontalApertureAttr(36)
    cam.CreateClippingRangeAttr((0.001, 10))
    if args.gui:
        from omni.kit.viewport.utility import get_active_viewport
        viewport = get_active_viewport()
        if viewport is not None:
            viewport.camera_path = "/World/Camera"

    product = rep.create.render_product("/World/Camera", (args.width, args.height))
    rgb = rep.AnnotatorRegistry.get_annotator("rgb")
    rgb.attach([product])
    for _ in range(24):
        app.update()
    writer = imageio_ffmpeg.write_frames(
        str(args.output), (args.width, args.height), fps=int(data["fps"]),
        codec="libx264", pix_fmt_in="rgb24", pix_fmt_out="yuv420p",
        quality=8, macro_block_size=1)
    writer.send(None)
    snapshots = {0, min(count - 1, 36), count - 1}
    for i in range(count):
        pos = knife_positions[i]
        set_knife_pose(pos)
        v0, v1 = surface["vertex_offsets"][i:i + 2]
        f0, f1 = surface["face_offsets"][i:i + 2]
        verts = surface["vertices"][v0:v1]
        faces = surface["faces"][f0:f1]
        butter.GetPointsAttr().Set(Vt.Vec3fArray.FromNumpy(verts.astype(np.float32)))
        butter.GetFaceVertexCountsAttr().Set(Vt.IntArray.FromNumpy(
            np.full(len(faces), 3, dtype=np.int32)))
        butter.GetFaceVertexIndicesAttr().Set(Vt.IntArray.FromNumpy(faces.ravel()))
        app.update()
        rep.orchestrator.step(rt_subframes=3 if i == 0 else 1)
        pixels = np.asarray(rgb.get_data())
        if pixels.shape[:2] != (args.height, args.width):
            raise RuntimeError(f"Unexpected Isaac image shape {pixels.shape}")
        image = Image.fromarray(pixels[:, :, :3].copy())
        writer.send(np.asarray(image).tobytes())
        if i in snapshots:
            image.save(args.output.with_name(f"frame-{i:03d}.png"))
        if i % 12 == 0:
            print(f"Rendered frame {i}/{count - 1}", flush=True)
    writer.close()
    stage.GetRootLayer().Export(str(args.output.with_suffix(".usda")))
    args.output.with_suffix(".json").write_text(json.dumps({
        "source": str(args.state), "video": str(args.output),
        "frames": count, "fps": int(data["fps"]),
        "physics": "Genesis MPM", "renderer": "Isaac Sim USD/RTX",
    }, indent=2), encoding="utf-8")
    print(f"Saved {args.output}", flush=True)
finally:
    app.close()
