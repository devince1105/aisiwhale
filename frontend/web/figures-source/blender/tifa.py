# Tifa, Animal Crossing style, on the Kenney rig (reference: avatars-source/q/Tifa.jpg).
arm = reset("tifa")

SKIN = mat("skin", "#F9D5BE")
HAIR = mat("hair", "#2B2224", rough=0.6)
WHITE = mat("top", "#F3F1EC")
BLACK = mat("black", "#2C2B31")
DARK = mat("dark", "#1E1D22")
RED = mat("red", "#B42B30", rough=0.55)
SOLE = mat("sole", "#3B2F2F")
METAL = mat("metal", "#B9BAC2", rough=0.35, metal=0.8)
EYE = mat("eye", "#3B2A25", rough=0.3)
SHINE = mat("shine", "#FFFFFF", rough=0.3)
BLUSH = mat("blush", "#F4A9A3")
NOSE = mat("nose", "#F2A27A")
MOUTH = mat("mouth", "#4A2A24")

# ---- head -------------------------------------------------------------------
H = Head((0, 0, 0.49), (0.17, 0.15, 0.15))
ellipsoid("head", H.c, H.r, "head", SKIN, seg=20, rings=10)
tube("neck", (0, 0.01, 0.32), (0, 0.01, 0.36), 0.03, bone="head", material=SKIN)
for s in (1, -1):
    ellipsoid(f"ear{s}", (s * 0.165, 0.005, 0.47), (0.022, 0.02, 0.032), "head", SKIN, seg=8, rings=4)

# face
for s in (1, -1):
    x = s * 0.065
    H.decal(f"eye{s}", x, 0.475, (0.028, 0.006, 0.034), EYE)
    H.decal(f"shine{s}", x + 0.009, 0.488, (0.008, 0.003, 0.009), SHINE, lift=0.008)
    # upper lid with a flick of lashes at the outer corner
    H.curve(f"lid{s}", [(x - s * 0.03, 0.495), (x - s * 0.01, 0.512), (x + s * 0.015, 0.512), (x + s * 0.034, 0.5), (x + s * 0.042, 0.508)], 0.0035, EYE)
    H.curve(f"brow{s}", [(x - s * 0.022, 0.528), (x, 0.535), (x + s * 0.024, 0.53)], 0.003, HAIR)
    H.decal(f"blush{s}", s * 0.105, 0.435, (0.026, 0.002, 0.014), BLUSH, lift=0.002)
H.decal("nose", 0, 0.45, (0.013, 0.01, 0.01), NOSE, lift=0.004)
H.curve("mouth", [(-0.03, 0.418), (-0.016, 0.404), (0, 0.4), (0.016, 0.404), (0.03, 0.418)], 0.003, MOUTH)

# earring, on her left ear
box("earring", (0.172, 0.0, 0.425), (0.008, 0.006, 0.026), "head", METAL, bevel=0)


# hair: a cap open at the face, bangs swept to her right, long hair behind
def strand(name, top, bottom, width, thick=0.016, lift=0.012):
    a, _ = H.surface(*top, lift=lift)
    b, _ = H.surface(*bottom, lift=lift)
    along = (b - a)
    mid = (a + b) / 2
    n = (mid - H.c).normalized()
    z = along.normalized()
    x = n.cross(z).normalized()
    y = z.cross(x)
    rot = Matrix((x, y, z)).transposed().to_euler()
    return ellipsoid(name, mid, (width, thick, along.length / 2 + width * 0.3), "head", HAIR, rot=rot)


def hair_shell(name, center, radii, fringe, bottom, cols=56, rows=10, phi_max=100):
    """One piece of hair: a cap from the crown down. Each column (azimuth t, 0 = the face, + to
    her left) runs down the head to ``fringe(t)`` degrees from the crown over the face, or, beside
    and behind it, past phi_max and straight down to the height ``bottom(t)``."""
    cx, cy, cz = center
    rx, ry, rz = radii
    pm = math.radians(phi_max)

    def at(t, d):
        # d: distance down from the crown, in radians of the sphere and then metres of curtain
        if d <= pm:
            ph = d
            return Vector((cx + rx * math.sin(ph) * math.sin(t), cy - ry * math.sin(ph) * math.cos(t), cz + rz * math.cos(ph)))
        top = at(t, pm)
        drop = d - pm
        back = smooth(110, 180, abs(math.degrees(t)))
        # the long hair narrows as it falls, more so across the back; grooves for the strands
        groove = 1 + 0.02 * math.sin(t * 38) * min(1, drop / 0.04)
        kx = (1 - 0.32 * smooth(0, 0.22, drop) * smooth(95, 135, abs(math.degrees(t)))) * groove
        ky = (1 + 0.04 * drop / 0.1) * groove
        return Vector((cx + (top.x - cx) * kx, cy + (top.y - cy) * ky, top.z - drop))

    def length(t):
        f = fringe(t)
        if f is not None:
            return math.radians(f)
        return pm + max(0.0, (cz + rz * math.cos(pm)) - bottom(t))

    bm = bmesh.new()
    crown = bm.verts.new((cx, cy, cz + rz))
    grid = []
    for i in range(cols):
        t = -math.pi + 2 * math.pi * i / cols
        L = length(t)
        grid.append([bm.verts.new(at(t, L * (j + 1) / rows)) for j in range(rows)])
    for i in range(cols):
        a, b = grid[i], grid[(i + 1) % cols]
        bm.faces.new((crown, a[0], b[0]))
        for j in range(rows - 1):
            bm.faces.new((a[j], a[j + 1], b[j + 1], b[j]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    o = bind(_new(name, bm), "head", HAIR)
    HAIR.use_backface_culling = False  # one sheet, seen from both sides
    return o


def smooth(e0, e1, x):
    k = min(1, max(0, (x - e0) / (e1 - e0)))
    return k * k * (3 - 2 * k)


FACE = math.radians(72)   # the face's half-width, as an azimuth


def fringe(t):
    if abs(t) > math.radians(104):
        return None
    deg = math.degrees(t)
    # swept: lower at her right (t < 0), with little points along the edge
    base = 74 - 7 * deg / 45
    tip = 4.5 * abs(((deg + 6) / 16) % 1 - 0.5) * 2 * (1 - smooth(50, 70, abs(deg)))
    edge = base + tip
    # beside the face the edge drops toward the side curtains
    # beside the face the edge comes down to the top of the ear, then to the curtain behind it
    side = smooth(math.degrees(FACE), 90, abs(deg))
    behind = smooth(94, 104, abs(deg))
    edge = edge + side * (84 - edge)
    return edge + behind * (100 - edge)


def bottom(t):
    a = abs(math.degrees(t))
    return 0.36 - 0.13 * smooth(104, 160, a)


hair_shell("hair", (0, 0.004, 0.5), (0.18, 0.164, 0.168), fringe, bottom)
tube("tail", (0.06, 0.15, 0.26), (0.095, 0.185, 0.11), 0.034, 0.006, bone="head", material=HAIR)
tube("tie", (0.081, 0.171, 0.175), (0.084, 0.174, 0.157), 0.024, bone="head", material=RED)

# ---- torso --------------------------------------------------------------------
ellipsoid("body", (0, 0.02, 0.27), (0.092, 0.07, 0.085), "torso", SKIN, seg=10, rings=5)
ellipsoid("tank", (0, 0.02, 0.288), (0.098, 0.076, 0.072), "torso", WHITE,
          cut=lambda v: v.z < -0.5 or v.z > 0.8)
tube("neckline", (0, 0.02, 0.338), (0, 0.02, 0.344), 0.046, bone="torso", material=BLACK, caps=False)
tube("waist", (0, 0.02, 0.236), (0, 0.02, 0.214), 0.098, bone="torso", material=DARK)
tube("skirt", (0, 0.02, 0.222), (0, 0.02, 0.15), 0.096, 0.145, bone="torso", material=BLACK, seg=32,
     profile=lambda a: 1 + 0.05 * abs(math.sin(a * 8)))
for s in (1, -1):
    x = s * 0.045
    stroke(f"suspender{s}", [(x, -0.09, 0.225), (x, -0.08, 0.31), (s * 0.055, -0.03, 0.352), (s * 0.055, 0.06, 0.345), (x, 0.1, 0.29), (x, 0.11, 0.225)],
           0.0065, "torso", BLACK)
    box(f"buckle{s}", (x, -0.098, 0.235), (0.018, 0.006, 0.022), "torso", METAL, bevel=0)

# ---- arms (rest pose: straight out to the side) --------------------------------
for s, bone in ((1, "arm-left"), (-1, "arm-right")):
    y, z = 0.017, 0.29
    tube(f"upper{s}", (s * 0.085, y, z), (s * 0.19, y, z), 0.03, 0.028, bone=bone, material=SKIN)
    tube(f"guard{s}", (s * 0.175, y, z), (s * 0.25, y, z), 0.033, 0.036, bone=bone, material=BLACK)
    tube(f"glove{s}", (s * 0.245, y, z), (s * 0.302, y, z), 0.038, 0.038, bone=bone, material=RED)
    for i, gx in enumerate((0.258, 0.29)):
        tube(f"strap{s}{i}", (s * (gx - 0.006), y, z), (s * (gx + 0.006), y, z), 0.04, bone=bone, material=BLACK)
    ellipsoid(f"stud{s}", (s * 0.274, y, z + 0.039), (0.01, 0.01, 0.006), bone, METAL, seg=6, rings=3)
    ellipsoid(f"hand{s}", (s * 0.328, y, z), (0.034, 0.031, 0.033), bone, SKIN)

# ---- legs -----------------------------------------------------------------------
for s, bone in ((1, "leg-left"), (-1, "leg-right")):
    x = s * 0.075
    tube(f"thigh{s}", (x, 0.029, 0.185), (x, 0.029, 0.125), 0.04, bone=bone, material=SKIN)
    tube(f"sock{s}", (x, 0.029, 0.148), (x, 0.027, 0.08), 0.043, 0.04, bone=bone, material=BLACK)
    box(f"boot{s}", (x, 0.012, 0.05), (0.09, 0.118, 0.092), bone, RED, bevel=1.0)
    box(f"sole{s}", (x, 0.01, 0.009), (0.092, 0.12, 0.018), bone, SOLE, bevel=0.6)
    box(f"bootstrap{s}", (x, 0.012, 0.07), (0.092, 0.108, 0.013), bone, BLACK, bevel=0)
    box(f"bootbuckle{s}", (x + s * 0.02, -0.044, 0.07), (0.018, 0.005, 0.016), bone, METAL, bevel=0)

finish()
