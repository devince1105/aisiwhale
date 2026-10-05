# Clean low-poly parts with planned UVs, each painted on a canvas of its own; the canvases are
# packed onto one atlas and the parts joined into the game mesh (D-198). Needs lib.py (reset, rig).
# Blender: Z up, the figure faces -Y, her left is +X.
import bpy, bmesh, math
import numpy as np
from mathutils import Euler, Vector


def smooth(e0, e1, x):
    k = min(1.0, max(0.0, (x - e0) / (e1 - e0)))
    return k * k * (3 - 2 * k)


def smooth_np(e0, e1, x):
    """``smooth`` over an array."""
    k = np.clip((x - e0) / (e1 - e0), 0, 1)
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
    front first (rx is the front-back radius, ry the vertical one), so u = 0.5 is the top. "XZ": around
    Y (along a foot), from underneath toward her right first (rx across, ry vertical); u = 0.5 is the top."""
    cx, cy, cz = center
    pts = []
    for k in range(seg):
        a = 2 * math.pi * k / seg
        s, c = _se(math.sin(a), power), _se(math.cos(a), power)
        if plane == "XY":
            pts.append(Vector((cx - s * rx, cy + c * ry, cz)))
        elif plane == "YZ":
            pts.append(Vector((cx, cy - s * rx, cz - c * ry)))
        else:
            pts.append(Vector((cx - s * rx, cy, cz - c * ry)))
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


def ellipsoid(name, center, radii, seg=8, rings=5, power=2.0):
    """An ellipsoid; a ``power`` above 2 squares it off toward a rounded box (pouches, holsters)."""
    cx, cy, cz = center
    rows = []
    for j in range(1, rings):
        a = math.pi * j / rings
        c, s = _se(math.cos(a), power), _se(math.sin(a), power)
        rows.append(ring((cx, cy, cz - radii[2] * c), radii[0] * s, radii[1] * s, seg, power=power))
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


def turn(o, pivot, euler):
    """Rotate a part about a point (an Euler in radians)."""
    pivot = Vector(pivot)
    m = Euler(euler).to_matrix()
    for v in o.data.vertices:
        v.co = pivot + m @ (v.co - pivot)
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


# ---- an Animal Crossing head ------------------------------------------------------------------------
HEAD_Y = 0.02           # the head's centre line, a little behind the neck bone
HEAD_PIVOT = (0, HEAD_Y, 0.345)
FACE_BOX = (-0.115, 0.335, 0.23, 0.29)          # the face canvas on the front of the head: x0, z0, width, height
FACE_COLORS = {"line": "#46302A", "iris": "#5E4336", "white": "#FAF4EF", "lid": "#F2AD9C", "brow": "#5A3E32",
               "blush": "#F4A090", "hatch": "#EE8F84", "mouth": "#6E3A28"}


HEAD_PROFILE = [(0.350, .066, .070, 2.6), (0.360, .087, .091, 2.6), (0.378, .098, .101, 2.5), (0.400, .1015, .104, 2.4),
                (0.425, .102, .105, 2.35), (0.455, .100, .104, 2.35), (0.490, .095, .100, 2.35), (0.520, .088, .093, 2.35),
                (0.548, .074, .079, 2.35), (0.568, .050, .054, 2.35)]


def ac_head(skin, ppm=3400, seg=24, rings=None):
    """The head: rounder than a ball, with a wide jaw and a flat soft chin, from the chin at 0.345 to
    the crown at 0.58. Returns the object and its face canvas, whose coordinates are the head's
    (x across, z up) less FACE_BOX's corner: paint at (x - x0, z - z0). The back of the head is
    unrolled into the canvas' top strip, so it shades with the rest. ``seg`` and ``rings`` (the
    profile resampled to that many rings) make it rounder for a bigger budget."""
    profile = HEAD_PROFILE
    if rings:
        zs = [p[0] for p in HEAD_PROFILE]
        z_new = np.linspace(zs[0], zs[-1], rings)
        profile = [(z, *(float(np.interp(z, zs, [p[k] for p in HEAD_PROFILE])) for k in (1, 2, 3))) for z in z_new]
    head = surface("head", [ring((0, HEAD_Y, z), rx, ry, seg, power=p) for z, rx, ry, p in profile],
                   start=(0, HEAD_Y, 0.345), end=(0, HEAD_Y, 0.580))
    x0, z0, w, h = FACE_BOX
    planar_front(head, x0, z0, w, h, wrap=(0.83, 0.99))
    return head, Canvas("face", w, h, ppm, skin)


def ac_face(face, eye_x=0.055, eye_z=0.437, gaze=0.0070, brows=(True, True), colors=None):
    """Paint an Animal Crossing face: per eye a round white ringed in dark brown - heavy over the
    top, fine underneath - with a tall iris pushed toward her left by ``gaze`` (so a crescent of white
    shows on her right of it), two thick lashes at the outer corner and a blush of pink over the lid;
    thin arched brows (``brows``: her right, her left), hatched blush on the cheeks, a smile."""
    c = dict(FACE_COLORS, **(colors or {}))
    x0, z0, _, _ = FACE_BOX
    fx, fz = (lambda x: x - x0), (lambda z: z - z0)
    a, b = 0.0235, 0.0232
    for s, brow in ((1, brows[1]), (-1, brows[0])):
        cx, cz = s * eye_x, eye_z
        X, Y = face.X - fx(cx), face.Y - fz(cz)
        e = face.ellipse(fx(cx), fz(cz), a, b)
        ang = np.degrees(np.arctan2(Y / b, X / a)) % 360       # 0 = toward her left, 90 = up
        face.put(c["lid"], 0.55 * np.clip(np.sin(np.radians(ang)), 0, 1) ** 0.8 * np.clip(1 - e / 0.0065, 0, 1) * (e > 0))
        face.fill(c["white"], e)
        iris = np.maximum(face.ellipse(fx(cx + gaze), fz(cz - 0.0005), 0.0152, 0.0222), e)
        face.fill(c["iris"], iris)
        face.put(c["line"], 0.35 * face.cover(iris) * np.clip(Y / b, 0, 1))          # the lid's shadow on the iris
        t = np.interp(ang, [0, 45, 90, 135, 180, 215, 250, 270, 315, 360],
                      [0.0011, 0.0022, 0.0027, 0.0027, 0.0024, 0.0016, 0.0008, 0.0005, 0.0006, 0.0011])
        face.fill(c["line"], np.abs(e) - t)
        for at, tilt, length in ((36, 26, 0.0115), (9, -8, 0.0075)):
            th = math.radians(at if s > 0 else 180 - at)
            d = math.radians(tilt if s > 0 else 180 - tilt)
            bx, bz = fx(cx) + a * math.cos(th), fz(cz) + b * math.sin(th)
            face.fill(c["line"], face.stroke([(bx - math.cos(d) * 0.003, bz - math.sin(d) * 0.003),
                                              (bx + math.cos(d) * length, bz + math.sin(d) * length)], 0.0023, 0.0009))
        if brow:
            face.fill(c["brow"], face.stroke([(fx(cx - 0.0165), fz(cz + 0.0375)), (fx(cx), fz(cz + 0.0425)),
                                              (fx(cx + 0.0165), fz(cz + 0.039))], 0.0014, 0.0015, 0.0027))
        bx, bz = fx(s * (eye_x + 0.019)), fz(eye_z - 0.045)
        face.put(c["blush"], 0.5 * np.clip(1 - np.hypot((face.X - bx) / 0.021, (face.Y - bz) / 0.012), 0, 1) ** 1.3)
        for k in (-1, 0, 1):
            hx = bx + k * 0.0068
            face.fill(c["hatch"], face.stroke([(hx - 0.0026, bz - 0.0052), (hx + 0.0026, bz + 0.0052)], 0.0008), alpha=0.7)
    mz = eye_z - 0.0345
    face.fill(c["mouth"], face.stroke([(fx(-0.0245), fz(mz)), (fx(-0.014), fz(mz - 0.009)), (fx(0), fz(mz - 0.0125)),
                                       (fx(0.014), fz(mz - 0.009)), (fx(0.0245), fz(mz))], 0.0019))


def ac_ears(skin, center=(0.110, 0.040, 0.414), radii=(0.034, 0.019, 0.034), weights="head", seg=8, rings=6, soft_fold=False):
    """Round ears standing off the sides of the head, with a fold painted inside - a crisp ring, or with
    ``soft_fold`` just a soft shadow, so the ear reads as a smooth round nub."""
    lobe = Canvas("ear", 0.06, 0.06, 2000, skin)
    if soft_fold:
        fold = lobe.ellipse(0.75 * lobe.width, 0.5 * lobe.height, 0.0060, 0.0150)
        lobe.put("#E3A07F", 0.35 * np.clip(1 - np.abs(fold) / 0.004, 0, 1))
    else:
        lobe.fill("#E6A27C", np.abs(lobe.ellipse(0.75 * lobe.width, 0.5 * lobe.height, 0.0050, 0.0150)) - 0.0012, soft=0.001)
    ear = ellipsoid("ear-l", center, radii, seg, rings)
    part(ear, lobe, weights)
    part(mirror(ear, "ear-r"), lobe, weights)


def ac_nose(z=0.417, color="#F6894B"):
    """A small orange bean of a nose, lighter on top."""
    c = Canvas("nose", 0.03, 0.02, 2000, color)
    c.shade(0.93 + 0.16 * c.Y / c.height)
    part(ellipsoid("nose", (0, HEAD_Y - 0.1055, z), (0.0125, 0.0085, 0.0068), 8, 5), c, "head")


def scale_parts(prefixes, pivot, k):
    """Scale every part whose name starts with one of ``prefixes`` about ``pivot`` - to size the head
    and hair as a whole to the reference."""
    for o, _, _ in PARTS:
        if o.name.split("-")[0] in prefixes:
            scale_about(o, pivot, k)


HEAD_PARTS = ("head", "ear", "earring", "nose", "cap", "fringe", "lock", "mass", "tie", "tail", "bob")


# ---- hair -----------------------------------------------------------------------------------------------
class Hair:
    """One head of hair round a centre: a cap from the crown, locks lying on it, masses hanging from
    under it. Every piece carries strands painted along its length.
    ``flare``: how far the hair stands further out below its middle (over ``flare_depth`` metres);
    ``tuck``: how far it comes back in toward its ends (between ``tuck_from`` and ``tuck_to`` metres
    below the middle) - a bob's ends turn under. ``dome`` above 2 makes the top fuller (a helmet bob)."""

    def __init__(self, center, radii, color, flare=0.13, flare_depth=0.07, tuck=0.0, tuck_from=0.09, tuck_to=0.14, dome=2.0):
        self.c, self.r, self.color, self.dome = Vector(center), Vector(radii), color, dome
        self.flare, self.flare_depth = flare, flare_depth
        self.tuck, self.tuck_from, self.tuck_to = tuck, tuck_from, tuck_to
        self.axis = lambda co: Vector((self.c.x, self.c.y, co.z))

    def scale(self, z):
        """The horizontal scale at a height: an ellipsoid above the middle; below, the flare."""
        k = z - self.c.z
        if k >= 0:
            return max(1e-4, 1 - abs(k / self.r.z) ** self.dome) ** (1 / self.dome)
        return 1 + self.flare * smooth(0, self.flare_depth, -k) - self.tuck * smooth(self.tuck_from, self.tuck_to, -k)

    def on(self, x, z, lift=0.0):
        """The point on the front of the hair's surface at (x, z), ``lift`` off it."""
        rx, ry = self.r.x * self.scale(z) + lift, self.r.y * self.scale(z) + lift
        x = max(-0.995 * rx, min(0.995 * rx, x))
        return Vector((x, self.c.y - ry * math.sqrt(1 - (x / rx) ** 2), z))

    def strands(self, name, o, count, weights, ppm=1100, length=0.2, girth=0.14, seed=0):
        cv = Canvas(name, girth, length, ppm, self.color)
        cv.streaks(count, groove=0.3, drift=0.14, seed=seed)
        cv.shade(1.06 - 0.16 * (cv.Y / cv.height))                         # a little darker toward the ends
        return part(o, cv, weights)

    def cap(self, hem, cols=32, rows=9, rim_depth=0.026, parting=22, ppm=940, seed=3, ridges=None, weights="head",
            grow=(0.15, 0.8), paint_grow=(0.0, 3.0), highlight=0.22, partings=0.55, side_fade=False, parting_color="#231B1E", sweep=0.0,
            crown_shade=(0.45, 0.35)):
        """The cap: columns from the crown, each ending at ``hem(azimuth)`` - azimuth in degrees, 0 the
        front, + toward her left - with an edge ``rim_depth`` thick, and a parting at ``parting``.
        ``ridges`` = (count, depth, clear[, phase]): the hair is sculpted into ``count`` rounded clumps
        around the head, standing out by up to ``depth`` of its radius with sharp partings between,
        growing in from the crown and kept off the front within ``clear`` degrees (the hairline stays
        smooth); ``phase`` (in clumps) turns them round, so a clump's middle can sit at the nape. The
        paint follows the clumps: dark partings, a soft highlight down each, a strand or two in it.
        Tuning (the defaults are what Ada was built with): ``grow`` (polar angle, radians) and
        ``paint_grow`` (start, rate down the canvas) say where the clumps begin below the crown, so they
        do not all meet at its top; ``highlight`` and ``partings`` set the paint's contrast;
        ``side_fade`` keeps the clumps off the hem beside the face; ``sweep`` (in clumps) combs them back
        toward the nape as they fall; the cap's ``weights`` let a curtain down the back follow the torso.
        ``crown_shade`` = (depth, extent): the top of the head is painted darker by up to ``depth``,
        easing off over the top ``extent`` of the canvas. The office lights a crown from straight above
        with its key, its sky and its ceiling panels at once; unshaded, dark hair there reads as a bald
        patch (D-201)."""
        c, r = self.c, self.r

        def bulge(az, ph, f=0.0):
            if not ridges:
                return 1.0
            count, depth, clear, phase = (tuple(ridges) + (0.0,))[:4]
            u = ((az + 180) / 360 * count + phase + sweep * (1 - math.cos(math.radians(az))) / 2 * smooth(0.3, 1.0, f)) % 1
            fade = 1 - 0.7 * smooth(0.85, 1.0, f) * (smooth(55, 75, abs(az)) - smooth(100, 110, abs(az))) if side_fade else 1.0
            return 1 + depth * (abs(math.sin(math.pi * u)) ** 0.45 - 0.7) * smooth(grow[0], grow[1], ph) * smooth(clear, clear + 30, abs(az)) * fade

        polar = lambda z: math.acos(min(1, (z - c.z) / r.z)) if z >= c.z else math.pi / 2 + (c.z - z) / r.z
        height = lambda ph: c.z + r.z * math.cos(ph) if ph <= math.pi / 2 else c.z - (ph - math.pi / 2) * r.z
        grid = []
        for j in range(1, rows + 1):
            row = []
            for i in range(cols):
                az = -180 + 360 * i / cols
                ph = polar(hem(az)) * j / rows
                z = height(ph)
                a = math.radians(az)
                k = self.scale(z) * bulge(az, ph, j / rows)
                row.append(Vector((c.x + r.x * k * math.sin(a), c.y - r.y * k * math.cos(a), z)))
            grid.append(row)
        cap = surface("cap", grid, start=(c.x, c.y, c.z + r.z), inside=c)
        rim(cap, rim_depth, self.axis)
        crown = Canvas("cap", 2 * math.pi * r.x, 0.30, ppm, self.color)
        if ridges:
            count, phase = ridges[0], (tuple(ridges) + (0.0,))[3]
            crown.streaks(count * 2, groove=0.15, drift=0.10, seed=seed)
            tt = np.clip((crown.Y / crown.height - 0.3) / 0.7, 0, 1)
            sw = sweep * (1 - np.cos(np.radians(crown.X / crown.width * 360 - 180))) / 2 * tt * tt * (3 - 2 * tt)
            u = (crown.X / crown.width * count + phase + sw) % 1
            g = np.clip((crown.Y / crown.height - paint_grow[0]) * paint_grow[1], 0, 1)
            crown.shade(1 - partings * (1 - np.abs(np.sin(np.pi * u)) ** 0.15) * g)          # the partings
            crown.shade(1 + highlight * np.exp(-((u - 0.5) / 0.16) ** 2) * g)                # a highlight down each clump
        else:
            crown.streaks(72, groove=0.3, drift=0.14, seed=seed)
        if crown_shade:
            depth, extent = crown_shade
            crown.shade(1 - depth * (1 - smooth_np(0.0, extent, crown.Y / crown.height)))
        if parting is not None:
            px = (0.5 + parting / 360) * crown.width
            crown.fill(parting_color, np.maximum(crown.column(px - 0.0012, px + 0.0012), 0.03 - crown.Y), alpha=0.85)
        return part(cap, crown, weights)

    def blade(self, name, pts, widths, thicks, seed, weights="head", seg=6, steps=3, strands=None):
        """A lock lying on the hair: ``pts`` are (x, z) on the front of the head, or full positions.
        ``strands``: how many strands to paint on it (by default one per 7 mm of its width)."""
        path = [Vector(p) if len(p) == 3 else self.on(p[0], p[1], thicks[min(i, len(thicks) - 1)] / 2 - 0.006)
                for i, p in enumerate(pts)]
        o = sweep(name, path, widths, thicks, self.c, seg=seg, steps=steps)
        count = strands or max(4, int(max(widths) / 0.007))
        return self.strands(name, o, count, weights, length=0.16, girth=2.2 * max(widths), seed=seed)

    def mass(self, name, path, widths, thicks, count, weights, length, girth, seed, tip=True):
        """A heavy lock hanging from under the cap."""
        return self.strands(name, sweep(name, path, widths, thicks, self.axis, seg=10, tip=tip), count, weights,
                            length=length, girth=girth, seed=seed)


def hang(z0, z1):
    """Weights for hair that hangs past the neck: the head's above z1, the torso's below z0."""
    return lambda co: {"head": smooth(z0, z1, co.z), "torso": 1 - smooth(z0, z1, co.z)}


# ---- straps, bands and buckles that stand off the body (the 9999 versions, D-200) ------------------------
def on_profile(profile, deg, z, lift=0.0, bulge=None):
    """The point on a lofted part's surface at azimuth ``deg`` (0 the front, + toward her left) and
    height z, ``lift`` off it; ``profile`` rows are (z, rx, ry, cy), the part centred on x = 0. A part
    whose rings were pushed out by ``bulge(deg, z)`` along this normal (see ``bulged_rings``) passes
    the same function, so what lies on it follows."""
    zs = [p[0] for p in profile]
    rx, ry, cy = (float(np.interp(z, zs, [p[k] for p in profile])) for k in (1, 2, 3))
    d = math.radians(deg)
    n = Vector((math.sin(d) / rx, -math.cos(d) / ry, 0)).normalized()
    return Vector((math.sin(d) * rx, cy - math.cos(d) * ry, z)) + n * (lift + (bulge(deg, z) if bulge else 0.0))


def bulged_rings(profile, seg, bulge):
    """The rings of a lofted part (rows (z, rx, ry, cy), centred on x = 0), each point pushed out by
    ``bulge(deg, z)`` metres along its normal - a bust, say."""
    rows = []
    for z, rx, ry, cy in profile:
        row = ring((0, cy, z), rx, ry, seg)
        for k, p in enumerate(row):
            deg = 360 * k / seg - 180                    # ring() starts at the back
            d = math.radians(deg)
            n = Vector((math.sin(d) / rx, -math.cos(d) / ry, 0)).normalized()
            p += n * bulge(deg, z)
        rows.append(row)
    return rows


def strap_canvas(color, stitch):
    """Leather strap: rounded edges, a stitched line down each side."""
    c = Canvas("strap", 0.03, 0.30, 1400, color)
    c.shade(0.80 + 0.35 * np.abs(np.sin(np.pi * c.X / c.width)) ** 0.5)
    for u in (0.30, 0.70):
        c.fill(stitch, np.maximum(c.column(u * c.width - 0.0003, u * c.width + 0.0003), np.sin(c.Y / 0.0016 * math.pi) - 0.2), alpha=0.6)
    return c


def flat_strap(name, pts, profile, toward, canvas, width=0.011, thick=0.0018, lift=0.0008, weights="torso", bulge=None):
    """A flat strap lying on a lofted part through (deg, z) points, its broad face turned away from the
    point ``toward`` (inside the body: outward round it, up over a shoulder)."""
    path = []
    for d, z in pts:
        p = on_profile(profile, d, z, bulge=bulge)
        path.append(p + (p - toward).normalized() * (lift + thick / 2))
    o = sweep(name, path, [width] * len(path), [thick] * len(path), toward, seg=6, steps=2, tip=False)
    return part(o, canvas, weights)


def buckle_canvas(metal, dark, strap, shine="#C9C4C8"):
    """A square frame buckle with its prong, painted round a box whose front face is the middle quarter
    of the canvas (u 0.385-0.615)."""
    c = Canvas("buckle", 0.04, 0.02, 1600, dark)
    box_d = lambda a, b: np.maximum(np.abs(c.X / c.width - 0.5) - a, np.abs(c.Y / c.height - 0.5) - b)
    c.fill(metal, box_d(0.105, 0.40) * c.width)                  # the frame
    c.fill(strap, box_d(0.060, 0.22) * c.width)                  # its opening, the strap behind
    c.fill(metal, box_d(0.006, 0.22) * c.width)                  # the prong
    c.put(shine, 0.6 * np.exp(-((c.Y / c.height - 0.78) / 0.06) ** 2) * (box_d(0.105, 0.40) < 0) * (box_d(0.060, 0.22) > 0))
    return c


def frame_buckle(name, at, deg, canvas, size=(0.0060, 0.0010, 0.0068), weights="torso", tilt=(0.0, 0.0), seg=12):
    """A square frame buckle at ``at``, facing out at azimuth ``deg`` (and tipped by ``tilt``, radians
    about x then y, for one on an arm or a slope)."""
    o = ellipsoid(name, at, size, seg, 4, power=8)
    return part(turn(o, at, (tilt[0], tilt[1], math.radians(deg))), canvas, weights)


def wrap_band(name, center, radius, t0, t1, seg=16, plane="XY", squash=1.0, rise=0.0016):
    """A band round a part from t0 to t1 along its axis (z for "XY", x for "YZ"), standing ``rise``
    off ``radius(t)`` with rounded edges; ``center`` is the axis' other two coordinates."""
    rows = []
    for t, k in ((t0, 0.0004), (t0 + 0.0008, rise), (t1 - 0.0008, rise), (t1, 0.0004)):
        r = radius(t) + k
        at = (center[0], center[1], t) if plane == "XY" else (t, center[0], center[1])
        rows.append(ring(at, r, r * squash, seg, plane=plane))
    return surface(name, rows)


# ---- arms that bend (D-201) --------------------------------------------------------------------------------
# The pack's arm bones pivot 5 cm out from where these figures' shoulders are, and have no elbow: its sit
# clip swings the arm 45 degrees down and out, so the long straight arm stuck out like a wing. The arm
# bones are moved to the shoulder and given a forearm bone at the elbow, which no clip moves; the office
# bends it (AvatarController).
SHOULDER_X, ELBOW_X, ARM_Y, ARM_Z = 0.058, 0.086, 0.017, 0.292


def fit_arms(shoulder_x=SHOULDER_X, elbow_x=ELBOW_X, y=ARM_Y, z=ARM_Z):
    """Move the rig's arm pivots to the shoulders and add a forearm bone at each elbow, oriented as the
    arm bones are (so a clip's rotations mean the same)."""
    arm = rig()
    bpy.ops.object.select_all(action="DESELECT")
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    bones = arm.data.edit_bones
    for s, side in ((1, "left"), (-1, "right")):
        upper = bones[f"arm-{side}"]
        length, roll = upper.length, upper.roll
        upper.head = (s * shoulder_x, y, z)
        upper.tail = (s * shoulder_x, y, z + length)
        upper.roll = roll
        fore = bones.new(f"forearm-{side}")
        fore.head = (s * elbow_x, y, z)
        fore.tail = (s * elbow_x, y, z + length)
        fore.roll = roll
        fore.parent = upper
        fore.use_connect = False
    bpy.ops.object.mode_set(mode="OBJECT")


def arm_weights(side, shoulder=(0.050, 0.066), elbow=(ELBOW_X - 0.008, ELBOW_X + 0.004)):
    """Weights along an arm (the rest pose's x): the torso's at the body, the arm's past the shoulder,
    the forearm's past the elbow, each blending into the next."""
    def weights(co):
        x = abs(co.x)
        a, f = smooth(*shoulder, x), smooth(*elbow, x)
        return {"torso": 1 - a, f"arm-{side}": a * (1 - f), f"forearm-{side}": a * f}
    return weights


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
    nodes = []
    for m in o.data.materials:              # every material bakes into the same image
        node = m.node_tree.nodes.new("ShaderNodeTexImage")
        node.image = img
        m.node_tree.nodes.active = node
        nodes.append((m.node_tree, node))
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.bake(type="AO", margin=margin, use_clear=False)
    a = np.array(img.pixels[:], dtype=np.float32).reshape(size, size, 4)[..., 0]
    a = sum(np.roll(np.roll(a, i, 0), j, 1) for i in (-1, 0, 1) for j in (-1, 0, 1)) / 9      # take the grain off
    for nt, node in nodes:
        nt.nodes.remove(node)
    bpy.data.images.remove(img)
    sc.render.engine = engine
    return a


HAIR_PARTS = ("cap", "fringe", "lock", "mass", "tail")


def _material(name, matte):
    """The figure's material; a matte one has no specular at all (glTF KHR_materials_specular 0): the
    office's light panels would otherwise shine on the top of dark hair like a bald crown (D-201)."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.use_backface_culling = False       # the skirt and the hair's hems are single sheets
    bsdf = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Roughness"].default_value = 1.0 if matte else 0.85
    if matte:
        bsdf.inputs["Specular IOR Level"].default_value = 0.0
    return m


def assemble(name, size=2048, pad=8, occlusion=0.42, occlusion_size=1024, samples=48, fade_face_seam=False, matte=HAIR_PARTS):
    """Pack the canvases, join the parts into one mesh on the rig, and multiply the mesh's own
    (warm-tinted) ambient occlusion into the paint: the soft shadow under the fringe, the chin, the
    skirt. Two materials share the one atlas: the parts named in ``matte`` (by the name before its
    first "-") get the matte one."""
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
        flag = 1 if o.name.split("-")[0] in matte else 0
        o.data.attributes.new("matte", "INT", "FACE").data.foreach_set("value", [flag] * len(o.data.polygons))
    print("parts", ", ".join(f"{o.name} {sum(len(p.vertices) - 2 for p in o.data.polygons)}" for o, _, _ in PARTS))
    bpy.ops.object.select_all(action="DESELECT")
    for o, _, _ in PARTS:
        o.select_set(True)
    bpy.context.view_layer.objects.active = PARTS[0][0]
    bpy.ops.object.join()
    mesh = bpy.context.view_layer.objects.active
    mesh.name = mesh.data.name = name + "-mesh"
    PARTS.clear()

    mesh.data.materials.clear()
    materials = [_material(name, False), _material(name + "-matte", True)]
    for m in materials:
        mesh.data.materials.append(m)
    flags = [0] * len(mesh.data.polygons)
    mesh.data.attributes["matte"].data.foreach_get("value", flags)
    mesh.data.polygons.foreach_set("material_index", flags)
    mesh.data.attributes.remove(mesh.data.attributes["matte"])
    if occlusion:
        ao = _bake_occlusion(mesh, occlusion_size, samples, pad * occlusion_size // size)
        k = size // occlusion_size
        dark = occlusion * (1 - np.repeat(np.repeat(ao, k, axis=0), k, axis=1))[..., None]
        face = next((c for c in canvases if c.name == "face"), None)
        if fade_face_seam and face is not None:
            # the head's projected front and its wrapped back meet in a seam the occlusion would draw:
            # fade it out toward the projection's edge and off the wrapped strip
            ramp = lambda e0, e1, t: (lambda q: q * q * (3 - 2 * q))(np.clip((t - e0) / (e1 - e0), 0, 1))
            keep = (1 - ramp(0.080, 0.095, np.abs(face.X + FACE_BOX[0]))) * ramp(0.020, 0.032, face.Y) * (face.Y < 0.83 * face.height)
            x, y = rects[face.name]
            dark[y:y + face.h, x:x + face.w, 0] *= keep.astype(np.float32)
        atlas = atlas * (1 - dark * np.array([0.7, 1.0, 1.1], dtype=np.float32))      # warm shadows, as on skin
    img = bpy.data.images.new(name, size, size, alpha=False)
    img.pixels[:] = np.concatenate([np.clip(atlas, 0, 1), np.ones((size, size, 1), dtype=np.float32)], axis=2).ravel()
    img.file_format = "PNG"
    img.pack()
    for m in materials:
        nt = m.node_tree
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = img
        nt.links.new(tex.outputs["Color"], next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED").inputs["Base Color"])
    mesh.parent = arm
    mesh.modifiers.new("Armature", "ARMATURE").object = arm
    print("triangles", sum(len(p.vertices) - 2 for p in mesh.data.polygons))
    return mesh
