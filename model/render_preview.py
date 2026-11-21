import math
import sys

import bpy
from mathutils import Vector

blend, prefix = sys.argv[1], sys.argv[2]
bpy.ops.wm.open_mainfile(filepath=blend)
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 48
scene.cycles.use_denoising = True
scene.render.resolution_x, scene.render.resolution_y = 960, 600
scene.render.film_transparent = False

world = bpy.data.worlds.new("w")
scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs[0].default_value = (0.20, 0.32, 0.52, 1)
bg.inputs[1].default_value = 0.6

sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sun.data.energy = 3.5
sun.rotation_euler = (math.radians(40), math.radians(15), math.radians(30))
scene.collection.objects.link(sun)

cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
scene.collection.objects.link(cam)
scene.camera = cam

VIEWS = {
    "front34": (Vector((14, 17, 6)), 40),
    "rear34": (Vector((-15, -17, 7)), 40),
    "top": (Vector((0, 0, 30)), 0),
    "side": (Vector((30, 0, 0.6)), 0),
    "front": (Vector((0, 30, 0.6)), 0),
    "below34": (Vector((14, 15, -7)), 40),
}
views = sys.argv[3].split(",") if len(sys.argv) > 3 else list(VIEWS)
for name in views:
    pos, fov = VIEWS[name]
    cam.location = pos
    if fov == 0:
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = 17.5
    else:
        cam.data.type = "PERSP"
        cam.data.angle = math.radians(fov)
    d = Vector((0, 0, 0)) - pos
    cam.rotation_euler = d.to_track_quat("-Z", "Y" if name != "top" else "Y").to_euler()
    if name == "top":
        cam.rotation_euler = (0, 0, math.radians(-90))
    scene.render.filepath = f"{prefix}_{name}.png"
    bpy.ops.render.render(write_still=True)
    print("wrote", scene.render.filepath)
