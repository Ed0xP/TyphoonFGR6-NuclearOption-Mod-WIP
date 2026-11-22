import sys, re, math
import bpy, numpy as np
from mathutils import Vector
obj, out, rx, cam, tgt, fov = sys.argv[-7:-1] if len(sys.argv[-1]) < 6 and sys.argv[-1].isdigit() else sys.argv[-6:]
res = int(sys.argv[-1]) if sys.argv[-1].isdigit() else 900
rx = re.compile(rx)
V=[];F=[];g=None
for l in open(obj):
    if l.startswith('v '): V.append([float(x) for x in l.split()[1:4]])
    elif l[:2] in ('o ','g '): g=l.split()[1]
    elif l.startswith('f ') and g and rx.search(g):
        F.append([int(t.split('/')[0])-1 for t in l.split()[1:]])
used=sorted({i for f in F for i in f}); idx={v:i for i,v in enumerate(used)}
U=lambda p:(-p[0],-p[2],p[1])
bpy.ops.wm.read_factory_settings(use_empty=True)
me=bpy.data.meshes.new('m'); me.from_pydata([U(V[i]) for i in used],[],[[idx[i] for i in f] for f in F]); me.update()
ob=bpy.data.objects.new('m',me); bpy.context.scene.collection.objects.link(ob)
mat=bpy.data.materials.new('c'); mat.use_nodes=True; b=mat.node_tree.nodes['Principled BSDF']; b.inputs['Base Color'].default_value=(0.55,0.55,0.55,1); b.inputs['Roughness'].default_value=0.6
me.materials.append(mat)
sc=bpy.context.scene; sc.render.engine='CYCLES'; sc.cycles.samples=24; sc.cycles.use_denoising=False
c=bpy.data.cameras.new('c'); co=bpy.data.objects.new('c',c); sc.collection.objects.link(co); sc.camera=co
p=Vector(U([float(a) for a in cam.split(',')])); t=Vector(U([float(a) for a in tgt.split(',')]))
co.location=p; co.rotation_euler=(t-p).to_track_quat('-Z','Y').to_euler(); c.angle=math.radians(float(fov)); c.clip_start=0.01
w=bpy.data.worlds.new('w'); sc.world=w; w.use_nodes=True; w.node_tree.nodes['Background'].inputs[0].default_value=(0.8,0.85,0.95,1); w.node_tree.nodes['Background'].inputs[1].default_value=0.7
s=bpy.data.lights.new('s','SUN'); s.energy=3; so=bpy.data.objects.new('s',s); sc.collection.objects.link(so); so.rotation_euler=(math.radians(50),0,math.radians(160))
sc.render.resolution_x=res; sc.render.resolution_y=int(res*0.75); sc.render.filepath=out
bpy.ops.render.render(write_still=True)
