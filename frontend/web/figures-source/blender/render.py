# usage: blender -b --python render.py -- in.glb out_prefix [action] [frame]
import bpy, sys, math
argv=sys.argv[sys.argv.index("--")+1:]
src,out=argv[0],argv[1]
action=argv[2] if len(argv)>2 else None
frame=float(argv[3]) if len(argv)>3 else 0
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
for o in list(bpy.data.objects):
    if o.name=="Icosphere": bpy.data.objects.remove(o)
arm=[o for o in bpy.data.objects if o.type=='ARMATURE'][0]
if action:
    arm.animation_data_create()
    act=bpy.data.actions[action]
    arm.animation_data.action=act
    try:
        arm.animation_data.action_slot=act.slots[0]
    except Exception as e: print(e)
    r=act.frame_range; f=r[0]+(r[1]-r[0])*frame
    bpy.context.scene.frame_set(int(f))
else:
    if arm.animation_data: arm.animation_data.action=None
    for pb in arm.pose.bones: pb.matrix_basis.identity()
sc=bpy.context.scene
sc.render.engine='BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items] else 'BLENDER_EEVEE'
sc.render.resolution_x=sc.render.resolution_y=512
sc.render.film_transparent=False
w=bpy.data.worlds.new("w"); sc.world=w; w.use_nodes=True
w.node_tree.nodes["Background"].inputs[0].default_value=(0.9,0.88,0.92,1); w.node_tree.nodes["Background"].inputs[1].default_value=1.0
sun=bpy.data.objects.new("sun",bpy.data.lights.new("sun",'SUN')); sc.collection.objects.link(sun)
sun.data.energy=3; sun.rotation_euler=(math.radians(50),math.radians(10),math.radians(30))
cam=bpy.data.objects.new("cam",bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera=cam
cam.data.type='ORTHO'; cam.data.ortho_scale=0.8
for name,ang in [("front",0),("side",90),("back",180),("q",35)]:
    a=math.radians(ang); d=3
    cam.location=(d*math.sin(a),-d*math.cos(a),0.36+ (0.25 if name=="q" else 0))
    cam.rotation_euler=(math.radians(90 - (8 if name=="q" else 0)),0,a)
    sc.render.filepath=f"{out}-{name}.png"
    bpy.ops.render.render(write_still=True)
