# Tifa's game mesh settings for lowpoly.py (D-197). Budget: 3,000 triangles in all.
TEX = 1024
CAGE = 0.015
RAY = 0.04


def smooth(e0, e1, x):
    k = min(1, max(0, (x - e0) / (e1 - e0)))
    return k * k * (3 - 2 * k)


def body_weights(co):
    """The skin's weights by region. Bone heat can't be used: the pack's leg bones point up from the
    hips, so it gives the lower legs to the root bone between them."""
    side = "left" if co.x > 0 else "right"
    leg = (1 - smooth(0.19, 0.225, co.z)) * smooth(0.004, 0.02, abs(co.x))
    arm = smooth(0.062, 0.092, abs(co.x)) * smooth(0.24, 0.26, co.z)
    w = {f"leg-{side}": leg, f"arm-{side}": arm * (1 - leg)}
    w["torso"] = max(0.0, 1 - leg - w[f"arm-{side}"])
    return w


GROUPS = {
    "lo-head": ("head", 380, True, ["head"], 0.004, 0.0),
    "lo-hair": ("head", 1100, False, ["hair", "lock-", "tail", "tie"], 0.004, 0.0),
    "lo-body": (body_weights, 760, True, ["body"], 0.004, 0.004),
    "lo-boots": ("legs", 300, True, ["boot", "sole", "cuff"], 0.004, 0.0),
}


FACE = ["head", "eye", "shine", "lid", "brow", "blush", "nose", "mouth"]
BAKE_FROM = {
    "lo-head": FACE,
    "lo-hair": ["hair", "lock-", "tail", "tie"],
    "lo-body": ["body", "tank", "piping", "socks", "sockband", "guards", "gloves", "glovestrap", "stud", "suspender", "buckle", "navel"],
    "lo-boots": ["boot", "sole", "cuff"],
    "lo-skirt": ["skirt"],
    "lo-waistband": ["waistband"],
    "lo-earring1": ["earring1"],
    "lo-earring-1": ["earring-1"],
}


CAGE_FOR = {"lo-boots": 0.003}      # the sole sits right under the boot


def FRONT_PROJECT(f, part, part_of):
    """The painted face: head faces looking forward, below the fringe."""
    c = f.calc_center_median()
    return f[part] == part_of["lo-head"] and f.normal.y < -0.35 and 0.39 < c.z < 0.6 and abs(c.x) < 0.14


def UV_SCALE(bm, part, part_of):
    """(face test, factor) — texel density per part, relative to an even spread. The face is painted
    on (eyes, mouth), most of the scalp is under the hair, and the body carries the piping and straps."""
    def of(name):
        i = part_of[name]
        return lambda f: f[part] == i
    return [
        (lambda f: FRONT_PROJECT(f, part, part_of), 3.5),
        (of("lo-head"), 0.6),
        (of("lo-body"), 2.2),
        (of("lo-skirt"), 1.6),
        (of("lo-waistband"), 1.5),
        (of("lo-boots"), 1.3),
    ]


def LOW_EXTRA():
    """The skirt (one sheet, 32 pleat faces round) and the earrings, made low directly."""
    out = []
    sk = pleated_skirt("lo-skirt", 0.236, 0.146, 0.068, 0.112, None, seg=32, rings=3, thickness=0)
    wb = lathe("lo-waistband", (0, 0.028, 0.226), (0, 0.028, 0.247), [0.064, 0.07, 0.064], "torso", None, seg=16, squash=0.86)
    rings = [box(f"lo-earring{s}", (s * 0.168, 0.008, 0.43), (0.007, 0.006, 0.024), "head", None, bevel=0) for s in (1, -1)]
    for o in [sk, wb] + rings:
        for m in list(o.modifiers):
            o.modifiers.remove(m)
        o.parent = None
        for c in list(o.users_collection):
            c.objects.unlink(o)
        bpy.context.scene.collection.objects.link(o)
        o.data.materials.clear()
        out.append(o)
    sk.vertex_groups.new(name="torso").add(list(range(len(sk.data.vertices))), 1.0, "REPLACE")
    return out
