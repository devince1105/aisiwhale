# Clean low-poly parts with planned UVs, each painted on a canvas of its own; the canvases are
# packed onto one atlas and the parts joined into the game mesh (D-198). Needs lib.py (reset, rig).
# Blender: Z up, the figure faces -Y, her left is +X.
import bpy, bmesh, math
import numpy as np
from mathutils import Vector


def smooth(e0, e1, x):
    k = min(1.0, max(0.0, (x - e0) / (e1 - e0)))
    return k * k * (3 - 2 * k)


def srgb(hexcolor):
    h = hexcolor.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)], dtype=np.float32)


# ---- painting ---------------------------------------------------------------------------------------
class Canvas:
    """One part's texture, painted in metres (x across = u, y up = v) in display colours. Shapes are
    signed distances (negative inside), drawn anti-aliased; ``soft`` widens an edge into an airbrush."""

    def __init__(self, name, width, height, ppm, base):
        self.name, self.width, self.height = name, width, height
        self.w, self.h = max(8, int(round(width * ppm))), max(8, int(round(height * ppm)))
        self.px = width / self.w
        self.X, self.Y = np.meshgrid((np.arange(self.w) + 0.5) * width / self.w, (np.arange(self.h) + 0.5) * height / self.h)
        self.rgb = np.empty((self.h, self.w, 3), dtype=np.float32)
        self.rgb[:] = srgb(base)

    def cover(self, d, soft=0.0):
        return np.clip(0.5 - d / (self.px + soft), 0, 1)

    def put(self, color, alpha):
        a = np.asarray(alpha, dtype=np.float32)[..., None]
        self.rgb = self.rgb * (1 - a) + srgb(color) * a

    def fill(self, color, d, alpha=1.0, soft=0.0):
        self.put(color, alpha * self.cover(d, soft))

    def shade(self, factor):
        self.rgb = np.clip(self.rgb * np.asarray(factor, dtype=np.float32)[..., None], 0, 1)

    def ellipse(self, cx, cy, a, b):
        dx, dy = self.X - cx, self.Y - cy
        k = np.sqrt((dx / a) ** 2 + (dy / b) ** 2) + 1e-9
        return (k - 1) / (np.sqrt((dx / a ** 2) ** 2 + (dy / b ** 2) ** 2) / k + 1e-9)

    def box(self, x0, y0, x1, y1, r=0.0):
        qx = np.abs(self.X - (x0 + x1) / 2) - ((x1 - x0) / 2 - r)
        qy = np.abs(self.Y - (y0 + y1) / 2) - ((y1 - y0) / 2 - r)
        return np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r

    def band(self, y0, y1):
        return np.maximum(y0 - self.Y, self.Y - y1)

    def column(self, x0, x1):
        return np.maximum(x0 - self.X, self.X - x1)

    def stroke(self, pts, r0, r1=None, rmid=None, samples=40):
        """A smooth line through ``pts`` whose radius runs r0 -> (rmid) -> r1."""
        r1 = r0 if r1 is None else r1
        P = [np.array(p, dtype=np.float64) for p in pts]
        curve = []
        for i in range(len(P) - 1):
            p0, p1, p2, p3 = P[max(i - 1, 0)], P[i], P[i + 1], P[min(i + 2, len(P) - 1)]
            n = max(2, samples // (len(P) - 1))
            for k in range(n):
                t = k / n
                curve.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
        curve.append(P[-1])
        d = np.full(self.X.shape, 1e3)
        # only the pixels near the line are worth computing
        rmax = max(r0, r1, rmid or 0) + 4 * self.px
        xs, ys = [c[0] for c in curve], [c[1] for c in curve]
        i0, i1 = max(0, int((min(xs) - rmax) / self.px)), min(self.w, int((max(xs) + rmax) / self.px) + 1)
        j0, j1 = max(0, int((min(ys) - rmax) / self.px)), min(self.h, int((max(ys) + rmax) / self.px) + 1)
        if i0 >= i1 or j0 >= j1:
            return d
        X, Y = self.X[j0:j1, i0:i1], self.Y[j0:j1, i0:i1]
        w = np.full(X.shape, 1e3)
        m = len(curve) - 1
        for i in range(m):
            a, b = curve[i], curve[i + 1]
            ab = b - a
            t = np.clip(((X - a[0]) * ab[0] + (Y - a[1]) * ab[1]) / max(ab @ ab, 1e-12), 0, 1)
            u = (i + t) / m
            r = r0 + (r1 - r0) * u if rmid is None else np.where(u < 0.5, r0 + (rmid - r0) * u * 2, rmid + (r1 - rmid) * (u - 0.5) * 2)
            w = np.minimum(w, np.hypot(X - (a[0] + ab[0] * t), Y - (a[1] + ab[1] * t)) - r)
        d[j0:j1, i0:i1] = w
        return d

    def streaks(self, count, groove=0.22, drift=0.10, seed=0):
        """Hair: strands running up the canvas - a dark groove between each of ``count`` strands and a
        slow drift of light and dark across them. ``count`` whole strands, so a closed part tiles."""
        rng = np.random.default_rng(seed)
        u = self.X / self.width
        g = np.abs(np.sin(np.pi * u * count)) ** 0.4
        fine = 0.5 + 0.5 * np.sin(2 * np.pi * (u * count * 3 + rng.uniform()))
        slow = sum(rng.uniform(0.5, 1) * np.sin(2 * np.pi * (k * u + rng.uniform())) for k in (2, 3, 5, 9)) / 3
        self.shade((1 - groove * (1 - g)) * (1 - 0.05 * fine) * (1 + drift * slow))


def along(o, params, cv):
    """For a lofted part: the canvas' y of a ring parameter (its z, or its x along an arm), and that
    parameter at every pixel."""
    vs = [float(v) for v in o["v"]]
    return (lambda p: float(np.interp(p, params, vs)) * cv.height), np.interp(cv.Y / cv.height, vs, params)


# ---- meshes -------------------------------------------------------------------------------------------
def _se(t, power):
    return math.copysign(abs(t) ** (2.0 / power), t)


def ring(center, rx, ry, seg, plane="XY", power=2.0):
    """A superellipse of points. "XY": around Z, from the back toward her right first, so u = 0.5 is the
    front and the texture reads as seen from the front. "YZ": around X, from underneath toward the
    front first (rx is the front-back radius, ry the vertical one), so u = 0.5 is the top."""
    cx, cy, cz = center
    pts = []
    for k in range(seg):
        a = 2 * math.pi * k / seg
        s, c = _se(math.sin(a), power), _se(math.cos(a), power)
        pts.append(Vector((cx - s * rx, cy + c * ry, cz)) if plane == "XY" else Vector((cx, cy - s * rx, cz - c * ry)))
    return pts


def _object(name, bm):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    return o


def surface(name, rows, closed=True, start=None, end=None, inside=None):
    """A clean quad surface through ``rows`` (rings of equal length), optionally closed around and
    capped by a fan to the points ``start`` / ``end``. UVs: u around (or across), v along, measured by
    the mean distance between rows. Faces look away from ``inside`` (default: the centroid)."""
    n = len(rows[0])
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    V = [[bm.verts.new(p) for p in row] for row in rows]
    mean = lambda a, b: sum((Vector(q) - Vector(p)).length for p, q in zip(a, b)) / n
    d0 = mean(rows[0], [start] * n) if start is not None else 0.0
    d1 = mean(rows[-1], [end] * n) if end is not None else 0.0
    dist = [0.0]
    for a, b in zip(rows, rows[1:]):
        dist.append(dist[-1] + mean(a, b))
    total = (d0 + dist[-1] + d1) or 1.0
    vs = [(d0 + d) / total for d in dist]
    span = n if closed else n - 1
    us = [i / span for i in range(span + 1)]

    def face(verts, uvs):
        f = bm.faces.new(verts)
        for l, t in zip(f.loops, uvs):
            l[uvl].uv = t

    for j in range(len(rows) - 1):
        for i in range(span):
            k = (i + 1) % n
            face((V[j][i], V[j][k], V[j + 1][k], V[j + 1][i]),
                 ((us[i], vs[j]), (us[i + 1], vs[j]), (us[i + 1], vs[j + 1]), (us[i], vs[j + 1])))
    if start is not None:
        t = bm.verts.new(start)
        for i in range(span):
            k = (i + 1) % n
            face((t, V[0][k], V[0][i]), (((us[i] + us[i + 1]) / 2, 0.0), (us[i + 1], vs[0]), (us[i], vs[0])))
    if end is not None:
        t = bm.verts.new(end)
        for i in range(span):
            k = (i + 1) % n
            face((t, V[-1][i], V[-1][k]), (((us[i] + us[i + 1]) / 2, 1.0), (us[i], vs[-1]), (us[i + 1], vs[-1])))
    bm.normal_update()
    c = Vector(inside) if inside is not None else sum((v.co for v in bm.verts), Vector()) / len(bm.verts)
    if sum(f.normal.dot(f.calc_center_median() - c) * f.calc_area() for f in bm.faces) < 0:
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    o = _object(name, bm)
    o["v"] = vs
    return o


def ellipsoid(name, center, radii, seg=8, rings=5):
    cx, cy, cz = center
    rows = []
    for j in range(1, rings):
        a = math.pi * j / rings
        rows.append(ring((cx, cy, cz - radii[2] * math.cos(a)), radii[0] * math.sin(a), radii[1] * math.sin(a), seg))
    return surface(name, rows, start=(cx, cy, cz - radii[2]), end=(cx, cy, cz + radii[2]))


def sweep(name, path, widths, thicks, out_from, seg=8, steps=3, tip=True):
    """A lock of hair: a flattened tube along ``path``, ``widths[i]`` across and ``thicks[i]`` deep at
    each path point, its broad side facing away from the point (or function of a position)
    ``out_from``. Rounded at the root, pointed at the end unless ``tip`` is False."""
    P = [Vector(p) for p in path]
    knots, ts = [], []
    for i in range(len(P) - 1):
        p0, p1, p2, p3 = P[max(i - 1, 0)], P[i], P[i + 1], P[min(i + 2, len(P) - 1)]
        for k in range(steps):
            t = k / steps
            knots.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
            ts.append(i + t)
    knots.append(P[-1])
    ts.append(len(P) - 1)
    n = len(knots)
    idx = list(range(len(P)))
    rows = []
    for i, c in enumerate(knots[:-1] if tip else knots):
        tan = (knots[min(i + 1, n - 1)] - knots[max(i - 1, 0)]).normalized()
        f = out_from(c) if callable(out_from) else Vector(out_from)
        out = c - f
        out = (out - tan * out.dot(tan)).normalized()
        side = tan.cross(out).normalized()
        w, d = float(np.interp(ts[i], idx, widths)) / 2, float(np.interp(ts[i], idx, thicks)) / 2
        rows.append([c + side * (w * math.cos(a)) + out * (d * math.sin(a)) for a in (2 * math.pi * k / seg for k in range(seg))])
    return surface(name, rows, start=knots[0], end=knots[-1] if tip else knots[-1])


def scale_about(o, pivot, k):
    """Scale a part about a point (to size the whole head, say, without re-deriving its numbers)."""
    pivot = Vector(pivot)
    for v in o.data.vertices:
        v.co = pivot + (v.co - pivot) * k
    return o


def mirror(o, name):
    """The same part on her other side: mirrored across X, sharing the canvas."""
    me = o.data.copy()
    me.name = name
    bm = bmesh.new()
    bm.from_mesh(me)
    for v in bm.verts:
        v.co.x = -v.co.x
    bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    bm.to_mesh(me)
    bm.free()
    m = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(m)
    m["v"] = o["v"]
    return m


def rim(o, depth, toward):
    """Give an open shell an edge with thickness: its boundary is extruded ``depth`` toward the point
    (or function of a position) ``toward``."""
    bm = bmesh.new()
    bm.from_mesh(o.data)
    uv = bm.loops.layers.uv.verify()
    edges = [e for e in bm.edges if e.is_boundary]
    uv_of = {}
    for e in edges:
        for l in e.link_loops:
            uv_of[l.vert] = l[uv].uv.copy()
            uv_of[l.link_loop_next.vert] = l.link_loop_next[uv].uv.copy()
    key = lambda co: (round(co.x, 6), round(co.y, 6), round(co.z, 6))
    orig = {key(v.co): v for v in uv_of}
    new = bmesh.ops.extrude_edge_only(bm, edges=edges)["geom"]
    src = {v: orig[key(v.co)] for v in new if isinstance(v, bmesh.types.BMVert)}
    for f in (g for g in new if isinstance(g, bmesh.types.BMFace)):
        f.smooth = True
        for l in f.loops:
            l[uv].uv = uv_of[src.get(l.vert, l.vert)]
    for v in src:
        t = toward(v.co) if callable(toward) else Vector(toward)
        v.co += (t - v.co).normalized() * depth
    bm.to_mesh(o.data)
    bm.free()
    return o


def planar_front(o, x0, z0, width, height, wrap, limit=-0.2):
    """UVs for a head: faces looking forward are projected flat from the front onto the canvas (its
    lower-left at x0, z0; width x height metres) - what is painted there is what the front view shows.
    The faces turned away, which a flat projection would smear, are unrolled round the head into the
    strip of the canvas between v = wrap[0] and wrap[1], so that they shade with the rest."""
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bm.normal_update()
    uv = bm.loops.layers.uv.verify()
    zs = [v.co.z for v in bm.verts]
    lo, hi = min(zs), max(zs)
    cy = sum(v.co.y for v in bm.verts) / len(bm.verts)
    for f in bm.faces:
        front = f.normal.y < limit
        for l in f.loops:
            co = l.vert.co
            if front:
                l[uv].uv = ((co.x - x0) / width, (co.z - z0) / height)
            else:
                turn = math.atan2(co.x, cy - co.y) / (2 * math.pi) + 0.5
                l[uv].uv = (turn, wrap[0] + (wrap[1] - wrap[0]) * (co.z - lo) / (hi - lo))
    bm.to_mesh(o.data)
    bm.free()
    return o


# ---- the figure -----------------------------------------------------------------------------------------
PARTS = []      # (object, canvas, weights): weights is a bone's name or a function co -> {bone: weight}


def part(o, canvas, weights):
    PARTS.append((o, canvas, weights))
    return o


def _pack(canvases, size, pad):
    """Shelves, tallest first. Returns {canvas name: (x, y)} of each canvas' lower-left pixel."""
    rects, x, y, shelf = {}, pad, pad, 0
    for c in sorted(canvases, key=lambda c: -c.h):
        if x + c.w + pad > size:
            x, y, shelf = pad, y + shelf + 2 * pad, 0
        if y + c.h + pad > size or c.w + 2 * pad > size:
            raise RuntimeError(f"the atlas is full at {c.name}: lower some canvases' resolution")
        rects[c.name] = (x, y)
        x += c.w + 2 * pad
        shelf = max(shelf, c.h)
    print("atlas rows used", y + shelf + pad, "of", size)
    return rects


def _weigh(o, weights):
    o.vertex_groups.clear()
    if isinstance(weights, str):
        o.vertex_groups.new(name=weights).add(list(range(len(o.data.vertices))), 1.0, "REPLACE")
        return
    groups = {}
    for v in o.data.vertices:
        for bone, w in weights(v.co).items():
            if w > 1e-3:
                if bone not in groups:
                    groups[bone] = o.vertex_groups.new(name=bone)
                groups[bone].add([v.index], w, "REPLACE")


def _bake_occlusion(o, size, samples, margin):
    """The mesh's own ambient occlusion in its UVs (white where nothing was baked)."""
    sc = bpy.context.scene
    engine = sc.render.engine
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    img = bpy.data.images.new("occlusion", size, size, alpha=False, float_buffer=True)
    img.colorspace_settings.name = "Non-Color"
    img.pixels[:] = np.ones(size * size * 4, dtype=np.float32)
    nt = o.data.materials[0].node_tree
    node = nt.nodes.new("ShaderNodeTexImage")
    node.image = img
    nt.nodes.active = node
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.bake(type="AO", margin=margin, use_clear=False)
    a = np.array(img.pixels[:], dtype=np.float32).reshape(size, size, 4)[..., 0]
    a = sum(np.roll(np.roll(a, i, 0), j, 1) for i in (-1, 0, 1) for j in (-1, 0, 1)) / 9      # take the grain off
    nt.nodes.remove(node)
    bpy.data.images.remove(img)
    sc.render.engine = engine
    return a


def assemble(name, size=2048, pad=8, occlusion=0.42, occlusion_size=1024, samples=48):
    """Pack the canvases, join the parts into one mesh on the rig with one material, and multiply the
    mesh's own (warm-tinted) ambient occlusion into the paint: the soft shadow under the fringe, the
    chin, the skirt."""
    arm = rig()
    canvases = []
    for _, c, _ in PARTS:
        if c not in canvases:
            canvases.append(c)
    rects = _pack(canvases, size, pad)
    atlas = np.full((size, size, 3), 0.5, dtype=np.float32)
    for c in canvases:
        x, y = rects[c.name]
        atlas[y - pad:y + c.h + pad, x - pad:x + c.w + pad] = np.pad(c.rgb, ((pad, pad), (pad, pad), (0, 0)), mode="edge")
    for o, c, weights in PARTS:
        x, y = rects[c.name]
        bm = bmesh.new()
        bm.from_mesh(o.data)
        uv = bm.loops.layers.uv.verify()
        for f in bm.faces:
            for l in f.loops:
                u, v = l[uv].uv
                l[uv].uv = ((x + min(1, max(0, u)) * c.w) / size, (y + min(1, max(0, v)) * c.h) / size)
        bm.to_mesh(o.data)
        bm.free()
        _weigh(o, weights)
    print("parts", ", ".join(f"{o.name} {sum(len(p.vertices) - 2 for p in o.data.polygons)}" for o, _, _ in PARTS))
    bpy.ops.object.select_all(action="DESELECT")
    for o, _, _ in PARTS:
        o.select_set(True)
    bpy.context.view_layer.objects.active = PARTS[0][0]
    bpy.ops.object.join()
    mesh = bpy.context.view_layer.objects.active
    mesh.name = mesh.data.name = name + "-mesh"
    PARTS.clear()

    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.use_backface_culling = False       # the skirt and the hair's hems are single sheets
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Roughness"].default_value = 0.85
    mesh.data.materials.clear()
    mesh.data.materials.append(m)
    if occlusion:
        ao = _bake_occlusion(mesh, occlusion_size, samples, pad * occlusion_size // size)
        k = size // occlusion_size
        dark = occlusion * (1 - np.repeat(np.repeat(ao, k, axis=0), k, axis=1))[..., None]
        atlas = atlas * (1 - dark * np.array([0.7, 1.0, 1.1], dtype=np.float32))      # warm shadows, as on skin
    img = bpy.data.images.new(name, size, size, alpha=False)
    img.pixels[:] = np.concatenate([np.clip(atlas, 0, 1), np.ones((size, size, 1), dtype=np.float32)], axis=2).ravel()
    img.file_format = "PNG"
    img.pack()
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    mesh.parent = arm
    mesh.modifiers.new("Armature", "ARMATURE").object = arm
    print("triangles", sum(len(p.vertices) - 2 for p in mesh.data.polygons))
    return mesh
