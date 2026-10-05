# Shared helpers for building a chibi on the Kenney rig (Blender: Z up, the figure faces -Y,
# her left is +X). Every part is a separate object, rigidly skinned to one bone.
import bpy, bmesh, math
from mathutils import Vector, Matrix, Euler

KENNEY = "/Users/vincelo/Dev/aisiwhale/frontend/web/public/models/characters/character-female-f.glb"
COLL = "Figure"


def reset(name):
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for blk in (bpy.data.meshes, bpy.data.materials, bpy.data.armatures, bpy.data.actions, bpy.data.curves, bpy.data.images):
        for b in list(blk):
            blk.remove(b)
    bpy.ops.import_scene.gltf(filepath=KENNEY)
    arm = None
    for o in list(bpy.data.objects):
        if o.type == "ARMATURE":
            arm = o
        else:
            bpy.data.objects.remove(o, do_unlink=True)
    arm.name = name
    arm.data.name = name
    if arm.animation_data:
        arm.animation_data.action = None
    for pb in arm.pose.bones:
        pb.matrix_basis.identity()
    for img in list(bpy.data.images):
        bpy.data.images.remove(img)
    for m in list(bpy.data.materials):
        bpy.data.materials.remove(m)
    return arm


def rig():
    return next(o for o in bpy.data.objects if o.type == "ARMATURE")


_mats = {}


def mat(name, hexcolor, rough=0.75, metal=0.0):
    m = bpy.data.materials.get(name)
    if m is None:
        m = bpy.data.materials.new(name)
        m.use_nodes = True
    h = hexcolor.lstrip("#")
    srgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in srgb]
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*lin, 1)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    m.diffuse_color = (*lin, 1)
    return m


def bind(o, bone, material, smooth=True):
    """Give o a material, skin it all to ``bone`` and parent it to the rig."""
    arm = rig()
    o.data.materials.clear()
    o.data.materials.append(material)
    if smooth:
        for p in o.data.polygons:
            p.use_smooth = True
    o.vertex_groups.clear()
    g = o.vertex_groups.new(name=bone)
    g.add(list(range(len(o.data.vertices))), 1.0, "REPLACE")
    o.parent = arm
    mod = o.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    o["bone"] = bone
    return o


def _new(name, bm):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    return o


def ellipsoid(name, center, radii, bone, material, seg=12, rings=6, rot=(0, 0, 0), cut=None):
    """An ellipsoid; ``cut(v)`` (in the unit sphere's space, before scaling) drops vertices."""
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=rings, radius=1.0)
    if cut:
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if cut(v.co)], context="VERTS")
    m = Matrix.Translation(center) @ Euler(rot).to_matrix().to_4x4() @ Matrix.Diagonal((*radii, 1))
    bm.transform(m)
    return bind(_new(name, bm), bone, material)


def tube(name, a, b, r1, r2=None, bone=None, material=None, seg=10, caps=True, profile=None):
    """A (truncated) cone from point a to b; ``profile(i)`` scales the radius per side vertex
    (for pleats)."""
    r2 = r1 if r2 is None else r2
    a, b = Vector(a), Vector(b)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=caps, cap_tris=False, segments=seg, radius1=r1, radius2=r2, depth=1.0)
    if profile:
        for v in bm.verts:
            ang = math.atan2(v.co.y, v.co.x)
            k = profile(ang)
            v.co.x *= k
            v.co.y *= k
    d = b - a
    rot = d.to_track_quat("Z", "Y").to_matrix().to_4x4()
    m = Matrix.Translation((a + b) / 2) @ rot @ Matrix.Diagonal((1, 1, d.length, 1))
    bm.transform(m)
    return bind(_new(name, bm), bone, material)


def box(name, center, size, bone, material, bevel=0.3, rot=(0, 0, 0)):
    """A rounded box: ``bevel`` is the fraction of the smallest side rounded off."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.transform(Matrix.Diagonal((*size, 1)))
    if bevel:
        bmesh.ops.bevel(bm, geom=bm.verts[:] + bm.edges[:], offset=min(size) * bevel / 2, segments=2,
                        affect="EDGES", profile=0.5)
    bm.transform(Matrix.Translation(center) @ Euler(rot).to_matrix().to_4x4())
    return bind(_new(name, bm), bone, material)


def stroke(name, points, radius, bone, material, closed=False):
    """A round wire through ``points`` (for mouths, brows, straps)."""
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = radius
    cu.bevel_resolution = 0
    cu.use_fill_caps = True
    sp = cu.splines.new("POLY" if len(points) < 3 else "NURBS")
    sp.points.add(len(points) - 1)
    for p, co in zip(sp.points, points):
        p.co = (*co, 1)
    if sp.type == "NURBS":
        sp.use_endpoint_u = True
        sp.order_u = 3
        sp.resolution_u = 2
    sp.use_cyclic_u = closed
    o = bpy.data.objects.new(name, cu)
    bpy.context.scene.collection.objects.link(o)
    me = bpy.data.meshes.new_from_object(o.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    bpy.data.objects.remove(o)
    bpy.data.curves.remove(cu)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return bind(ob, bone, material)


class Head:
    """The head as an ellipsoid; places things on its surface."""

    def __init__(self, center, radii):
        self.c = Vector(center)
        self.r = Vector(radii)

    def surface(self, x, z, lift=0.0, back=False):
        """The point on the face (front, -Y; or the back) at (x, z), raised ``lift`` off it,
        and the rotation that turns an object's -Y toward the outward normal."""
        dx, dz = (x - self.c.x) / self.r.x, (z - self.c.z) / self.r.z
        k = max(0.0, 1 - dx * dx - dz * dz)
        y = self.c.y + (1 if back else -1) * self.r.y * math.sqrt(k)
        p = Vector((x, y, z))
        n = Vector(((x - self.c.x) / self.r.x ** 2, (y - self.c.y) / self.r.y ** 2, (z - self.c.z) / self.r.z ** 2)).normalized()
        return p + n * lift, n.to_track_quat("-Y", "Z").to_euler()

    def decal(self, name, x, z, size, material, lift=0.004, spin=0.0):
        p, rot = self.surface(x, z, lift)
        e = Euler(rot)
        o = ellipsoid(name, p, size, "head", material, seg=10, rings=5, rot=e)
        if spin:
            o.rotation_mode = "XYZ"
        return o

    def curve(self, name, pts, radius, material, lift=0.003):
        return stroke(name, [self.surface(x, z, lift)[0] for x, z in pts], radius, "head", material)


def finish():
    arm = rig()
    bpy.context.view_layer.objects.active = arm
    tris = sum(len(o.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.polygons) for o in bpy.data.objects if o.type == "MESH")
    print("parts", len([o for o in bpy.data.objects if o.type == "MESH"]), "faces", tris)
