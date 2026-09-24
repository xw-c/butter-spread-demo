"""Extract two surface LODs from the MIT-licensed CD-MPM bread VDB using Blender."""
from pathlib import Path
import bpy,numpy as np,json,hashlib
root=Path(__file__).resolve().parents[1]
volume=bpy.data.volumes.new('UpstreamCDMPM')
volume.filepath=str(root/'assets/reference/cdmpm/breadxxx.vdb')
volume.grids.load()
obj=bpy.data.objects.new('UpstreamVolume',volume);bpy.context.collection.objects.link(obj)
target=bpy.data.objects.new('ExtractedMesh',bpy.data.meshes.new('Extraction'))
bpy.context.collection.objects.link(target)
mod=target.modifiers.new('IsoSurface','VOLUME_TO_MESH')
mod.object=obj;mod.grid_name='surface';mod.threshold=0.0
mod.resolution_mode='VOXEL_AMOUNT';mod.adaptivity=.035
report={'upstream':'https://github.com/penn-graphics-research/ziran2019/blob/master/Data/LevelSets/breadxxx.vdb.zip',
        'license':'MIT, Copyright (c) 2020 Penn Graphics Research',
        'asset_use':'reference VDB surface only; no CD-MPM fracture simulation is run',
        'lods':[]}
for name,res in [('hero',512),('background',240)]:
    mod.voxel_amount=res
    dg=bpy.context.evaluated_depsgraph_get();dg.update()
    evaluated=target.evaluated_get(dg);mesh=evaluated.to_mesh()
    vertices=np.empty(len(mesh.vertices)*3,np.float32);mesh.vertices.foreach_get('co',vertices)
    vertices=vertices.reshape(-1,3)
    mesh.calc_loop_triangles()
    faces=np.empty(len(mesh.loop_triangles)*3,np.int32);mesh.loop_triangles.foreach_get('vertices',faces)
    faces=faces.reshape(-1,3)
    path=root/f'assets/cdmpm-bread-{name}.npz'
    np.savez_compressed(path,vertices=vertices,faces=faces)
    info={'name':name,'voxel_amount':res,'vertices':len(vertices),'triangles':len(faces),
          'bounds':[vertices.min(0).tolist(),vertices.max(0).tolist()],
          'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    report['lods'].append(info);print(json.dumps(info),flush=True)
    evaluated.to_mesh_clear()
(root/'assets/reference/cdmpm/mesh-provenance.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
