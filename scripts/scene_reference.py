"""Editable 3D reconstruction of the user's reference photograph.

All props are geometry with materials. No reference-photo background or
painted butter trail is used. Physics states are rotated as one task group.
"""
from pathlib import Path
import numpy as np
from PIL import Image
from scipy.spatial import Delaunay
from pxr import Gf, Sdf, UsdGeom, UsdShade, Vt
from scene_assets import _material, _textured_material, _mesh, _rounded_rect, _prism, _ellipsoid, _smooth_outline

from bread_knife_assets import add_bread, add_knife

TASK_ANGLE = -24.0

def smooth_mesh(stage,path,points,faces,material,uvs=None):
    mesh=_mesh(stage,path,points,faces,material,uvs)
    p=np.asarray(points,dtype=np.float32)
    normals=np.zeros_like(p)
    for face in faces:
        a,b,c=face[:3]
        normal=np.cross(p[b]-p[a],p[c]-p[a])
        for i in face: normals[i]+=normal
    normals/=np.maximum(np.linalg.norm(normals,axis=1,keepdims=True),1e-10)
    mesh.CreateNormalsAttr(Vt.Vec3fArray.FromNumpy(normals))
    mesh.SetNormalsInterpolation('vertex')
    mesh.CreateDoubleSidedAttr(True)
    return mesh

def normal_texture(stage, material, path, scale=1):
    shader=UsdShade.Shader.Get(stage,material.GetPath().AppendChild('Preview'))
    base=str(material.GetPath())
    uv=UsdShade.Shader.Define(stage,base+'/NormalUV')
    uv.CreateIdAttr('UsdPrimvarReader_float2')
    uv.CreateInput('varname',Sdf.ValueTypeNames.Token).Set('st')
    tex=UsdShade.Shader.Define(stage,base+'/NormalMap')
    tex.CreateIdAttr('UsdUVTexture')
    tex.CreateInput('wrapS',Sdf.ValueTypeNames.Token).Set('repeat')
    tex.CreateInput('wrapT',Sdf.ValueTypeNames.Token).Set('repeat')
    tex.CreateInput('file',Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(str(path)))
    tex.CreateInput('sourceColorSpace',Sdf.ValueTypeNames.Token).Set('raw')
    tex.CreateInput('scale',Sdf.ValueTypeNames.Float4).Set(Gf.Vec4f(2,2,2,1))
    tex.CreateInput('bias',Sdf.ValueTypeNames.Float4).Set(Gf.Vec4f(-1,-1,-1,0))
    tex.CreateInput('st',Sdf.ValueTypeNames.Float2).ConnectToSource(uv.ConnectableAPI(),'result')
    tex.CreateOutput('rgb',Sdf.ValueTypeNames.Float3)
    shader.CreateInput('normal',Sdf.ValueTypeNames.Normal3f).ConnectToSource(tex.ConnectableAPI(),'rgb')

def lathe(stage,path,profile,center,mat,uv_radius=.12,segments=160):
    pts=[];uv=[];faces=[]
    for r,z in profile:
        for t in np.linspace(0,2*np.pi,segments,endpoint=False):
            x,y=r*np.cos(t),r*np.sin(t)
            pts.append((x+center[0],y+center[1],z+center[2]))
            uv.append((.5+x/(2*uv_radius),.5+y/(2*uv_radius)))
    for k in range(len(profile)-1):
        for i in range(segments):
            j=(i+1)%segments
            faces.append((k*segments+i,(k+1)*segments+i,(k+1)*segments+j,k*segments+j))
    return smooth_mesh(stage,path,pts,faces,mat,uv)

def plate(stage,path,center,pattern,rim):
    profile=[(.00001,.010),(.030,.010),(.062,.010),(.077,.0105),(.084,.0115),
             (.094,.014),(.104,.018),(.115,.023),(.121,.024),(.123,.0235),
             (.124,.022),(.123,.020),(.115,.016),(.095,.009),(.073,.003),(.04,.002),(.00001,.002)]
    lathe(stage,path+'/Ceramic',profile,center,pattern,.124)
    lathe(stage,path+'/InkRim',[(.1227,.022),(.124,.0225),(.124,.0237),(.1227,.024)],center,rim,.124)
    lathe(stage,path+'/Foot',[(.047,.003),(.047,-.006),(.051,-.006),(.051,.003)],center,rim)

def inside(points,polygon):
    x,y=points.T; hit=np.zeros(len(points),bool)
    for a,b in zip(polygon,np.roll(polygon,-1,axis=0)):
        hit^=((a[1]>y)!=(b[1]>y)) & (x < (b[0]-a[0])*(y-a[1])/(b[1]-a[1]+1e-15)+a[0])
    return hit

def bread(stage,path,center,angle,crumb,crust,edge,texture,seed=0):
    return add_bread(stage,path,center,angle,Path(texture).parent.parent,seed)


def tub(stage,base,center,angle,white,blue,label,butter):
    root=UsdGeom.Xform.Define(stage,base)
    root.AddTranslateOp().Set(Gf.Vec3d(*center));root.AddRotateZOp().Set(angle)
    outline=np.array(_rounded_rect(.12,.145,.019,16)); n=len(outline)
    pts=[]; faces=[]
    layers=[(.86,-.003),(.87,.004),(1.,.046),(1.005,.05),(.975,.052),(.94,.049),(.90,.036)]
    for scale,z in layers:pts.extend([(x*scale,y*scale,z) for x,y in outline])
    for k in range(len(layers)-1):
        for i in range(n):faces.append((k*n+i,k*n+(i+1)%n,(k+1)*n+(i+1)%n,(k+1)*n+i))
    smooth_mesh(stage,base+'/PlasticRim',pts,faces,white)
    # Blue outer sleeve, with text oriented towards the camera on the front.
    sleeve=[];uv=[]
    for k,(scale,z) in enumerate([(.877,.003),(.986,.043)]):
        for i,(x,y) in enumerate(outline):
            sleeve.append((x*scale,y*scale,z));uv.append((i/n,k))
    smooth_mesh(stage,base+'/BlueSleeve',sleeve,[(i,(i+1)%n,n+(i+1)%n,n+i) for i in range(n)],blue,uv)
    _mesh(stage,base+'/FrontLabel',[(-.047,-.067,.007),(.047,-.067,.007),(.053,-.074,.042),(-.053,-.074,.042)],
          [(0,1,2,3)],label,[(0,0),(1,0),(1,1),(0,1)])
    # Scooped, folded margarine surface is a static prop inside the tub.
    gx,gy=np.meshgrid(np.linspace(-.053,.053,95),np.linspace(-.064,.064,113))
    q=np.c_[gx.ravel(),gy.ravel()];q=q[inside(q,outline*.90)]
    x,y=q.T
    z=np.full_like(x,.040)
    for cx,cy,depth in [(-.017,.028,.009),(.018,-.025,.008),(.019,.047,.005)]:
        dx=x-cx-.20*(y-cy)
        g=np.exp(-(dx/.026)**2-((y-cy)/.035)**2)
        z-=depth*g
        z+=depth*.65*np.exp(-((dx+.024)/.0045)**2-((y-cy)/.033)**2)
    z+=.00045*np.sin(780*x+90*y)*np.sin(y*73)
    tri=Delaunay(q).simplices;tri=tri[inside(q[tri].mean(axis=1),outline*.90)]
    smooth_mesh(stage,base+'/ScoopedMargarine',np.c_[q,z],tri,butter)
    for i,cy in enumerate([-.045,-.019,.010,.033,.050]):
        points=[];faces=[]
        for a,u in enumerate(np.linspace(0,1,20)):
            for b,v in enumerate(np.linspace(-1,1,12)):
                px=-.047+.024*u+.003*np.sin(v*3+i)
                py=cy+.011*v+.007*u
                pz=.039+(.009+.002*np.sin(i))*np.sin(u*np.pi*.9)*(1-.25*v*v)
                points.append((px,py,pz))
        for a in range(19):
            for b in range(11):
                k=a*12+b;faces.append((k,k+12,k+13,k+1))
        smooth_mesh(stage,f'{base}/ButterCurl{i}',points,faces,butter)

def make_scene_assets(stage,asset_root:Path,initial_knife_pose,knife_thickness=.012):
    tex=asset_root/'textures'
    table=_textured_material(stage,'Stone',tex/'stone-gray.png',(.2,.2,.2),.72)
    normal_texture(stage,table,tex/'stone-normal.png')
    pattern=_textured_material(stage,'Seigaiha',tex/'seigaiha.png',(.7,.7,.7),.22)
    rim=_material(stage,'NavyGlaze',(.009,.018,.03),.20)
    white=_material(stage,'IvoryPlastic',(.78,.79,.70),.26)
    blue=_material(stage,'BlueTub',(.025,.35,.47),.34)
    label=_textured_material(stage,'BlueBandLabel',tex/'tub-label.png',(.7,.7,.7),.38)
    crumb=_textured_material(stage,'BreadCrumbV2',tex/'bread-crumb-v2.png',(.8,.7,.5),.91)
    crust=_textured_material(stage,'BreadCrustV2',tex/'bread-crust.png',(.6,.3,.1),.85)
    crust_tex=UsdShade.Shader.Get(stage,'/World/Looks/BreadCrustV2/Texture')
    crust_tex.CreateInput('scale',Sdf.ValueTypeNames.Float4).Set(Gf.Vec4f(.65,.65,.65,1))
    crust_tex.CreateInput('bias',Sdf.ValueTypeNames.Float4).Set(Gf.Vec4f(.18,.15,.10,0))
    edge=_material(stage,'BreadPaleEdge',(.66,.48,.25),.85)
    steel=_material(stage,'BrushedSteel',(.65,.67,.69),.16,.98)
    sugar=_material(stage,'SugarCrystals',(.78,.78,.75),.55)
    butter=_material(stage,'TubMargarine',(.87,.74,.24),.35)
    skin=_material(stage,'Skin',(.40,.23,.18),.63)
    nail=_material(stage,'NaturalNail',(.44,.27,.23),.43)
    crease=_material(stage,'SkinCrease',(.30,.155,.12),.72)
    _mesh(stage,'/World/Countertop',[(-.6,-.6,-.006),(.6,-.6,-.006),(.6,.6,-.006),(-.6,.6,-.006)],
          [(0,1,2,3)],table,[(0,0),(1,0),(1,1),(0,1)])
    plate(stage,'/World/MainPlate',(0,-.006,0),pattern,rim)
    plate(stage,'/World/StackPlate',(-.197,.139,0),pattern,rim)
    task=UsdGeom.Xform.Define(stage,'/World/Task');task.AddRotateZOp().Set(TASK_ANGLE)
    bread(stage,'/World/Task/Bread',(0,0,.026),0,crumb,crust,edge,tex/'bread-crumb-v2.png')
    for i in range(4):
        bread(stage,f'/World/Stack/Slice{i}',(-.243+i*.023,.115+i*.014,.025+i*.012),
              -.35+i*.10,crumb,crust,edge,tex/'bread-crumb-v2.png',i+1)
    lathe(stage,'/World/SugarBowl/Steel',[(.0001,0),(.028,0),(.041,.006),(.049,.022),
        (.051,.041),(.052,.049),(.051,.050),(.049,.049),(.047,.035),(.039,.012),(.026,.004),(.0001,.004)],
        (-.048,.209,-.004),steel,.052)
    lathe(stage,'/World/SugarBowl/Sugar',[(.00001,.026),(.018,.025),(.035,.022),(.043,.018)],
        (-.048,.209,-.004),sugar,.045)
    # Thousands of small facets give sugar actual highlights and self-shadow.
    rng=np.random.default_rng(7);p=[];f=[]
    for _ in range(2200):
        x,y=rng.uniform(-.042,.042,2)
        r=np.hypot(x,y)
        if r>.042:continue
        z=.022-.007*(r/.043)**2;r0=rng.uniform(.00025,.00065);k=len(p)
        p.extend([(x-.048-r0,y+.209,z),(x-.048+r0,y+.209,z),
                  (x-.048,y+.209+r0,z),(x-.048,y+.209,z+r0)])
        f.extend([(k,k+1,k+3),(k+1,k+2,k+3),(k+2,k,k+3)])
    _mesh(stage,'/World/SugarBowl/Granules',p,f,sugar)
    tub(stage,'/World/ButterTub',(.123,.172,-.003),-17,white,blue,label,butter)
    knife_steel=_textured_material(stage,'KnifeSteel',tex/'stone-gray.png',(.6,.62,.65),.19)
    # Use a constant metal colour; the only mapped detail is fine brushed relief.
    knife_shader=UsdShade.Shader.Get(stage,'/World/Looks/KnifeSteel/Preview')
    knife_shader.GetInput('diffuseColor').DisconnectSource()
    knife_shader.GetInput('diffuseColor').Set(Gf.Vec3f(.6,.62,.65))
    knife_shader.GetInput('metallic').Set(1.0)
    normal_texture(stage,knife_steel,tex/'knife-brushed-normal.png')
    return add_knife(stage, '/World/Task/Knife', knife_steel, initial_knife_pose,
                     collider_thickness=knife_thickness)
