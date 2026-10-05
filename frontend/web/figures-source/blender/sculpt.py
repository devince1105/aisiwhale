# High-poly sculpting helpers (D-197): forms are unioned by voxel remesh and relaxed into one
# surface; clothes are offset layers lifted off that surface; hair is swept clumps. Nothing here is
# bound to the rig: the high-poly is only a source for baking (see lowpoly.py).
import bpy, bmesh, math
from mathutils import Vector, Matrix
from mathutils.kdtree import KDTree

HI = "HI"


def hi_collection():
    c = bpy.data.collections.get(HI)
    if c is None:
        c = bpy.data.collections.new(HI)
        bpy.context.scene.collection.children.link(c)
    return c


def to_hi(o, material=None):
    """Strip the rig binding lib.py gives every part and move it to the HI collection."""
    for m in list(o.modifiers):
        o.modifiers.remove(m)
    o.vertex_groups.clear()
    o.parent = None
    for c in list(o.users_collection):
        c.objects.unlink(o)
    hi_collection().objects.link(o)
    if material is not None:
        o.data.materials.clear()
        o.data.materials.append(material)
    for p in o.data.polygons:
        p.use_smooth = True
    return o


def apply_all(o):
    with bpy.context.temp_override(object=o, active_object=o, selected_objects=[o]):
        for m in list(o.modifiers):
            bpy.ops.object.modifier_apply(modifier=m.name)


def union(name, parts, voxel=0.003, smooth=8, smooth_factor=0.6, material=None):
    """Join the parts and voxel-remesh them into one closed surface, then relax the creases where
    they met — the 'blend' pass a sculptor would do by hand."""
    parts = list(parts)
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    for p in parts:
        m = p.data.copy()
        m.transform(p.matrix_world)
        bm.from_mesh(m)
        bpy.data.meshes.remove(m)
    bm.to_mesh(me)
    bm.free()
    for p in parts:
        bpy.data.objects.remove(p, do_unlink=True)
    o = bpy.data.objects.new(name, me)
    hi_collection().objects.link(o)
    r = o.modifiers.new("Remesh", "REMESH")
    r.mode = "VOXEL"
    r.voxel_size = voxel
    r.use_smooth_shade = True
    if smooth:
        s = o.modifiers.new("Relax", "SMOOTH")
        s.factor = smooth_factor
        s.iterations = smooth
    apply_all(o)
    if material is not None:
        o.data.materials.append(material)
    return o


def layer(name, source, keep, offset, material, thickness=0.0, rim=None):
    """A garment lifted off ``source``: the faces whose centre passes ``keep(co)``, pushed out by
    ``offset`` along the normals; optional ``thickness`` (solidify, inward). Returns the object
    and its boundary loops (lists of points) for trims."""
    bm = bmesh.new()
    bm.from_mesh(source.data)
    bm.transform(source.matrix_world)
    bm.normal_update()
    drop = [f for f in bm.faces if not keep(f.calc_center_median())]
    bmesh.ops.delete(bm, geom=drop, context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    # the cut follows the voxel grid in steps; relax each boundary loop along itself
    for _ in range(12):
        moves = {}
        for v in bm.verts:
            if not v.is_boundary:
                continue
            nb = [e.other_vert(v) for e in v.link_edges if e.is_boundary]
            if len(nb) == 2:
                moves[v] = (nb[0].co + nb[1].co) / 2
        for v, co in moves.items():
            v.co = v.co * 0.4 + co * 0.6
    bm.normal_update()
    for v in bm.verts:
        v.co += v.normal * offset
    loops = boundary_loops(bm)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    hi_collection().objects.link(o)
    o.data.materials.append(material)
    for p in o.data.polygons:
        p.use_smooth = True
    if thickness:
        s = o.modifiers.new("Solidify", "SOLIDIFY")
        s.thickness = thickness
        s.offset = -1
        apply_all(o)
    return o, loops


def boundary_loops(bm):
    edges = {e for e in bm.edges if e.is_boundary}
    loops = []
    while edges:
        e = edges.pop()
        chain = [e.verts[0], e.verts[1]]
        while True:
            nxt = [x for x in chain[-1].link_edges if x in edges]
            if not nxt:
                break
            edges.discard(nxt[0])
            v = nxt[0].other_vert(chain[-1])
            if v is chain[0]:
                break
            chain.append(v)
        if len(chain) > 6:
            loops.append([v.co.copy() for v in chain])
    return loops


def trim(name, pts, radius, material, closed=True, every=2):
    """A round piping along a boundary loop (necklines, hems, cuffs)."""
    pts = pts[::every]
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = radius
    cu.bevel_resolution = 2
    sp = cu.splines.new("NURBS")
    sp.points.add(len(pts) - 1)
    for p, co in zip(sp.points, pts):
        p.co = (*co, 1)
    sp.use_cyclic_u = closed
    sp.order_u = 3
    sp.resolution_u = 3
    o = bpy.data.objects.new(name, cu)
    hi_collection().objects.link(o)
    return curve_to_mesh(o, material)


def curve_to_mesh(o, material):
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(o.evaluated_get(dg))
    name = o.name
    cu = o.data
    bpy.data.objects.remove(o)
    bpy.data.curves.remove(cu)
    ob = bpy.data.objects.new(name, me)
    hi_collection().objects.link(ob)
    ob.data.materials.append(material)
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob


def sweep(name, path, widths, thick, material, normal_from=None, seg=12, steps=6, tip=True):
    """A clump swept along ``path`` (points): an ellipse ``widths[i]`` across by ``thick[i]`` deep
    (both interpolated along the path), its flat side facing away from ``normal_from`` (a point,
    e.g. the head's centre) — a hair clump or a strap. Ends are closed."""
    from mathutils import geometry
    path = [Vector(p) for p in path]
    # a smooth path through the points
    knots = []
    for i in range(len(path) - 1):
        p0 = path[max(i - 1, 0)]
        p1, p2 = path[i], path[i + 1]
        p3 = path[min(i + 2, len(path) - 1)]
        for k in range(steps):
            t = k / steps
            t2, t3 = t * t, t * t * t
            knots.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    knots.append(path[-1])
    n = len(knots)

    def lerp(vals, u):
        x = u * (len(vals) - 1)
        i = min(int(x), len(vals) - 2)
        f = x - i
        return vals[i] * (1 - f) + vals[i + 1] * f

    bm = bmesh.new()
    rings = []
    for i, c in enumerate(knots):
        u = i / (n - 1)
        tan = (knots[min(i + 1, n - 1)] - knots[max(i - 1, 0)]).normalized()
        out = (c - Vector(normal_from)).normalized() if normal_from is not None else Vector((0, -1, 0))
        out = (out - tan * out.dot(tan)).normalized()
        side = tan.cross(out).normalized()
        w, d = lerp(widths, u) / 2, lerp(thick, u) / 2
        if tip and i == n - 1:
            rings.append([bm.verts.new(c)])
            continue
        rings.append([bm.verts.new(c + side * (w * math.cos(a)) + out * (d * math.sin(a)))
                      for a in (2 * math.pi * k / seg for k in range(seg))])
    for lo, hi in zip(rings, rings[1:]):
        for k in range(seg):
            if len(hi) == 1:
                bm.faces.new((lo[k], lo[(k + 1) % seg], hi[0]))
            else:
                bm.faces.new((lo[k], lo[(k + 1) % seg], hi[(k + 1) % seg], hi[k]))
    bm.faces.new(rings[0])
    if len(rings[-1]) > 1:
        bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    hi_collection().objects.link(o)
    o.data.materials.append(material)
    for p in o.data.polygons:
        p.use_smooth = True
    return o


PLEATS = 16


def pleated_skirt(name, top, bottom, r_top, r_bottom, material, seg=192, rings=24, thickness=0.003):
    """Knife pleats that open toward the hem (seg should be a multiple of PLEATS)."""
    bm = bmesh.new()
    grid = []
    for j in range(rings + 1):
        f = j / rings
        z = top + (bottom - top) * f
        r = r_top + (r_bottom - r_top) * f ** 0.7
        depth = 0.012 * f ** 0.8 + 0.002
        row = []
        for k in range(seg):
            a = 2 * math.pi * k / seg
            u = (a * PLEATS / (2 * math.pi)) % 1
            # a sawtooth: each pleat steps out, then folds sharply back under the next
            saw = u if u < 0.85 else (1 - u) / 0.15 * 0.85
            rr = r + depth * (saw - 0.5)
            row.append(bm.verts.new((rr * math.cos(a), 0.028 + rr * math.sin(a) * 0.86, z)))
        grid.append(row)
    for j in range(rings):
        for k in range(seg):
            bm.faces.new((grid[j][k], grid[j][(k + 1) % seg], grid[j + 1][(k + 1) % seg], grid[j + 1][k]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    hi_collection().objects.link(o)
    o.data.materials.append(material)
    for p in o.data.polygons:
        p.use_smooth = True
    if thickness:
        sol = o.modifiers.new("Solidify", "SOLIDIFY")
        sol.thickness = thickness
        apply_all(o)
    return o


class Surface:
    """Places things on a sculpted (not analytic) surface by casting rays at it from the front."""

    def __init__(self, o):
        from mathutils.bvhtree import BVHTree
        self.tree = BVHTree.FromObject(o, bpy.context.evaluated_depsgraph_get())

    def at(self, x, z, lift=0.0):
        """The point on the front of the surface at (x, z), raised ``lift`` along the normal, and the
        rotation that turns an object's -Y toward that normal."""
        loc, nor, _, _ = self.tree.ray_cast(Vector((x, -1.0, z)), Vector((0, 1, 0)))
        return loc + nor * lift, nor.to_track_quat("-Y", "Z").to_euler()

    def cast(self, origin, direction, lift=0.0):
        """The first point hit from ``origin`` along ``direction``, raised ``lift`` off the surface."""
        loc, nor, _, _ = self.tree.ray_cast(Vector(origin), Vector(direction).normalized())
        return loc + nor * lift


def subdivide(o, levels=1):
    s = o.modifiers.new("Subsurf", "SUBSURF")
    s.levels = levels
    s.render_levels = levels
    apply_all(o)
    return o
