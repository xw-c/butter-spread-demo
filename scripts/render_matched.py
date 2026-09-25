"""Isaac Sim photographic scene alignment driven by Genesis MPM state.

The supplied frame defines a camera-matched photo set. Genesis particles and
the simulated knife pose control the time-dependent butter reveal; the photo
layers provide the scene appearance. See README for this visual approximation.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--state", type=Path, default=ROOT / "outputs" / "mpm-state.npz")
parser.add_argument("--output", type=Path, default=ROOT / "outputs" / "butter-spread-matched.mp4")
parser.add_argument("--width", type=int, default=1280)
parser.add_argument("--height", type=int, default=720)
parser.add_argument("--frames", type=int, default=0)
parser.add_argument("--gui", action="store_true")
args = parser.parse_args()
state = np.load(args.state)
knife_poses = state["knife_positions"]
particles = state["particles"]
count = len(knife_poses) if args.frames == 0 else min(args.frames, len(knife_poses))
args.output.parent.mkdir(parents=True, exist_ok=True)

assets = ROOT / "assets" / "matched"
W, H = Image.open(assets / "clean-scene.png").size
BW, BH = Image.open(assets / "buttered-scene.png").size
if abs(BW-W)>1 or abs(BH-H)>1:
    raise ValueError("Scene photo layers must have nearly identical dimensions")
SCALE = 0.00025

# Corners of the working slice measured in the user's frame, in photo pixels.
source = np.array([[-.07,.05],[.07,.05],[.07,-.05],[-.07,-.05]], dtype=float)
target = np.array([[913,385],[1286,570],[1128,917],[716,733]], dtype=float)
def homography(src, dst):
    rows=[]
    for (x,y),(u,v) in zip(src,dst):
        rows.append([x,y,1,0,0,0,-u*x,-u*y])
        rows.append([0,0,0,x,y,1,-v*x,-v*y])
    terms=np.linalg.solve(np.asarray(rows),dst.ravel())
    return np.array([[terms[0],terms[1],terms[2]],
                     [terms[3],terms[4],terms[5]],
                     [terms[6],terms[7],1.]])
HOMOGRAPHY=homography(source,target)
def photo_xy(x,y):
    q=HOMOGRAPHY @ np.array([x,y,1.])
    return q[0]/q[2],q[1]/q[2]
def world_xy(px,py):
    return (px-W/2)*SCALE,(H/2-py)*SCALE

from isaacsim import SimulationApp
app = SimulationApp({"headless": not args.gui, "width": args.width,
                     "height": args.height, "anti_aliasing": 3})
try:
    import omni.usd
    import omni.replicator.core as rep
    import imageio_ffmpeg
    from pxr import Gf, Sdf, UsdGeom, UsdShade, Vt

    ctx=omni.usd.get_context()
    ctx.new_stage()
    stage=ctx.get_stage()
    UsdGeom.SetStageUpAxis(stage,UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage,1)
    root=UsdGeom.Xform.Define(stage,"/World")
    stage.SetDefaultPrim(root.GetPrim())

    def photo_material(name,path,alpha=False):
        mat=UsdShade.Material.Define(stage,f"/World/Looks/{name}")
        shader=UsdShade.Shader.Define(stage,f"/World/Looks/{name}/Preview")
        shader.CreateIdAttr("UsdPreviewSurface")
        shader.CreateInput("diffuseColor",Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0,0,0))
        tex=UsdShade.Shader.Define(stage,f"/World/Looks/{name}/Texture")
        tex.CreateIdAttr("UsdUVTexture")
        tex.CreateInput("file",Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(str(path)))
        tex.CreateInput("sourceColorSpace",Sdf.ValueTypeNames.Token).Set("sRGB")
        uv=UsdShade.Shader.Define(stage,f"/World/Looks/{name}/UV")
        uv.CreateIdAttr("UsdPrimvarReader_float2")
        uv.CreateInput("varname",Sdf.ValueTypeNames.Token).Set("st")
        tex.CreateInput("st",Sdf.ValueTypeNames.Float2).ConnectToSource(uv.ConnectableAPI(),"result")
        tex.CreateOutput("rgb",Sdf.ValueTypeNames.Float3)
        tex.CreateOutput("a",Sdf.ValueTypeNames.Float)
        shader.CreateInput("emissiveColor",Sdf.ValueTypeNames.Color3f).ConnectToSource(tex.ConnectableAPI(),"rgb")
        if alpha:
            shader.CreateInput("opacity",Sdf.ValueTypeNames.Float).ConnectToSource(tex.ConnectableAPI(),"a")
            shader.CreateInput("opacityThreshold",Sdf.ValueTypeNames.Float).Set(.01)
        mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(),"surface")
        return mat

    def mesh(path,points,faces,uvs,mat):
        obj=UsdGeom.Mesh.Define(stage,path)
        obj.CreateSubdivisionSchemeAttr("none")
        obj.CreateDoubleSidedAttr(True)
        obj.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(np.asarray(points,np.float32)))
        obj.CreateFaceVertexCountsAttr(Vt.IntArray.FromNumpy(
            np.asarray([len(f) for f in faces],np.int32)))
        obj.CreateFaceVertexIndicesAttr(Vt.IntArray.FromNumpy(
            np.asarray([j for f in faces for j in f],np.int32)))
        primvar=UsdGeom.PrimvarsAPI(obj.GetPrim()).CreatePrimvar(
            "st",Sdf.ValueTypeNames.TexCoord2fArray,UsdGeom.Tokens.vertex)
        primvar.Set(Vt.Vec2fArray.FromNumpy(np.asarray(uvs,np.float32)))
        UsdShade.MaterialBindingAPI.Apply(obj.GetPrim()).Bind(mat)
        return obj

    halfx,halfy=W*SCALE/2,H*SCALE/2
    quad=[(-halfx,-halfy,0),(halfx,-halfy,0),
          (halfx,halfy,0),(-halfx,halfy,0)]
    quad_uv=[(0,0),(1,0),(1,1),(0,1)]
    mesh("/World/PhotoScene",quad,[(0,1,2,3)],quad_uv,
         photo_material("CleanScene",assets/"clean-scene.png"))

    # The buttered photo is sampled only over the bread. The reveal endpoint
    # follows the Genesis knife pose; MPM spreading scales its width.
    buttered=photo_material("ButteredBread",assets/"buttered-scene.png")
    nx,ny=28,12
    overlay_faces=[]
    for i in range(nx-1):
        for j in range(ny-1):
            k=i*ny+j
            overlay_faces.append((k,k+ny,k+ny+1,k+1))
    overlay=mesh("/World/ButterPhotoLayer",[(0,0,.002)]*(nx*ny),
                 overlay_faces,[(0,0)]*(nx*ny),buttered)
    overlay_uv=UsdGeom.PrimvarsAPI(overlay.GetPrim()).GetPrimvar("st")

    knife_mat=photo_material("SilverKnife",assets/"butter-knife.png",alpha=True)
    knife_mesh=mesh("/World/KnifeSprite",quad,[(0,1,2,3)],quad_uv,knife_mat)

    cam=UsdGeom.Camera.Define(stage,"/World/Camera")
    cm=Gf.Matrix4d()
    cm.SetLookAt(Gf.Vec3d(0,0,1),Gf.Vec3d(0,0,0),Gf.Vec3d(0,1,0))
    UsdGeom.Xformable(cam.GetPrim()).AddTransformOp().Set(cm.GetInverse())
    cam.CreateFocalLengthAttr(float(36/(W*SCALE)))
    cam.CreateHorizontalApertureAttr(36)
    cam.CreateClippingRangeAttr((.001,10))
    if args.gui:
        from omni.kit.viewport.utility import get_active_viewport
        viewport=get_active_viewport()
        if viewport is not None:
            viewport.camera_path="/World/Camera"

    initial_span=np.ptp(particles[0,:,:2],axis=0)
    final_span=np.ptp(particles[-1,:,:2],axis=0)
    def update(i):
        position=knife_poses[i]
        span=np.ptp(particles[i,:,:2],axis=0)
        # The simulated knife reaches the right edge at 2.55s. The photo
        # material covers the bread by the end, representing its thin coating.
        knife_progress=np.clip((float(position[0])+.068)/.136,0,1)
        plastic_progress=np.clip((span[0]-initial_span[0])/
                                 max(final_span[0]-initial_span[0],1e-6),0,1)
        progress=.58*knife_progress+.42*plastic_progress
        x_end=-.07+.14*progress
        width_factor=.75+.25*np.clip((span[1]-initial_span[1])/
                                   max(final_span[1]-initial_span[1],1e-6),0,1)
        points=[]
        st=[]
        for a in range(nx):
            u=a/(nx-1)
            for b in range(ny):
                v=b/(ny-1)
                # Uneven front edge avoids a rectangular wipe across bread.
                edge_wave=(.0035*np.sin(11*v+0.7)+
                           .0015*np.sin(29*v+1.2))*np.sin(np.pi*progress)
                local_x=-.07+(x_end+.07)*u+u**8*edge_wave
                local_y=(-.05+.10*v)*width_factor
                px,py=photo_xy(local_x,local_y)
                wx,wy=world_xy(px,py)
                points.append((wx,wy,.002))
                st.append((px/BW,1-py/BH))
        overlay.GetPointsAttr().Set(Vt.Vec3fArray.FromNumpy(np.asarray(points,np.float32)))
        overlay_uv.Set(Vt.Vec2fArray.FromNumpy(np.asarray(st,np.float32)))

        # The photographic knife follows the same normalized action phase.
        # Tip position is measured in the reference photo and moves down-right.
        tip_x=820+280*progress
        tip_y=625+240*progress
        shift_x=(tip_x-94)*SCALE
        shift_y=-(tip_y-550)*SCALE
        knife_points=[(x+shift_x,y+shift_y,.004) for x,y,_ in quad]
        knife_mesh.GetPointsAttr().Set(Vt.Vec3fArray.FromNumpy(
            np.asarray(knife_points,np.float32)))

    product=rep.create.render_product("/World/Camera",(args.width,args.height))
    rgb=rep.AnnotatorRegistry.get_annotator("rgb")
    rgb.attach([product])
    for _ in range(24): app.update()
    writer=imageio_ffmpeg.write_frames(
        str(args.output),(args.width,args.height),fps=int(state["fps"]),
        codec="libx264",pix_fmt_in="rgb24",pix_fmt_out="yuv420p",
        quality=8,macro_block_size=1)
    writer.send(None)
    snapshots={0,min(count-1,36),count-1}
    for i in range(count):
        update(i)
        app.update()
        rep.orchestrator.step(rt_subframes=3 if i==0 else 1)
        pixels=np.asarray(rgb.get_data())
        image=Image.fromarray(pixels[:,:,:3].copy())
        writer.send(np.asarray(image).tobytes())
        if i in snapshots:
            image.save(args.output.with_name(f"matched-frame-{i:03d}.png"))
        if i%12==0:
            print(f"Matched frame {i}/{count-1}",flush=True)
    writer.close()
    stage.GetRootLayer().Export(str(args.output.with_suffix(".usda")))
    args.output.with_suffix(".json").write_text(json.dumps({
        "source":str(args.state),"video":str(args.output),"frames":count,
        "fps":int(state["fps"]),"background":"user-frame matched photography",
        "physics":"Genesis MPM", "renderer":"Isaac Sim RTX",
        "note":"Butter photo reveal is a visual approximation driven by the simulated knife pose and MPM spread."},indent=2),encoding="utf-8")
    print(f"Saved {args.output}",flush=True)
finally:
    app.close()
