# Tifa's high-poly (D-197), the source for lowpoly.py's bake. Needs lib.py and sculpt.py first.
# References: avatars-source/q/Tifa.jpg, back/tifa.jpg, stand-side/tifa.jpg. Blender: Z up, she
# faces -Y, her left is +X; rest pose is the Kenney T-pose.
arm = reset("tifa")

SKIN = mat("skin", "#F9D5BE")
HAIR = mat("hair", "#2B2224", rough=0.6)
WHITE = mat("top", "#F3F1EC")
BLACK = mat("black", "#2C2B31")
DARK = mat("dark", "#1E1D22")
RED = mat("red", "#B42B30", rough=0.55)
SOLE = mat("sole", "#2A2526")
METAL = mat("metal", "#B9BAC2", rough=0.35, metal=0.8)
EYE = mat("eye", "#3B2A25", rough=0.3)
SHINE = mat("shine", "#FFFFFF", rough=0.3)
BLUSH = mat("blush", "#F4A9A3")
NOSE = mat("nose", "#F2A27A")
MOUTH = mat("mouth", "#4A2A24")


def smooth(e0, e1, x):
    k = min(1, max(0, (x - e0) / (e1 - e0)))
    return k * k * (3 - 2 * k)


def E(name, c, r, seg=32, rings=16, rot=(0, 0, 0), cut=None):
    return to_hi(ellipsoid(name, c, r, "head", SKIN, seg=seg, rings=rings, rot=rot, cut=cut))


def T(name, a, b, r1, r2=None, seg=24):
    return to_hi(tube(name, a, b, r1, r2, bone="head", material=SKIN, seg=seg))


# ---- head: Animal Crossing shape — round, fuller at the cheeks, a soft flat chin ---------------
HEAD_C = Vector((0, 0, 0.5))
head = union("head", [
    E("cranium", HEAD_C, (0.162, 0.148, 0.152)),
    E("cheeks", (0, -0.025, 0.445), (0.15, 0.115, 0.085)),
    E("ear-l", (0.16, 0.01, 0.478), (0.026, 0.02, 0.034), seg=16, rings=8),
    E("ear-r", (-0.16, 0.01, 0.478), (0.026, 0.02, 0.034), seg=16, rings=8),
    T("neck", (0, 0.01, 0.33), (0, 0.01, 0.4), 0.027),
], voxel=0.0025, smooth=10, material=SKIN)

# the face is painted on by the bake: thin shells just above the sculpted skin
FACE = Surface(head)


def face_part(name, x, z, size, material, lift=0.0035):
    p, rot = FACE.at(x, z, lift)
    o = ellipsoid(name, p, size, "head", material, seg=24, rings=8, rot=rot, cut=lambda v: v.y > 0.05)
    return to_hi(o, material)


def face_line(name, pts, radius, material, lift=0.003):
    return to_hi(stroke(name, [FACE.at(x, z, lift)[0] for x, z in pts], radius, "head", material), material)


for s in (1, -1):
    x = s * 0.072
    face_part(f"eye{s}", x, 0.486, (0.031, 0.006, 0.037), EYE)
    face_part(f"shine{s}", x - s * 0.01, 0.5, (0.01, 0.003, 0.011), SHINE, lift=0.007)
    face_part(f"shine2{s}", x + s * 0.012, 0.472, (0.005, 0.003, 0.005), SHINE, lift=0.007)
    face_line(f"lid{s}", [(x - s * 0.034, 0.5), (x - s * 0.018, 0.52), (x + s * 0.008, 0.526), (x + s * 0.03, 0.514), (x + s * 0.04, 0.506), (x + s * 0.048, 0.517)], 0.0042, EYE)
    face_line(f"brow{s}", [(x - s * 0.024, 0.553), (x - s * 0.004, 0.562), (x + s * 0.024, 0.558)], 0.0026, HAIR)
    face_part(f"blush{s}", s * 0.108, 0.447, (0.027, 0.004, 0.014), BLUSH, lift=0.0015)
face_part("nose", 0, 0.463, (0.015, 0.007, 0.011), NOSE, lift=0.003)
face_line("mouth", [(-0.036, 0.43), (-0.02, 0.415), (0, 0.41), (0.02, 0.415), (0.036, 0.43)], 0.0032, MOUTH)
for s in (1, -1):
    to_hi(box(f"earring{s}", (s * 0.168, 0.008, 0.43), (0.007, 0.006, 0.024), "head", METAL, bevel=0.3), METAL)


# ---- body: one skin from shoulders to ankles -----------------------------------------------------
def B(name, c, r, rot=(0, 0, 0)):
    return to_hi(ellipsoid(name, c, r, "torso", SKIN, seg=32, rings=16, rot=rot))


parts = [
    B("chest", (0, 0.026, 0.292), (0.058, 0.046, 0.06)),
    B("waist", (0, 0.028, 0.245), (0.052, 0.043, 0.05)),
    B("hips", (0, 0.028, 0.212), (0.062, 0.048, 0.035)),
    T("neckbase", (0, 0.02, 0.31), (0, 0.015, 0.355), 0.03, 0.026),
]
for s in (1, -1):
    parts += [
        B(f"bust{s}", (s * 0.025, 0.0, 0.3), (0.026, 0.018, 0.022)),
        B(f"shoulder{s}", (s * 0.068, 0.02, 0.292), (0.03, 0.028, 0.029)),
        T(f"upperarm{s}", (s * 0.068, 0.018, 0.29), (s * 0.15, 0.017, 0.29), 0.025, 0.022),
        T(f"forearm{s}", (s * 0.15, 0.017, 0.29), (s * 0.26, 0.017, 0.29), 0.022, 0.026),
        B(f"hand{s}", (s * 0.292, 0.016, 0.288), (0.034, 0.03, 0.031)),
        B(f"thumb{s}", (s * 0.282, -0.012, 0.296), (0.013, 0.011, 0.012)),
        T(f"thigh{s}", (s * 0.048, 0.028, 0.215), (s * 0.05, 0.028, 0.1), 0.03, 0.029),
        T(f"calf{s}", (s * 0.05, 0.028, 0.1), (s * 0.05, 0.03, 0.04), 0.03, 0.026),
    ]
body = union("body", parts, voxel=0.0025, smooth=10, material=SKIN)

# a navel
to_hi(ellipsoid("navel", (0, -0.016, 0.243), (0.004, 0.002, 0.006), "torso", MOUTH, seg=12, rings=6), MOUTH)

# ---- the top: a cropped tank lifted off the skin, with black piping -------------------------------
def in_top(c):
    return 0.262 < c.z < 0.352 and abs(c.x) < 0.066 and not (abs(c.x) > 0.05 and c.z > 0.33)


top, loops = layer("tank", body, in_top, 0.0035, WHITE)
for i, lp in enumerate(loops):
    trim(f"piping{i}", lp, 0.0028, BLACK)


# ---- socks, arm guards, gloves: layers on the skin --------------------------------------------------
sock, loops = layer("socks", body, lambda c: 0.04 < c.z < 0.15 and abs(c.x) > 0.012, 0.0035, BLACK)
for i, lp in enumerate(loops):
    if sum(p.z for p in lp) / len(lp) > 0.1:     # a rolled top only
        trim(f"sockband{i}", lp, 0.0035, BLACK)
guard, _ = layer("guards", body, lambda c: 0.145 < abs(c.x) < 0.232 and c.z > 0.25, 0.0035, BLACK)
glove, loops = layer("gloves", body, lambda c: 0.228 < abs(c.x) < 0.3 and c.z > 0.25 and not (abs(c.x) > 0.28 and c.y < -0.0), 0.0045, RED)
for s in (1, -1):
    for i, gx in enumerate((0.237, 0.266)):
        to_hi(tube(f"glovestrap{s}{i}", (s * (gx - 0.005), 0.017, 0.29), (s * (gx + 0.005), 0.017, 0.29), 0.0335, bone="head", material=BLACK, seg=32), BLACK)
    to_hi(ellipsoid(f"stud{s}", (s * 0.252, 0.017, 0.29 + 0.034), (0.009, 0.009, 0.006), "head", METAL, seg=16, rings=8), METAL)



# ---- skirt: knife pleats that open toward the hem, with a waistband -------------------------------
pleated_skirt("skirt", 0.236, 0.146, 0.068, 0.112, BLACK)
to_hi(lathe("waistband", (0, 0.028, 0.226), (0, 0.028, 0.247), [0.064, 0.069, 0.07, 0.069, 0.064], "torso", DARK, seg=64, squash=0.86), DARK)

# ---- suspenders: flat straps from the waistband, over the shoulders, down the back ---------------
BODY = Surface(body)
for s in (1, -1):
    x = s * 0.033
    front = [BODY.cast((x, -1, z), (0, 1, 0), 0.006) for z in (0.25, 0.275, 0.3, 0.325)]
    over = [BODY.cast((s * 0.04, y, 1), (0, 0, -1), 0.006) for y in (0.0, 0.025, 0.045)]
    back = [BODY.cast((x, 1, z), (0, -1, 0), 0.006) for z in (0.32, 0.29, 0.26)]
    sweep(f"suspender{s}", front + over + back, [0.011, 0.011], [0.0035, 0.0035], BLACK, normal_from=(0, 0.028, 0.29), seg=8, tip=False)
    for y, z in ((-1, 0.252), (1, 0.252)):
        p = BODY.cast((x, y, z), (0, -y, 0), 0.008)
        to_hi(box(f"buckle{s}{y}", p, (0.016, 0.004, 0.012), "torso", METAL, bevel=0.3), METAL)

# ---- boots: a round toe grown out of the shaft, a thick sole, a strap with a buckle ----------------
for s in (1, -1):
    x = s * 0.05
    boot = union(f"boot{s}", [
        to_hi(lathe(f"shaft{s}", (x, 0.03, 0.022), (x, 0.03, 0.118), [0.037, 0.04, 0.04, 0.039, 0.038], "torso", RED, seg=48)),
        to_hi(ellipsoid(f"toe{s}", (x, -0.012, 0.042), (0.043, 0.06, 0.042), "torso", RED, seg=48, rings=24)),
    ], voxel=0.002, smooth=8, material=RED)
    to_hi(box(f"sole{s}", (x, 0.006, 0.014), (0.092, 0.138, 0.026), "torso", SOLE, bevel=0.9, segs=4), SOLE)
    to_hi(lathe(f"cuff{s}", (x, 0.03, 0.112), (x, 0.03, 0.122), [0.04, 0.043, 0.04], "torso", RED, seg=48), RED)
    to_hi(lathe(f"bootstrap{s}", (x, 0.03, 0.09), (x, 0.03, 0.103), [0.0415, 0.0425, 0.0415], "torso", BLACK, seg=48), BLACK)
    to_hi(box(f"bootbuckle{s}", (x + s * 0.03, -0.012, 0.0965), (0.016, 0.006, 0.016), "torso", METAL, bevel=0.3, rot=(0, 0, s * -0.7)), METAL)


# ---- hair --------------------------------------------------------------------------------------
# A shell from the crown: each column (azimuth t: 0 = the face, + toward her left) runs down the
# head to the fringe edge over the face, or past PHI_MAX falls as a curtain. Clumps are sculpted in
# as rounded ridges with sharp partings between them, and each clump's end comes to a point.
HC, HR = Vector((0, 0.01, 0.512)), Vector((0.186, 0.172, 0.178))
PHI_MAX = math.radians(100)
PART = 22
CLUMPS = 14


def clump(t):
    """0 in the parting between two clumps, 1 at a clump's middle — rounded, with sharp partings."""
    u = (t * CLUMPS / (2 * math.pi)) % 1
    return abs(math.sin(math.pi * u)) ** 0.45


def fringe(deg):
    a = abs(deg)
    if a >= 100:
        return None
    if a > 62:                      # above the ear; the temple locks come down in front of it
        return 84 + 2 * smooth(62, 80, a)
    if deg < PART:                  # bangs swept from the parting down across to her right
        f = (PART - deg) / (PART + 62)
        tips = max(max(0.0, 1 - abs(deg - c) / 11) ** 1.5 for c in (2, -22, -46))
        return 50 + 36 * f ** 0.75 + 7 * tips
    # her left of the parting the hair is combed back: the forehead shows, then the temple
    return 50 + 30 * smooth(PART + 10, 64, deg)


def curtain_bottom(t):
    deg = math.degrees(t)
    a = abs(deg)
    return 0.305 - 0.03 * smooth(100, 170, a) - 0.02 * smooth(100, 160, deg) - 0.03 * clump(t) ** 3


def hair_shell(cols=280, rows=70):
    def ridge(t, k):
        return 1 + 0.045 * (clump(t) - 0.7) * k

    def cap(t, ph):
        k = smooth(8, 45, math.degrees(ph))
        r = ridge(t, k)
        return Vector((HC.x + HR.x * r * math.sin(ph) * math.sin(t), HC.y - HR.y * r * math.sin(ph) * math.cos(t), HC.z + HR.z * math.cos(ph)))

    def at(t, d, L):
        if d <= PHI_MAX:
            return cap(t, d)
        top = cap(t, PHI_MAX)
        drop = d - PHI_MAX
        span = max(1e-6, L - PHI_MAX)
        a = abs(math.degrees(t))
        # fuller below the ears, flatter across the back, and the ends turn in a little
        kx = (1 + 0.07 * smooth(0, 0.12, drop)) * (1 - 0.12 * smooth(0, 0.18, drop) * smooth(120, 170, a))
        tuck = 1 - 0.1 * smooth(0.6, 1.0, drop / span)
        rr = (1 + 0.06 * (clump(t) - 0.7) * smooth(0, 0.06, drop)) * tuck
        return Vector((HC.x + (top.x - HC.x) * kx * rr, HC.y + (top.y - HC.y) * rr, top.z - drop))

    def length(t):
        deg = math.degrees(t)
        f = fringe(deg)
        if f is not None:
            return math.radians(f)
        return PHI_MAX + max(0.0, cap(t, PHI_MAX).z - curtain_bottom(t))

    bm = bmesh.new()
    crown = bm.verts.new(HC + Vector((0, 0, HR.z)))
    grid = []
    for i in range(cols):
        t = -math.pi + 2 * math.pi * i / cols
        L = length(t)
        grid.append([bm.verts.new(at(t, L * ((j + 1) / rows) ** 0.9, L)) for j in range(rows)])
    for i in range(cols):
        a, b = grid[i], grid[(i + 1) % cols]
        bm.faces.new((crown, a[0], b[0]))
        for j in range(rows - 1):
            bm.faces.new((a[j], a[j + 1], b[j + 1], b[j]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new("hair")
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new("hair", me)
    hi_collection().objects.link(o)
    o.data.materials.append(HAIR)
    for p in o.data.polygons:
        p.use_smooth = True
    sol = o.modifiers.new("Solidify", "SOLIDIFY")   # real thickness, rounded off at the edge
    sol.thickness = 0.014
    sol.offset = -1
    sol.use_even_offset = True
    apply_all(o)
    return o


hair_shell()
HEADC = (0, 0.01, 0.5)
# temple locks: in front of the ears, the right one long over the shoulder onto the chest
sweep("lock-r", [(-0.13, -0.075, 0.56), (-0.158, -0.07, 0.5), (-0.16, -0.065, 0.43), (-0.14, -0.06, 0.36), (-0.115, -0.055, 0.29)],
      [0.05, 0.05, 0.042, 0.03, 0.006], [0.02, 0.02, 0.018, 0.014, 0.004], HAIR, normal_from=HEADC, seg=16, steps=8)
sweep("lock-l", [(0.13, -0.075, 0.56), (0.158, -0.065, 0.5), (0.162, -0.055, 0.43), (0.148, -0.045, 0.37)],
      [0.045, 0.044, 0.034, 0.006], [0.02, 0.018, 0.014, 0.004], HAIR, normal_from=HEADC, seg=16, steps=8)
# the tail: gathered low at her left, tied in red, a soft teardrop below
sweep("tail", [(0.075, 0.145, 0.34), (0.1, 0.155, 0.29), (0.118, 0.162, 0.24), (0.13, 0.165, 0.19), (0.133, 0.16, 0.15)],
      [0.05, 0.032, 0.062, 0.052, 0.006], [0.04, 0.032, 0.05, 0.042, 0.006], HAIR, seg=16, steps=8)
to_hi(lathe("tie", (0.104, 0.156, 0.29), (0.108, 0.158, 0.268), [0.019, 0.021, 0.021, 0.019], "head", RED, seg=32), RED)
