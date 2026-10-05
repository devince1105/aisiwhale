# The game mesh (D-197): low-poly envelopes of the high-poly (tifa_hi.py) within the 3,000-triangle
# budget, weighted to the Kenney rig, with the high-poly's colour, normals and occlusion baked onto
# one atlas. Needs lib.py and sculpt.py; the HI collection must already be built. Expects TEX (the
# atlas size), CAGE and RAY (bake distances), GROUPS: {name: (bone | "auto" | "legs" | weights(co), triangles,
# symmetric, [HI object name prefixes], voxel, inflate)} and LOW_EXTRA() (parts authored low).
import numpy as np

arm = rig()
hi = {o.name: o for o in bpy.data.collections[HI].objects}
for o in list(bpy.data.objects):          # a previous game mesh
    if o is not arm and o.name not in hi:
        bpy.data.objects.remove(o, do_unlink=True)
for img in list(bpy.data.images):
    bpy.data.images.remove(img)
for m in list(bpy.data.materials):        # its materials
    if m.name.startswith(("bake", arm.name)) or m.users == 0:
        bpy.data.materials.remove(m)


def pick(prefixes):
    return [o for n, o in hi.items() if any(n == p or n.startswith(p) for p in prefixes)]


def envelope(name, prefixes, tris, symmetric, voxel, inflate):
    """The union of these high-poly parts, remeshed coarse, pushed out ``inflate`` (to cover garment
    layers lifted off a skin) and collapsed to ``tris`` triangles."""
    copies = []
    for o in pick(prefixes):
        c = o.copy()
        c.data = o.data.copy()
        bpy.context.scene.collection.objects.link(c)
        copies.append(c)
    o = union(name, copies, voxel=voxel, smooth=2, smooth_factor=0.5)
    for c in list(o.users_collection):
        c.objects.unlink(o)
    bpy.context.scene.collection.objects.link(o)
    if inflate:
        d = o.modifiers.new("Inflate", "DISPLACE")
        d.strength = inflate
        d.mid_level = 0
        apply_all(o)
    return collapse(o, tris, symmetric)


def collapse(o, tris, symmetric):
    now = sum(len(p.vertices) - 2 for p in o.data.polygons)
    if now > tris:
        d = o.modifiers.new("Decimate", "DECIMATE")
        d.ratio = tris / now
        d.use_symmetry = symmetric
        d.symmetry_axis = "X"
        apply_all(o)
    tri = o.modifiers.new("Triangulate", "TRIANGULATE")
    apply_all(o)
    for p in o.data.polygons:
        p.use_smooth = True
    return o


def weigh(o, bone):
    o.vertex_groups.clear()
    if callable(bone):              # explicit weights: bone(co) -> {bone name: weight}
        groups = {}
        for v in o.data.vertices:
            for name, w in bone(v.co).items():
                if w > 1e-3:
                    if name not in groups:
                        groups[name] = o.vertex_groups.new(name=name)
                    groups[name].add([v.index], w, "REPLACE")
        return
    if bone == "auto":
        bpy.ops.object.select_all(action="DESELECT")
        o.select_set(True)
        arm.select_set(True)
        bpy.context.view_layer.objects.active = arm
        bpy.ops.object.parent_set(type="ARMATURE_AUTO")
        for m in list(o.modifiers):
            o.modifiers.remove(m)
        o.parent = None
        return
    if bone == "legs":
        groups = {b: o.vertex_groups.new(name=b) for b in ("leg-left", "leg-right")}
        for v in o.data.vertices:
            groups["leg-left" if v.co.x > 0 else "leg-right"].add([v.index], 1.0, "REPLACE")
        return
    g = o.vertex_groups.new(name=bone)
    g.add(list(range(len(o.data.vertices))), 1.0, "REPLACE")


# ---- build the envelopes ------------------------------------------------------------------------
lows = []
for name, (bone, tris, symmetric, prefixes, voxel, inflate) in GROUPS.items():
    o = envelope(name, prefixes, tris, symmetric, voxel, inflate)
    weigh(o, bone)
    # remember which envelope each face came from (the face gets more of the atlas)
    o.data.attributes.new("part", "INT", "FACE").data.foreach_set("value", [len(lows)] * len(o.data.polygons))
    o["part"] = name
    lows.append(o)
for o in LOW_EXTRA():            # parts authored low directly (the skirt, the earrings)
    o.data.attributes.new("part", "INT", "FACE").data.foreach_set("value", [len(lows)] * len(o.data.polygons))
    o["part"] = o.name
    lows.append(o)
part_of = {o["part"]: i for i, o in enumerate(lows)}

bpy.ops.object.select_all(action="DESELECT")
for o in lows:
    o.select_set(True)
bpy.context.view_layer.objects.active = lows[0]
bpy.ops.object.join()
low = bpy.context.view_layer.objects.active
low.name = low.data.name = arm.name + "-mesh"
low.data.materials.clear()
low.data.validate()
print("low triangles", sum(len(p.vertices) - 2 for p in low.data.polygons))

# ---- UVs ------------------------------------------------------------------------------------------
bpy.ops.object.select_all(action="DESELECT")
low.select_set(True)
bpy.context.view_layer.objects.active = low
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.01)


def uv_islands(bm, uv):
    """Faces grouped into UV islands (faces joined by an edge whose UVs match on both sides)."""
    parent = {f: f for f in bm.faces}

    def find(f):
        while parent[f] is not f:
            parent[f] = parent[parent[f]]
            f = parent[f]
        return f

    for e in bm.edges:
        if len(e.link_faces) != 2:
            continue
        f1, f2 = e.link_faces
        ok = True
        for v in e.verts:
            a = next(l[uv].uv for l in f1.loops if l.vert is v)
            b = next(l[uv].uv for l in f2.loops if l.vert is v)
            ok &= (a - b).length < 1e-5
        if ok:
            parent[find(f1)] = find(f2)
    groups = {}
    for f in bm.faces:
        groups.setdefault(find(f), []).append(f)
    return list(groups.values())


bm = bmesh.from_edit_mesh(low.data)
uv = bm.loops.layers.uv.active
part = bm.faces.layers.int.get("part")
# faces seen head-on (the painted face) are re-projected flat from the front as one island
for f in bm.faces:
    if FRONT_PROJECT(f, part, part_of):
        for l in f.loops:
            l[uv].uv = Vector((l.vert.co.x, l.vert.co.z))
# then each island is scaled by the first rule a face of it matches, before packing
rules = UV_SCALE(bm, part, part_of)
for isl in uv_islands(bm, uv):
    factor = next((k for test, k in rules if any(test(f) for f in isl)), 1.0)
    # bring every island to the same texel density first, then apply the rule
    a_uv = sum(abs((f.loops[i][uv].uv - f.loops[0][uv].uv).cross(f.loops[i + 1][uv].uv - f.loops[0][uv].uv)) / 2
               for f in isl for i in range(1, len(f.loops) - 1))
    a_3d = sum(f.calc_area() for f in isl)
    if a_uv < 1e-12:
        continue
    factor *= math.sqrt(a_3d / a_uv)
    c = sum((l[uv].uv for f in isl for l in f.loops), Vector((0, 0))) / sum(len(f.loops) for f in isl)
    for f in isl:
        for l in f.loops:
            l[uv].uv = c + (l[uv].uv - c) * factor
bmesh.update_edit_mesh(low.data)
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.pack_islands(rotate=True, margin=0.01)
bpy.ops.object.mode_set(mode="OBJECT")

# ---- bake ------------------------------------------------------------------------------------------
sc = bpy.context.scene
try:
    sc.render.engine = "CYCLES"
except TypeError as e:
    raise SystemExit(e)
sc.cycles.device = "CPU"


def image(name, color=True):
    img = bpy.data.images.get(name)
    if img:
        bpy.data.images.remove(img)
    img = bpy.data.images.new(name, TEX, TEX, alpha=False, float_buffer=not color)
    if not color:
        img.colorspace_settings.name = "Non-Color"
    return img


bake_mat = bpy.data.materials.new("bake")
bake_mat.use_nodes = True
low.data.materials.append(bake_mat)
node = bake_mat.node_tree.nodes.new("ShaderNodeTexImage")
bake_mat.node_tree.nodes.active = node

for o in hi.values():
    o.hide_render = False
    o.hide_set(False)


def piece(index):
    """A copy of the game mesh holding only the faces from one part (same UVs)."""
    o = low.copy()
    o.data = low.data.copy()
    bpy.context.scene.collection.objects.link(o)
    o.hide_render = False
    bm = bmesh.new()
    bm.from_mesh(o.data)
    lay = bm.faces.layers.int.get("part")
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f[lay] != index], context="FACES")
    bm.to_mesh(o.data)
    bm.free()
    return o


color, normal, ao = image(arm.name + "-color"), image(arm.name + "-normal", color=False), image(arm.name + "-ao", color=False)
for img, fill in ((color, (0.5, 0.5, 0.5, 1)), (normal, (0.5, 0.5, 1, 1)), (ao, (1, 1, 1, 1))):
    img.pixels[:] = np.tile(fill, TEX * TEX)
# each part is baked from its own high-poly sources only, so hair never picks up skin underneath;
# the whole game mesh stays out of the render meanwhile, or it shadows the occlusion bake
low.hide_render = True
for name, index in part_of.items():
    src = pick(BAKE_FROM[name])
    pc = piece(index)
    bpy.ops.object.select_all(action="DESELECT")
    for o in src:
        o.select_set(True)
    pc.select_set(True)
    bpy.context.view_layer.objects.active = pc
    for kind, img, samples, kw in (("DIFFUSE", color, 4, {"pass_filter": {"COLOR"}}), ("NORMAL", normal, 4, {}), ("AO", ao, 48, {})):
        node.image = img
        sc.cycles.samples = samples
        bpy.ops.object.bake(type=kind, use_selected_to_active=True, cage_extrusion=CAGE_FOR.get(name, CAGE), max_ray_distance=RAY,
                            margin=3, use_clear=False, **kw)
    bpy.data.objects.remove(pc, do_unlink=True)
low.hide_render = False

# occlusion multiplied into the colour, softened so the flat colours stay bright
c = np.array(color.pixels[:]).reshape(-1, 4)
a = np.array(ao.pixels[:]).reshape(-1, 4)[:, :1]
c[:, :3] *= 0.5 + 0.5 * a
color.pixels[:] = c.ravel()
final = bpy.data.images.new(arm.name, TEX, TEX, alpha=False)
final.pixels[:] = color.pixels[:]
final.file_format = "PNG"
final.pack()
nrm = bpy.data.images.new(arm.name + "-normal-map", TEX, TEX, alpha=False)
nrm.colorspace_settings.name = "Non-Color"
nrm.pixels[:] = normal.pixels[:]
nrm.file_format = "PNG"
nrm.pack()

# ---- the shipped material -------------------------------------------------------------------------
low.data.materials.clear()
m = bpy.data.materials.new(arm.name)
m.use_nodes = True
m.use_backface_culling = False       # the skirt is one sheet
nt = m.node_tree
bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
tc = nt.nodes.new("ShaderNodeTexImage")
tc.image = final
tn = nt.nodes.new("ShaderNodeTexImage")
tn.image = nrm
nm = nt.nodes.new("ShaderNodeNormalMap")
nt.links.new(tc.outputs["Color"], bsdf.inputs["Base Color"])
nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
bsdf.inputs["Roughness"].default_value = 0.7
low.data.materials.append(m)

for o in hi.values():
    o.select_set(False)
    o.hide_set(True)
    o.hide_render = True
for img in (color, normal, ao):
    bpy.data.images.remove(img)
low.parent = arm
mod = low.modifiers.new("Armature", "ARMATURE")
mod.object = arm
sc.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in [e.identifier for e in sc.render.bl_rna.properties["engine"].enum_items] else sc.render.engine
print("baked", TEX)
