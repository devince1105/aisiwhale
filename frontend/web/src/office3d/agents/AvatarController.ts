// Drives one avatar (T-405): the pose's clip from the pack (crossfaded), a one-off clip when a
// pose begins (a nod when done), and the upper-body layer the pack does not have — typing,
// thinking, reading, slumping — as bone rotations on top of the sitting clip. No React: the
// component calls setPose() from a store subscription and update() every frame.
import {
  AnimationMixer,
  Euler,
  LoopOnce,
  LoopRepeat,
  Quaternion,
  Vector3,
  type AnimationAction,
  type AnimationClip,
  type Object3D,
} from "three";

import { POSE_CLIP } from "../assets/characters";
import type { Pose } from "../visual/mapping";

const FADE = 0.3;
/**
 * The pack's heads are big (a toy look); scaled down from the neck (T-413) the figures read more
 * like office staff. Applied after the clips, which may key the head's scale. A member's own figure
 * (D-198) is modelled to her reference's proportions and keeps her head at 1.
 */
export const HEAD_SCALE = 0.8;
const BONES = ["torso", "head", "arm-left", "arm-right", "forearm-left", "forearm-right"] as const;
type BoneName = (typeof BONES)[number];

/** Upper-body rotations (radians, x = pitch forward, z = roll) per pose, at time t. */
export function upperBody(pose: Pose, t: number): Partial<Record<BoneName, [number, number, number]>> {
  switch (pose) {
    case "sit_type": {
      // both forearms on the keyboard, tapping out of step
      const tap = (phase: number) => Math.max(0, Math.sin(t * 14 + phase)) * 0.12;
      return {
        "arm-left": [-1.15 - tap(0), 0, 0.12],
        "arm-right": [-1.15 - tap(Math.PI), 0, -0.12],
        head: [0.12, 0, 0],
      };
    }
    case "sit_think":
      // chin on the right hand, head tilted, a slow sway
      return {
        "arm-right": [-2.2, 0, -0.35],
        head: [0.05, 0, 0.18 + Math.sin(t * 1.2) * 0.05],
        torso: [0.05, 0, 0],
      };
    case "sit_read":
      return {
        head: [0.32, 0, 0],
        "arm-left": [-0.9, 0, 0.1],
        "arm-right": [-0.9, 0, -0.1],
      };
    case "slump":
      return {
        head: [0.55, 0, 0],
        torso: [0.3, 0, 0],
        "arm-left": [0.15, 0, 0.05],
        "arm-right": [0.15, 0, -0.05],
      };
    case "sit_idle":
      // breathing
      return { torso: [Math.sin(t * 1.6) * 0.02, 0, 0] };
    default:
      return {};
  }
}

type Triple = [number, number, number];

/**
 * An own figure's arms bend (D-201): its rig has its arm pivots at its shoulders and a forearm bone at
 * each elbow, which no clip moves. Seated, the pack's sit clip holds the arms 45 degrees down and out,
 * like wings; these are the left arm's rotations after it (upper arm, forearm), which put both hands
 * on the desk to type, in the lap, up to read, folded to slump on, or the right fist under the chin.
 * The right arm mirrors them. Solved for the clip and the figures' proportions (Tifa's, D-199), seated
 * SEAT_FORWARD nearer the desk (figures-source/blender, D-201).
 */
const SEATED_ARMS: Record<"sit_type" | "sit_idle" | "sit_read" | "slump" | "think", [Triple, Triple]> = {
  sit_type: [[1.382, -0.725, 1.091], [0.082, -0.331, 0.425]],
  sit_idle: [[1.532, -0.69, 0.28], [0.102, -0.164, 1.014]],
  sit_read: [[1.438, -0.715, 0.895], [0.306, -0.248, 1.2]],
  slump: [[1.26, -0.681, 1.046], [0.228, -0.741, 0.451]],
  think: [[1.55, -0.737, 0.292], [0.423, 0.088, 1.877]],
};
/** How far a seated own figure turns her head toward the camera (radians), and how quickly (per second). */
export const GAZE_LIMIT = Math.PI / 4;
const GAZE_RATE = 4;
/** How far she lifts her head toward a camera above her (radians, D-215): about 20 degrees, well inside
 * what a neck does, so a bird's-eye view gets a look up and not a head thrown back. */
export const GAZE_UP_LIMIT = 0.35;
/** The share of the camera's height above her (as an angle) she lifts her head by: the eyes do the rest. */
export const GAZE_UP_SHARE = 0.5;

/** Where an own figure's head goes for a camera at ``at`` in her own frame (+z ahead, +x her left, +y up),
 * if she is looking at all: [turn, lift] - the turn toward it, not round to look behind her, and the lift
 * toward it when it is above her. The controller limits and eases both. */
export function gazeToward(at: { x: number; y: number; z: number }, looking: boolean): [number, number] {
  const turn = Math.atan2(at.x, at.z);
  if (!looking || Math.abs(turn) >= Math.PI * 0.6) return [0, 0];
  return [turn, Math.max(0, Math.atan2(at.y, Math.hypot(at.x, at.z))) * GAZE_UP_SHARE];
}
/** Standing and walking: how far below level the arms hang (radians), and the forearms' bend forward. */
const HANG = 1.15;
const ELBOW_BEND = 0.26;
const mirror = ([x, y, z]: Triple): Triple => [x, -y, -z];

/** Which seated arms a pose takes, per side (the right fist goes to the chin when thinking). */
function seatedArms(pose: Pose, side: "left" | "right"): [Triple, Triple] | null {
  switch (pose) {
    case "sit_type":
    case "sit_idle":
    case "sit_read":
    case "slump":
      return SEATED_ARMS[pose];
    case "sit_think":
      return side === "right" ? SEATED_ARMS.think : SEATED_ARMS.sit_idle;
    default:
      return null;
  }
}

export class AvatarController {
  readonly mixer: AnimationMixer;
  /** The pose being shown; set to null to force the next setPose to apply. */
  pose: Pose | null = null;
  private readonly actions = new Map<string, AnimationAction>();
  private base: AnimationAction | null = null;
  private once: AnimationAction | null = null;
  private readonly bones = new Map<BoneName, { bone: Object3D; rest: Quaternion }>();
  private time = 0;
  private readonly offset = new Quaternion();
  private readonly euler = new Euler();
  private readonly swing = new Vector3();
  /** Whether the rig has the own figures' bending arms (forearm bones). */
  private readonly bendy: boolean;
  /** Where the head should turn, about its own vertical (radians, + toward her left); the head eases
   * there. Set each frame by whoever knows where the camera is (D-203). */
  gaze = 0;
  /** How far up the head should lift (radians, + up), eased the same way (D-215). */
  gazeUp = 0;
  private headTurn = 0;
  private headLift = 0;

  constructor(
    private readonly root: Object3D,
    clips: readonly AnimationClip[],
    private readonly headScale = HEAD_SCALE,
  ) {
    this.mixer = new AnimationMixer(root);
    for (const clip of clips) this.actions.set(clip.name, this.mixer.clipAction(clip));
    for (const name of BONES) {
      const bone = root.getObjectByName(name);
      if (bone) this.bones.set(name, { bone, rest: bone.quaternion.clone() });
    }
    this.bendy = this.bones.has("forearm-left") && this.bones.has("forearm-right");
    this.bones.get("head")?.bone.scale.setScalar(this.headScale);
    this.mixer.addEventListener("finished", (event) => {
      if (event.action === this.once && this.base) {
        this.base.reset().setEffectiveWeight(1).fadeIn(FADE).play();
        this.once.fadeOut(FADE);
        this.once = null;
      }
    });
  }

  /** Change pose: crossfade to its clip, play its one-off clip if it has one. No-op if unchanged. */
  setPose(pose: Pose): void {
    if (pose === this.pose) return;
    this.pose = pose;
    this.root.userData.pose = pose;
    const { base, once } = POSE_CLIP[pose];
    const next = this.actions.get(base) ?? null;
    if (next && next !== this.base) {
      next.reset().setLoop(LoopRepeat, Infinity).setEffectiveWeight(1).fadeIn(this.base ? FADE : 0).play();
      this.base?.fadeOut(FADE);
      this.base = next;
    }
    // a standing gesture still playing must not linger over a new (seated) pose
    if (this.once && base !== "idle") {
      this.once.fadeOut(FADE);
      this.once = null;
    }
    // a one-off gesture only where it does not fight the base pose (standing on standing)
    const gesture = once ? this.actions.get(once) : undefined;
    if (gesture && base === "idle") {
      this.once?.stop();
      gesture.reset().setLoop(LoopOnce, 1).setEffectiveWeight(1).fadeIn(FADE).play();
      gesture.clampWhenFinished = false;
      this.base?.fadeOut(FADE);
      this.once = gesture;
    }
  }

  /** Advance the clips, then lay the pose's upper body on top. */
  update(dt: number): void {
    this.time += dt;
    for (const { bone, rest } of this.bones.values()) bone.quaternion.copy(rest);
    this.mixer.update(dt);
    this.bones.get("head")?.bone.scale.setScalar(this.headScale);
    if (!this.pose) return;
    if (this.bendy) this.bendArms(this.pose);
    for (const [name, [x, y, z]] of Object.entries(upperBody(this.pose, this.time)) as [BoneName, Triple][]) {
      const entry = this.bones.get(name);
      if (!entry || (this.bendy && name.startsWith("arm-"))) continue;
      entry.bone.quaternion.multiply(this.offset.setFromEuler(this.euler.set(x, y, z)));
    }
    const ease = Math.min(1, dt * GAZE_RATE);
    this.headTurn += (Math.max(-GAZE_LIMIT, Math.min(GAZE_LIMIT, this.gaze)) - this.headTurn) * ease;
    this.headLift += (Math.max(0, Math.min(GAZE_UP_LIMIT, this.gazeUp)) - this.headLift) * ease;
    if (Math.abs(this.headTurn) > 1e-4 || this.headLift > 1e-4) {
      // turned first, then lifted in the turned frame (x forward is a nod down, so up is negative)
      this.bones.get("head")?.bone.quaternion.multiply(this.offset.setFromEuler(this.euler.set(-this.headLift, this.headTurn, 0, "YXZ")));
      this.euler.order = "XYZ";
    }
  }

  /** The bending arms (D-201): seated, the pose's arms after the sit clip; standing or walking (and no
   * gesture playing), hanging at the sides, swinging as the clip swings the pack's spread arms. */
  private bendArms(pose: Pose): void {
    for (const [side, s] of [["left", 1], ["right", -1]] as const) {
      const upper = this.bones.get(`arm-${side}`)!;
      const fore = this.bones.get(`forearm-${side}`)!;
      const seated = seatedArms(pose, side);
      if (seated) {
        const [u, f] = side === "left" ? seated : [mirror(seated[0]), mirror(seated[1])];
        upper.bone.quaternion.multiply(this.offset.setFromEuler(this.euler.set(...u)));
        fore.bone.quaternion.multiply(this.offset.setFromEuler(this.euler.set(...f)));
        if (pose === "sit_type") {
          // tapping: each hand lifts off the keys in turn
          const tap = Math.max(0, Math.sin(this.time * 14 + (s > 0 ? 0 : Math.PI))) * 0.14;
          fore.bone.quaternion.multiply(this.offset.setFromEuler(this.euler.set(0, 0, s * tap)));
        }
      } else if (!this.once) {
        // how far forward the clip swings the arm, kept; how far out it holds it, not
        this.swing.set(s, 0, 0).applyQuaternion(upper.bone.quaternion);
        const forward = Math.atan2(this.swing.z, Math.abs(this.swing.x));
        upper.bone.quaternion
          .copy(upper.rest)
          .multiply(this.offset.setFromEuler(this.euler.set(-forward, 0, 0)))
          .multiply(this.offset.setFromEuler(this.euler.set(0, 0, -s * HANG)));
        fore.bone.quaternion.copy(fore.rest).multiply(this.offset.setFromEuler(this.euler.set(0, -s * ELBOW_BEND, 0)));
      }
    }
  }

  /** Which clip currently drives the body (for tests and debugging). */
  get clip(): string | null {
    return this.once?.getClip().name ?? this.base?.getClip().name ?? null;
  }

  /** Stop everything. The controller may be used again afterwards, and starts from nothing.
   *
   * It does not uncache the root: that drops the mixer's bookkeeping for actions this object
   * still holds, and playing one of them again walks off the end of the mixer's own list
   * ("Cannot set properties of undefined (setting '_cacheIndex')"). React makes that happen in
   * development — it runs an effect, cleans it up and runs it again, while the controller
   * itself is a useMemo value that survives both. Nothing leaks: the mixer belongs to this
   * controller alone and is collected with it.
   */
  dispose(): void {
    this.mixer.stopAllAction();
    this.base = null;
    this.once = null;
    this.pose = null;
  }
}
