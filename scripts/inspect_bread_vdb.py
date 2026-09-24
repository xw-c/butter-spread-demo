"""Run with Blender's Python to inspect the upstream CD-MPM level set."""
from pathlib import Path
import bpy,json
root=Path(__file__).resolve().parents[1]
v=bpy.data.volumes.new('CDMPM_Bread')
v.filepath=str(root/'assets/reference/cdmpm/breadxxx.vdb')
v.grids.load()
print('VDB_GRIDS',[(g.name,g.data_type) for g in v.grids],flush=True)
obj=bpy.data.objects.new('BreadVolume',v);bpy.context.collection.objects.link(obj)
target=bpy.data.objects.new('BreadMesh',bpy.data.meshes.new('BreadMesh'))
bpy.context.collection.objects.link(target)
mod=target.modifiers.new('ExtractUpstreamSurface','VOLUME_TO_MESH')
print('MOD_PROPERTIES',[(p.identifier,p.type) for p in mod.bl_rna.properties],flush=True)
mod.object=obj
mod.grid_name=v.grids[0].name
mod.threshold=0.0
mod.resolution_mode='GRID'
mod.adaptivity=.015
dg=bpy.context.evaluated_depsgraph_get()
dg.update()
mesh=target.evaluated_get(dg).to_mesh()
print('EXTRACTED',len(mesh.vertices),len(mesh.polygons),flush=True)
import numpy as np
verts=np.empty(len(mesh.vertices)*3,np.float32)
mesh.vertices.foreach_get('co',verts)
verts=verts.reshape(-1,3)
print('BOUNDS',verts.min(axis=0).tolist(),verts.max(axis=0).tolist(),flush=True)
mesh.calc_loop_triangles()
faces=np.empty(len(mesh.loop_triangles)*3,np.int32)
mesh.loop_triangles.foreach_get('vertices',faces)
out=root/'assets/cdmpm-bread-raw.npz'
np.savez_compressed(out,vertices=verts,faces=faces.reshape(-1,3))
print('SAVED',out,flush=True)
