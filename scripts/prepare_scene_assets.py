"""Build deterministic surface maps and a continuous hand mesh for the reference scene."""
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import gaussian_filter
from skimage.measure import marching_cubes

ROOT = Path(__file__).resolve().parents[1] / 'assets'
TEX = ROOT / 'textures'
rng = np.random.default_rng(42)

# Vector-style seigaiha artwork, not a photograph projected onto the scene.
n = 2048
img = Image.new('RGB', (n,n), (224,225,215))
d = ImageDraw.Draw(img)
pitch = 256
for row in range(-2, 18):
    for col in range(-2, 11):
        x = col*pitch + (row % 2)*pitch/2
        y = row*pitch/2
        d.pieslice((x-128,y-128,x+128,y+128),180,360,fill=(224,225,215))
        for r in (124,99,74,49,24):
            d.arc((x-r,y-r,x+r,y+r),180,360,fill=(15,27,37),width=7)
img.save(TEX / 'seigaiha.png')

noise = rng.normal(size=(n,n)).astype(np.float32)
cloud = gaussian_filter(noise, 48)
cloud /= cloud.std()
stone = 104 + 5*cloud + 6*gaussian_filter(noise, .5)
rgb = np.stack((stone*.99,stone,stone*.985),axis=-1)
Image.fromarray(np.clip(rgb,0,255).astype('uint8')).save(TEX/'stone-gray.png')

# Fine non-directional normal map for the countertop.
h = gaussian_filter(noise,1.0)
dy, dx = np.gradient(h)
normal = np.stack((-dx*.28,-dy*.28,np.ones_like(h)),axis=-1)
normal /= np.linalg.norm(normal,axis=-1,keepdims=True)
Image.fromarray(((normal*.5+.5)*255).astype('uint8')).save(TEX/'stone-normal.png')

# An editable packaging label matching the reference's blue/white tub.
label=Image.new('RGB',(1600,700),(62,158,185)); q=ImageDraw.Draw(label)
q.rectangle((0,100,1600,510),fill=(235,232,211))
fontpath=Path('C:/Windows/Fonts/arialbd.ttf')
font=ImageFont.truetype(str(fontpath),200)
q.text((110,165),'Blue Band',font=font,fill=(24,42,65))
q.ellipse((1250,155,1380,285),fill=(220,168,48))
q.text((240,550),'MARGARINE',font=ImageFont.truetype(str(fontpath),66),fill=(234,232,212))
label.save(TEX/'tub-label.png')

# Smooth union of tapered finger and palm volumes. Mesh is continuous rather
# than intersecting visible primitives. It is a visual asset, not a collider.
voxel=.00125
origin=np.array([-.057,-.185,-.021])
shape=(93,153,63)
grid=np.moveaxis(np.indices(shape,dtype=np.float32),0,-1)*voxel+origin
field=np.full(shape,1.,dtype=np.float32)
def union(sdf,k=.004):
    global field
    h=np.maximum(k-np.abs(field-sdf),0)/k
    field=np.minimum(field,sdf)-h*h*k*.25
def ellipsoid(center,radii):
    q=(grid-center)/radii
    union((np.linalg.norm(q,axis=-1)-1)*min(radii))
def segment(a,b,ra,rb):
    a,b=np.array(a),np.array(b)
    t=np.clip(np.sum((grid-a)*(b-a),axis=-1)/np.sum((b-a)**2),0,1)
    union(np.linalg.norm(grid-a-t[...,None]*(b-a),axis=-1)-(ra+(rb-ra)*t))
ellipsoid((0,-.098,0),(.034,.039,.0125))
segment((0,-.17,-.003),(0,-.116,0),.022,.024)
# Extended left hand, a small stabilizing gesture at the plate's edge.
tips=[]
for x,y,r in [(-.027,-.062,.007),(-.010,-.037,.008),(.009,-.030,.0083),(.027,-.043,.0074)]:
    a=(x*.8,-.092,0); b=(x,y-.02,.004); c=(x+.001,y,.003)
    segment(a,b,r*1.12,r); segment(b,c,r,r*.78)
    tips.append((c,r))
segment((.025,-.105,0),(.043,-.083,.001),.011,.009)
segment((.043,-.083,.001),(.050,-.064,.001),.009,.007)
v,f,normals,_=marching_cubes(field,0,spacing=(voxel,)*3)
v+=origin
np.savez_compressed(ROOT/'hand-rest.npz',vertices=v.astype('float32'),faces=f.astype('int32'),normals=normals)
print('Prepared scene textures and continuous hand mesh')
