# Join the parts into one skinned mesh (on copies; the parts stay editable), fit the triangle
# budget, and write OUT (a GLB with every clip; baked textures as JPEG). Expects OUT and BUDGET.
import bmesh
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
if arm.animation_data:
    arm.animation_data.action = None
for pb in arm.pose.bones:
    pb.matrix_basis.identity()
bpy.context.scene.frame_set(0)
parts = [o for o in bpy.data.objects if o.type == "MESH" and o.parent == arm]
copies = []
for o in parts:
    c = o.copy()
    c.data = o.data.copy()
    bpy.context.scene.collection.objects.link(c)
    copies.append(c)
bpy.ops.object.select_all(action="DESELECT")
for c in copies:
    c.select_set(True)
bpy.context.view_layer.objects.active = copies[0]
bpy.ops.object.join()
body = bpy.context.view_layer.objects.active
body.name = arm.name + "-mesh"
body.data.name = body.name
for m in list(body.modifiers):
    body.modifiers.remove(m)
tris = sum(len(p.vertices) - 2 for p in body.data.polygons)
if tris > BUDGET:
    dec = body.modifiers.new("Decimate", "DECIMATE")
    dec.ratio = BUDGET / tris * 0.98
    bpy.ops.object.modifier_apply(modifier="Decimate")
mod = body.modifiers.new("Armature", "ARMATURE")
mod.object = arm
after = sum(len(p.vertices) - 2 for p in body.data.polygons)
bpy.ops.object.select_all(action="DESELECT")
body.select_set(True)
arm.select_set(True)
bpy.context.view_layer.objects.active = arm
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=True, export_animations=True,
                          export_animation_mode="ACTIONS", export_skins=True, export_apply=False,
                          export_yup=True, export_texcoords=True, export_normals=True,
                          export_tangents=True, export_image_format="JPEG", export_image_quality=88,
                          export_jpeg_quality=88)
bpy.data.objects.remove(body, do_unlink=True)
print("triangles", tris, "->", after)
