"""Render recorded Genesis MPM state in the Isaac Sim scene."""
import argparse
import hashlib
import json
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
parser.add_argument("--start-frame", type=int, default=0)
parser.add_argument("--samples", type=int, default=64)
parser.add_argument("--renderer", choices=('PathTracing', 'RaytracedLighting'), default='PathTracing')
parser.add_argument('--camera', choices=('scene','bread'), default='scene')
parser.add_argument('--stage-format', choices=('usda','usdc'), default='usdc')
parser.add_argument('--skip-stage', action='store_true')
args = parser.parse_args()
data = np.load(args.state)
surface = np.load(args.surface)
surface_vertices, surface_faces = surface['vertices'], surface['faces']
surface_normals = surface['normals'] if 'normals' in surface.files else None
vertex_offsets, face_offsets = surface['vertex_offsets'], surface['face_offsets']
source_hashes = {"state": hashlib.sha256(args.state.read_bytes()).hexdigest(),
                 "surface": hashlib.sha256(args.surface.read_bytes()).hexdigest()}
particles = data["particles"]
bread_particles = data['bread_particles']
knife_positions = data["knife_positions"]
if len(surface["vertex_offsets"]) != len(particles) + 1:
    raise ValueError("Surface/state frame counts differ; rebuild the surface from this state")
count = len(particles) if args.frames == 0 else min(args.frames, len(particles))
if not 0 <= args.start_frame < len(particles):
    parser.error('--start-frame is outside the recorded state')
count = min(count, len(particles) - args.start_frame)
args.output.parent.mkdir(parents=True, exist_ok=True)

from isaacsim import SimulationApp
app = SimulationApp({"headless": not args.gui, "width": args.width,
                     "height": args.height, "anti_aliasing": 3,
                     "renderer": args.renderer, "samples_per_pixel_per_frame": min(args.samples,2)})

try:
    import omni.usd
    import omni.replicator.core as rep
    import imageio_ffmpeg
    from PIL import Image
    from pxr import Gf, Sdf, UsdGeom, UsdShade, UsdLux, Vt
    from scene_reference import make_scene_assets
    import carb
    settings=carb.settings.get_settings()
    # Small GPU batches avoid long path-tracing kernels under Windows WDDM.
    settings.set('/rtx/pathtracing/spp', min(args.samples,2))
    settings.set('/rtx/pathtracing/totalSpp', args.samples)
    settings.set('/rtx/pathtracing/maxBounces', 6)
    settings.set('/omni/replicator/captureOnPlay', False)

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

    mats = {"butter": material("Butter", (0.83, 0.73, 0.34), 0.40)}

    def bind(prim, name):
        UsdShade.MaterialBindingAPI.Apply(prim).Bind(mats[name])

    set_knife_pose = make_scene_assets(
        stage, ROOT / "assets", knife_positions[0],
        knife_thickness=float(data["knife_size"][2]))

    # Override only the task slice. Editing the shared library would deform
    # all four background slices as well, and instance proxies are read-only.
    from bread_deformation import BreadDeformation
    bread_root = stage.GetPrimAtPath('/World/Task/Bread')
    bread_root.SetInstanceable(False)
    bread_mesh = UsdGeom.Mesh.Get(stage, '/World/Task/Bread/Mesh')
    bread_rest_local = np.asarray(bread_mesh.GetPointsAttr().Get(), dtype=np.float32).copy()
    bread_rest_normals = np.asarray(bread_mesh.GetNormalsAttr().Get(), dtype=np.float32).copy()
    transform_cache = UsdGeom.XformCache()
    relative_transform = np.asarray(
        transform_cache.GetLocalToWorldTransform(bread_mesh.GetPrim())
        * transform_cache.GetLocalToWorldTransform(stage.GetPrimAtPath('/World/Task')).GetInverse())
    if not np.allclose(relative_transform[:3, :3], np.eye(3), atol=1e-8):
        raise ValueError('Bread reference mesh must share the simulation axes inside /World/Task')
    bread_offset = relative_transform[3, :3].astype(np.float32)
    bread_binding = BreadDeformation(bread_particles[0], bread_rest_local + bread_offset, bread_rest_normals)
    bread_deformation_frames = []
    bread_probe_ids = np.linspace(0, len(bread_rest_local) - 1, 4096).astype(int)
    bread_readback_error = 0.0

    butter = UsdGeom.Mesh.Define(stage, "/World/Task/Butter/Surface")
    butter.CreateSubdivisionSchemeAttr("none")
    bind(butter.GetPrim(), "butter")
    dome = UsdLux.DomeLight.Define(stage, "/World/Lights/Dome")
    dome.CreateIntensityAttr(260)
    key = UsdLux.RectLight.Define(stage, "/World/Lights/Key")
    key.CreateIntensityAttr(1850)
    key.CreateWidthAttr(0.48)
    key.CreateHeightAttr(0.40)
    key_xf = UsdGeom.Xformable(key.GetPrim())
    key_xf.AddTranslateOp().Set(Gf.Vec3d(-0.27, 0.02, 0.55))
    reflection = UsdLux.RectLight.Define(stage, '/World/Lights/WindowReflection')
    reflection.CreateIntensityAttr(1400)
    reflection.CreateWidthAttr(.32)
    reflection.CreateHeightAttr(.24)
    reflection_xf=UsdGeom.Xformable(reflection.GetPrim())
    reflection_xf.AddTranslateOp().Set(Gf.Vec3d(.12,.33,.48))
    reflection_xf.AddRotateXOp().Set(-35.)
    # A studio flag creates a dark band in the steel, like surrounding kitchen
    # reflections. It sits outside the camera frustum, not in front of the bread.
    flag_material=material('ReflectionFlag',(.002,.002,.002),1.)
    from scene_assets import _mesh
    flag=_mesh(stage,'/World/Lights/ReflectionFlag',
        [(-.025,.13,.30),(.065,.13,.30),(.065,.18,.30),(-.025,.18,.30)],
        [(0,1,2,3)],flag_material)
    flag.CreateDoubleSidedAttr(True)
    cam = UsdGeom.Camera.Define(stage, "/World/Camera")
    eye, target = Gf.Vec3d(-0.045, -0.305, 0.71), Gf.Vec3d(-0.045, 0.075, 0.01)
    if args.camera == 'bread':
        eye,target=Gf.Vec3d(.01,-.22,.30),Gf.Vec3d(0,0,.025)
    matrix = Gf.Matrix4d()
    matrix.SetLookAt(eye, target, Gf.Vec3d(0, 0, 1))
    UsdGeom.Xformable(cam.GetPrim()).AddTransformOp().Set(matrix.GetInverse())
    cam.CreateFocalLengthAttr(59)
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
    # New-stage initialization restores SimulationApp's totalSpp to its batch
    # SPP. Apply the requested total only after that initialization completes.
    settings.set('/rtx/pathtracing/spp', min(args.samples,2))
    settings.set('/rtx/pathtracing/totalSpp', args.samples)
    effective_render_settings = {key: settings.get(key) for key in (
        '/rtx/rendermode', '/rtx/pathtracing/spp', '/rtx/pathtracing/totalSpp',
        '/omni/replicator/pathTracedMotionBlurSubSamples')}
    print('Effective render settings: ' + json.dumps(effective_render_settings), flush=True)
    writer = imageio_ffmpeg.write_frames(
        str(args.output), (args.width, args.height), fps=int(data["fps"]),
        codec="libx264", pix_fmt_in="rgb24", pix_fmt_out="yuv420p",
        quality=8, macro_block_size=1)
    writer.send(None)
    snapshots = {args.start_frame, args.start_frame + (count - 1) // 2, args.start_frame + count - 1}
    for i in range(args.start_frame, args.start_frame + count):
        pos = knife_positions[i]
        set_knife_pose(pos)
        bread_points, bread_normals, minimum_jacobian = bread_binding.deform(bread_particles[i])
        bread_local_points = bread_points - bread_offset
        bread_mesh.GetPointsAttr().Set(Vt.Vec3fArray.FromNumpy(bread_local_points))
        bread_mesh.GetNormalsAttr().Set(Vt.Vec3fArray.FromNumpy(bread_normals))
        bread_mesh.CreateExtentAttr().Set(Vt.Vec3fArray.FromNumpy(np.stack(
            (bread_local_points.min(axis=0), bread_local_points.max(axis=0)))))
        actual_points = np.asarray(bread_mesh.GetPointsAttr().Get())
        bread_readback_error = max(bread_readback_error, float(np.max(np.abs(
            actual_points[bread_probe_ids] - bread_local_points[bread_probe_ids]))))
        bread_displacement = bread_points - bread_binding.rest
        bread_deformation_frames.append(dict(
            source_frame=i, time_s=float(data['time_s'][i]),
            max_vertex_displacement_m=float(np.linalg.norm(bread_displacement, axis=1).max()),
            max_vertex_downward_m=float(-bread_displacement[:, 2].min()),
            minimum_deformation_jacobian=minimum_jacobian))
        v0, v1 = vertex_offsets[i:i + 2]
        f0, f1 = face_offsets[i:i + 2]
        verts = surface_vertices[v0:v1]
        faces = surface_faces[f0:f1]
        butter.GetPointsAttr().Set(Vt.Vec3fArray.FromNumpy(verts.astype(np.float32)))
        butter.GetFaceVertexCountsAttr().Set(Vt.IntArray.FromNumpy(
            np.full(len(faces), 3, dtype=np.int32)))
        butter.GetFaceVertexIndicesAttr().Set(Vt.IntArray.FromNumpy(faces.ravel()))
        if surface_normals is not None:
            normals = surface_normals[v0:v1]
        else:
            # Retained only for comparison with previously saved surfaces.
            normals=np.zeros_like(verts)
            face_normals=np.cross(verts[faces[:,1]]-verts[faces[:,0]],verts[faces[:,2]]-verts[faces[:,0]])
            for corner in range(3): np.add.at(normals,faces[:,corner],face_normals)
            normals/=np.maximum(np.linalg.norm(normals,axis=1,keepdims=True),1e-10)
        butter.CreateNormalsAttr(Vt.Vec3fArray.FromNumpy(normals.astype(np.float32)))
        butter.SetNormalsInterpolation('vertex')
        # Replicator flushes the USD updates and waits for the requested SPP.
        # A separate app.update() would render the same state again.
        for attempt in range(4):
            # On this Isaac/RTX build the RGB annotator intermittently returns
            # an uninitialized all-black buffer. Render the same USD state
            # again instead of encoding that buffer as a video frame.
            rep.orchestrator.step(rt_subframes=2)
            if args.renderer == 'PathTracing' and settings.get('/rtx/pathtracing/totalSpp') != args.samples:
                raise RuntimeError('Isaac changed the requested path-tracing sample count during capture')
            pixels = np.asarray(rgb.get_data())
            if pixels.shape[:2] != (args.height, args.width):
                raise RuntimeError(f"Unexpected Isaac image shape {pixels.shape}")
            if np.any(pixels[:, :, :3]):
                break
            print(f"RTX returned an empty buffer for frame {i}; retry {attempt+1}/4", flush=True)
        else:
            raise RuntimeError(f"Isaac repeatedly returned a black image for source frame {i}")
        image = Image.fromarray(pixels[:, :, :3].copy())
        writer.send(np.asarray(image).tobytes())
        if i in snapshots:
            image.save(args.output.with_name(f"{args.output.stem}-frame-{i:03d}.png"))
        if i % 6 == 0:
            print(f"Rendered source frame {i} ({i-args.start_frame+1}/{count})", flush=True)
    writer.close()
    stage_path=args.output.with_suffix('.'+args.stage_format)
    if not args.skip_stage:
        stage.GetRootLayer().Export(str(stage_path))
    bread_prim=stage.GetPrimAtPath('/World/BreadLibrary/PorousSlice/Mesh')
    scene_audit={
        'no_synthetic_contact_film':not any('ContactFilm' in str(p.GetPath()) for p in stage.Traverse()),
        'no_hand_model':not bool(stage.GetPrimAtPath('/World/RestingHand')),
        'cdmpm_bread_vertices':len(bread_prim.GetAttribute('points').Get()) if bread_prim else 0,
        'flat_blade_present':bool(stage.GetPrimAtPath('/World/Task/Knife/FlatBlade')),
        'bread_library_unchanged': bool(np.array_equal(
            np.asarray(bread_prim.GetAttribute('points').Get()), bread_rest_local)),
        'task_bread_is_independently_deformable': not bread_root.IsInstanceable(),
        'background_bread_remains_instanced': all(
            stage.GetPrimAtPath(f'/World/Stack/Slice{i}').IsInstance() for i in range(4)),
    }
    args.output.with_suffix(".json").write_text(json.dumps({
        "source": str(args.state), "video": str(args.output),
        "surface_source": str(args.surface), "source_sha256": source_hashes,
        "normal_method": str(surface['normal_method']) if 'normal_method' in surface.files else 'triangle_average',
        "frames": count, "fps": int(data["fps"]),
        "start_frame": args.start_frame,
        "physics": "Genesis MPM", "renderer": 'Isaac Sim RTX ' + args.renderer,
        "path_tracing_samples": args.samples if args.renderer == 'PathTracing' else None,
        "effective_render_settings": effective_render_settings,
        "scene_reference": "assets/reference/target-scene.png",
        "bread_reference": 'https://joshuahwolper.com/cdmpm',
        "video_reference": 'assets/reference/video/source.json',
        "scene_audit": scene_audit,
        "bread_deformation": {
            "method": "reference_trilinear_mpm_displacement", "displacement_gain": 1.0,
            "source_particle_count": int(bread_particles.shape[1]),
            "mesh_vertex_count": len(bread_rest_local), "normal_transport": "inverse_transpose",
            "usd_readback_max_error_m": bread_readback_error,
            "frames": bread_deformation_frames,
        },
        "usd_stage": str(stage_path.resolve()) if not args.skip_stage else None,
    }, indent=2), encoding="utf-8")
    print(f"Saved {args.output}", flush=True)
finally:
    app.close()
