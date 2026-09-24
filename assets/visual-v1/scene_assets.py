"""Detailed, editable USD assets for the Isaac render.

Geometry dimensions match the Genesis rigid bread and knife colliders. The
crumb texture is generated for this project and lives beside the scene.
"""
from pathlib import Path

import numpy as np
from pxr import Gf, Sdf, UsdGeom, UsdShade, Vt


def _material(stage, name, color, roughness=0.65, metallic=0):
    mat = UsdShade.Material.Define(stage, f"/World/Looks/{name}")
    shader = UsdShade.Shader.Define(stage, f"/World/Looks/{name}/Preview")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(roughness)
    shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(metallic)
    mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return mat


def _textured_material(stage, name, image_path, color, roughness):
    mat = _material(stage, name, color, roughness)
    shader = UsdShade.Shader.Get(stage, f"/World/Looks/{name}/Preview")
    uv = UsdShade.Shader.Define(stage, f"/World/Looks/{name}/UV")
    uv.CreateIdAttr("UsdPrimvarReader_float2")
    uv.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
    tex = UsdShade.Shader.Define(stage, f"/World/Looks/{name}/Texture")
    tex.CreateIdAttr("UsdUVTexture")
    tex.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(str(image_path)))
    tex.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(uv.ConnectableAPI(), "result")
    tex.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
    shader.GetInput("diffuseColor").ConnectToSource(tex.ConnectableAPI(), "rgb")
    return mat


def _mesh(stage, path, points, faces, material, uvs=None):
    shape = UsdGeom.Mesh.Define(stage, path)
    shape.CreateSubdivisionSchemeAttr("none")
    shape.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(np.asarray(points, np.float32)))
    shape.CreateFaceVertexCountsAttr(Vt.IntArray.FromNumpy(
        np.asarray([len(f) for f in faces], np.int32)))
    shape.CreateFaceVertexIndicesAttr(Vt.IntArray.FromNumpy(
        np.asarray([i for f in faces for i in f], np.int32)))
    if uvs is not None:
        p = UsdGeom.PrimvarsAPI(shape.GetPrim()).CreatePrimvar(
            "st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.vertex)
        p.Set(Vt.Vec2fArray.FromNumpy(np.asarray(uvs, np.float32)))
    UsdShade.MaterialBindingAPI.Apply(shape.GetPrim()).Bind(material)
    return shape


def _closed_ring_mesh(stage, path, outline, layers, material):
    n = len(outline)
    points = [(x * scale, y * scale, z) for scale, z in layers for x, y in outline]
    faces = []
    for k in range(len(layers) - 1):
        a, b = k * n, (k + 1) * n
        for i in range(n):
            j = (i + 1) % n
            faces.append((a+i, a+j, b+j, b+i))
    faces.append(tuple(reversed(range(n))))
    faces.append(tuple((len(layers)-1)*n+i for i in range(n)))
    return _mesh(stage, path, points, faces, material)


def _smooth_outline(control, samples=5):
    result = []
    count = len(control)
    for i in range(count):
        p0, p1, p2, p3 = [np.asarray(control[j % count], float)
                          for j in (i-1, i, i+1, i+2)]
        for s in range(samples):
            t = s / samples
            result.append(tuple(0.5 * (2*p1 + (-p0+p2)*t +
                         (2*p0-5*p1+4*p2-p3)*t*t +
                         (-p0+3*p1-3*p2+p3)*t*t*t)))
    return result


def _bread(stage, base, x, y, z, angle, crumb, crust, dark_crust):
    # Flat-bottom sandwich slice, softly domed upper edge and irregular crust.
    outline = _smooth_outline([
        (-.064,-.048),(-.071,-.038),(-.071,.018),(-.064,.042),
        (-.044,.052),(-.018,.056),(.015,.057),(.044,.052),
        (.064,.042),(.071,.018),(.071,-.038),(.064,-.048),
        (.035,-.050),(0,-.050),(-.035,-.050)], 4)
    c, s = np.cos(angle), np.sin(angle)
    def xy(q, scale=1):
        a, b = q[0]*scale, q[1]*scale
        return (x + c*a-s*b, y+s*a+c*b)
    outer = [xy(q) for q in outline]
    inner = [xy(q, .925) for q in outline]
    n = len(outline)
    # Crust thickness undulates slightly, as real sliced bread does.
    side = []
    for k, q in enumerate(outer):
        jitter = .00055 * np.sin(k*1.7) + .00025 * np.cos(k*2.8)
        side.append((q[0], q[1], z + .009 + jitter))
    for k, q in enumerate(outer):
        jitter = .00045 * np.sin(k*1.7)
        side.append((q[0], q[1], z + .022 + jitter))
    faces = [(i, (i+1)%n, n+(i+1)%n, n+i) for i in range(n)]
    side_uv = [(i/n,0) for i in range(n)] + [(i/n,1) for i in range(n)]
    _mesh(stage, f"{base}/CrustSide", side, faces, dark_crust, side_uv)
    top = [(a,b,z+.023) for a,b in outer] + [(a,b,z+.024) for a,b in inner]
    ring_faces = [(i,(i+1)%n,n+(i+1)%n,n+i) for i in range(n)]
    _mesh(stage, f"{base}/CrustRim", top, ring_faces, crust)
    center = (x, y, z+.0242)
    points = [center] + [(a,b,z+.0242) for a,b in inner]
    uv = [(.5,.5)] + [(.5+(a-x)/.145, .5+(b-y)/.115) for a,b in inner]
    crumb_faces = [(0,1+i,1+(i+1)%n) for i in range(n)]
    _mesh(stage, f"{base}/Crumb", points, crumb_faces, crumb, uv)


def _rounded_rect(width, height, radius, n=9):
    pts = []
    for cx, cy, start in [(width/2-radius,height/2-radius,0),
                          (-width/2+radius,height/2-radius,90),
                          (-width/2+radius,-height/2+radius,180),
                          (width/2-radius,-height/2+radius,270)]:
        for t in np.linspace(start, start+90, n, endpoint=False):
            # winding is immaterial for preview surface, but continuous outline matters
            rad = np.deg2rad(t)
            pts.append((cx+radius*np.cos(rad),cy+radius*np.sin(rad)))
    return pts


def _prism(stage, path, outline, bottom, top, material):
    return _closed_ring_mesh(stage, path, outline,
                             [(1,bottom),(1,top)], material)


def _ellipsoid(stage, path, center, radii, material):
    sphere = UsdGeom.Sphere.Define(stage, path)
    sphere.CreateRadiusAttr(1)
    mat_api = UsdShade.MaterialBindingAPI.Apply(sphere.GetPrim())
    mat_api.Bind(material)
    xf = Gf.Matrix4d(1)
    xf.SetScale(Gf.Vec3d(*radii))
    xf.SetTranslateOnly(Gf.Vec3d(*center))
    UsdGeom.Xformable(sphere.GetPrim()).AddTransformOp().Set(xf)


def _finger(stage, path, nodes, widths, material):
    points = []
    sides = 12
    for (x,y,z), radius in zip(nodes, widths):
        for a in np.linspace(0,2*np.pi,sides,endpoint=False):
            points.append((x+radius*np.cos(a),y,z+radius*np.sin(a)))
    faces = []
    for k in range(len(nodes)-1):
        for i in range(sides):
            j=(i+1)%sides
            faces.append((k*sides+i,k*sides+j,(k+1)*sides+j,(k+1)*sides+i))
    faces.append(tuple(reversed(range(sides))))
    faces.append(tuple((len(nodes)-1)*sides+i for i in range(sides)))
    shape = _mesh(stage,path,points,faces,material)
    shape.CreateSubdivisionSchemeAttr("catmullClark")


def make_scene_assets(stage, asset_root: Path, initial_knife_pose):
    table = _material(stage, "GrayCountertop", (.43,.44,.43), .86)
    ceramic = _material(stage, "WhiteCeramic", (.88,.89,.86), .23)
    rim = _material(stage, "CeramicEdge", (.73,.75,.73), .27)
    crust = _material(stage, "GoldenCrust", (.66,.38,.15), .83)
    dark_crust = _textured_material(stage, "ToastedCrust",
                                    asset_root / "textures" / "bread-crust.png",
                                    (.70,.45,.23), .89)
    crumb = _textured_material(stage, "BreadCrumb",
                               asset_root / "textures" / "bread-crumb.png",
                               (.95,.86,.69), .92)
    steel = _material(stage, "PolishedSteel", (.76,.79,.81), .16, .9)
    edge = _material(stage, "BladeEdge", (.91,.92,.92), .10, .9)
    handle_mat = _material(stage, "KnifeHandle", (.24,.15,.095), .45)
    rivet = _material(stage, "Rivets", (.57,.59,.60), .21, .8)
    skin = _material(stage, "HandSkin", (.58,.36,.25), .78)

    _prism(stage, "/World/Countertop", _rounded_rect(.68,.5,.02), -.051, -.019, table)
    # The small white rectangular serving plate matches the public video thumbnail.
    plate = _rounded_rect(.255,.188,.012)
    _closed_ring_mesh(stage, "/World/Plate/Body", plate,
                      [(1,-.019),(1,-.015),(.97,-.009),(.93,-.004)], ceramic)
    _closed_ring_mesh(stage, "/World/Plate/Lip", plate,
                      [(1,-.015),(1,-.013),(.965,-.010)], rim)
    _bread(stage, "/World/Bread/Main", 0, 0, .002, 0, crumb, crust, dark_crust)

    # A few remaining slices are placed beyond the working slice, with the
    # same asset family visible in the source video's public thumbnail.
    for i, (bx, by, angle) in enumerate([(.145,.075,-.16),(-.145,.079,.11)]):
        _bread(stage, f"/World/Bread/Background{i}", bx, by, -.003,
               angle, crumb, crust, dark_crust)

    knife = UsdGeom.Xform.Define(stage, "/World/Knife")
    blade_outline = [(-.006,-.034),(-.005,-.026),(-.006,.018),
                     (-.0058,.030),(-.003,.035),(.003,.035),
                     (.0058,.030),(.006,.018),(.006,-.026),(.005,-.034)]
    _prism(stage, "/World/Knife/Blade", blade_outline, -.0015,.0015, steel)
    _prism(stage, "/World/Knife/CuttingEdge",
           [(.004,-.026),(.006,-.026),(.006,.018),(.005,.029),(.004,.030)],
           -.0015,.0015, edge)
    grip = _rounded_rect(.016,.053,.006)
    grip = [(a,b-.057) for a,b in grip]
    _prism(stage, "/World/Knife/Handle", grip, -.0038,.0038, handle_mat)
    for i, py in enumerate((-.047,-.066)):
        riv = UsdGeom.Sphere.Define(stage, f"/World/Knife/Rivet{i}")
        riv.CreateRadiusAttr(.0015)
        mat_api = UsdShade.MaterialBindingAPI.Apply(riv.GetPrim())
        mat_api.Bind(rivet)
        xf = Gf.Matrix4d(1)
        xf.SetTranslateOnly(Gf.Vec3d(0,py,.004))
        UsdGeom.Xformable(riv.GetPrim()).AddTransformOp().Set(xf)
    # A partial gripping hand follows the knife. It is deliberately a visual
    # asset only; Genesis contacts still use the measured blade collider.
    _ellipsoid(stage, "/World/Knife/Hand/Palm", (0,-.120,.002),
               (.031,.038,.013), skin)
    _ellipsoid(stage, "/World/Knife/Hand/Wrist", (0,-.172,.001),
               (.026,.038,.012), skin)
    for i, x0 in enumerate((-.027,-.011,.010,.027)):
        side = -1 if x0 < 0 else 1
        _finger(stage, f"/World/Knife/Hand/Finger{i}",
                [(x0,-.101,.008), (x0*.9,-.081,.011),
                 (side*.012,-.067,.010), (side*.009,-.058,.006)],
                [.0065,.0063,.0059,.0040], skin)
    _finger(stage, "/World/Knife/Hand/Thumb",
            [(-.030,-.120,.006),(-.025,-.103,.013),
             (-.012,-.079,.015),(-.005,-.070,.009)],
            [.008,.007,.006,.004], skin)
    translate = knife.AddTranslateOp()
    def set_pose(pos):
        # Match the lower face of the 3 mm display blade to the lower face
        # of Genesis' 12 mm collision blade (both use the same XY pose).
        x, y, z = map(float, pos)
        translate.Set(Gf.Vec3d(x, y, z - 0.0045))
    set_pose(initial_knife_pose)
    return set_pose
