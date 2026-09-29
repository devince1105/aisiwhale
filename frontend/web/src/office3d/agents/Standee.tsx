// A standee (D-118): someone's Q-version figure, cut out of its portrait, standing in the office
// on an upright card that always turns to the camera. It takes the model's place in AgentAvatar,
// so where she sits, the walk to the next desk and the click that opens her panel are unchanged;
// what a model shows with its limbs, the standee shows by how high it stands and how it bobs.
import { useTexture } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useRef } from "react";
import { DoubleSide, Quaternion, SRGBColorSpace, Vector3, type Group, type Mesh, type MeshBasicMaterial, type Object3D, type Texture } from "three";

import type { Pose } from "../visual/mapping";
import { AVATAR_SCALE, SEAT_LIFT } from "./body";

/** Model units (the avatar group is scaled by AVATAR_SCALE): a little taller than the chibi
 * figures (0.78), so a face reads at the overview. */
export const STANDEE_HEIGHT = 0.95;

/** A seated picture's height, in the same units: the chibi's legs are short, so sitting takes
 * little off her height (the operator's seated and standing pictures, matched by head size). */
export const SIT_HEIGHT = STANDEE_HEIGHT * 0.97;

/** Seated, unless standing or walking (no pose yet is the chair, where everyone starts). */
export function isSeated(pose: Pose | null): boolean {
  return pose !== "stand" && pose !== "walk";
}

/** How high the standee stands for a pose, at time ``t`` (seconds). With a seated picture
 * (D-124) she sits on her chair's seat, her feet on the floor, and only bobs. Without one the
 * standing picture sinks so the desk hides her legs; typing and walking bob; slumping sinks
 * further. */
export function standeeLift(pose: Pose | null, t: number, seatedPicture = false): number {
  if (seatedPicture && isSeated(pose)) {
    // the avatar is raised to the chair's seat; her picture goes back down to the floor
    const floor = -SEAT_LIFT / AVATAR_SCALE;
    if (pose === "sit_type") return floor + Math.abs(Math.sin(t * 10)) * 0.012;
    if (pose === "sit_think") return floor + Math.sin(t * 2) * 0.008;
    if (pose === "slump") return floor - 0.05;
    return floor;
  }
  switch (pose) {
    case "walk":
      return Math.abs(Math.sin(t * 9)) * 0.04;
    case "stand":
      return 0;
    case "sit_type":
      return -0.22 + Math.abs(Math.sin(t * 10)) * 0.012;
    case "sit_think":
      return -0.22 + Math.sin(t * 2) * 0.01;
    case "slump":
      return -0.28;
    default:
      return -0.22;
  }
}

/** Model units: how far toward the camera the card stands, so she is in front of her chair's back
 * (which, from the camera's side, is between the viewer and a seated figure) rather than behind
 * it. Only toward the viewer: where she is on the floor plan does not change. */
export const CARD_FORWARD = 0.3;

const toward = new Vector3();
const yaw = new Quaternion();
const parentTurn = new Quaternion();
const UP = new Vector3(0, 1, 0);

/** The card's own turn so that, under its parent's, it faces the camera about the vertical only:
 * the camera's horizontal direction, less whatever the avatar group is turned (its seat, or the
 * way a courier walks). Not drei's Billboard: with the tilt locked it keeps the camera's Y euler,
 * which under this isometric camera is not its yaw, and the card stood almost edge-on. */
export function faceCamera(card: Group, cameraDirection: Vector3, step: number = CARD_FORWARD): void {
  toward.set(-cameraDirection.x, 0, -cameraDirection.z);
  if (toward.lengthSq() < 1e-6) return;
  yaw.setFromAxisAngle(UP, Math.atan2(toward.x, toward.z));
  card.parent?.getWorldQuaternion(parentTurn);
  parentTurn.invert();
  card.quaternion.copy(parentTurn).multiply(yaw);
  // a step toward the camera, in the parent's own frame
  card.position.copy(toward.normalize().multiplyScalar(step).applyQuaternion(parentTurn));
}

const forward = new Vector3();
const turn = new Quaternion();

/** How far past side-on the camera must go before the picture changes (the dot product of her
 * facing and the way to the camera), so that seen edge-on she does not flicker between the two. */
const SIDE_ON = 0.12;

/**
 * Whether the camera is at her back (D-123): behind the way she faces — the avatar group's +z,
 * which her seat or her walk turns — measured on the floor. ``wasBack`` is what was shown last.
 */
export function seesBack(avatar: Object3D, cameraDirection: Vector3, wasBack: boolean): boolean {
  forward.set(0, 0, 1).applyQuaternion(avatar.getWorldQuaternion(turn));
  forward.y = 0;
  toward.set(-cameraDirection.x, 0, -cameraDirection.z);
  if (forward.lengthSq() < 1e-6 || toward.lengthSq() < 1e-6) return wasBack;
  const facing = forward.normalize().dot(toward.normalize());
  return wasBack ? facing < SIDE_ON : facing < -SIDE_ON;
}

const lookDirection = new Vector3();

/** Someone's pictures: standing, from the front and behind (D-118, D-123), and seated (D-124).
 * Only the standing front is needed; the rest stand in for each other when missing. */
export interface Pictures {
  stand: string;
  standBack?: string | null;
  sit?: string | null;
  sitBack?: string | null;
}
export type View = "stand" | "standBack" | "sit" | "sitBack";

/** Which picture shows, seated or not, seen from behind or not. */
export function viewFor(pictures: Pictures, seated: boolean, back: boolean): View {
  if (seated && pictures.sit) return back && pictures.sitBack ? "sitBack" : "sit";
  return back && pictures.standBack ? "standBack" : "stand";
}

/** How far toward the camera the card stands for a view: seated, or seen from behind, she is in
 * her chair (its back in front of her, as a sitter's is); standing and seen from the front, a step
 * out of it, or the chair's back would hide her. */
export function stepFor(view: View): number {
  return view === "stand" ? CARD_FORWARD : 0;
}

const VIEWS: View[] = ["stand", "standBack", "sit", "sitBack"];

function sizeOf(texture: Texture, view: View): [number, number] {
  const height = view === "sit" || view === "sitBack" ? SIT_HEIGHT : STANDEE_HEIGHT;
  const image = texture.image as { width: number; height: number } | undefined;
  return [image ? (height * image.width) / image.height : height * 0.6, height];
}

export function Standee({ pictures, pose }: { pictures: Pictures; pose: () => Pose | null }) {
  const card = useRef<Group>(null);
  const plane = useRef<Mesh>(null);
  const shown = useRef<View>("stand");
  const views = VIEWS.filter((view) => pictures[view]);
  const textures = useTexture(
    views.map((view) => pictures[view]!),
    (t) => {
      for (const loaded of Array.isArray(t) ? t : [t]) {
        loaded.colorSpace = SRGBColorSpace;
        loaded.anisotropy = 4;
      }
    },
  );
  const texture = (view: View) => textures[views.indexOf(view)];
  useFrame(({ camera }) => {
    if (!card.current) return;
    camera.getWorldDirection(lookDirection);
    const avatar = card.current.parent;
    const wasBack = shown.current === "standBack" || shown.current === "sitBack";
    const back = Boolean(avatar && seesBack(avatar, lookDirection, wasBack));
    const view = viewFor(pictures, isSeated(pose()), back);
    faceCamera(card.current, lookDirection, stepFor(view));
    if (view === shown.current || !plane.current) return;
    shown.current = view;
    const material = plane.current.material as MeshBasicMaterial;
    material.map = texture(view);
    material.needsUpdate = true;
    const [width, height] = sizeOf(texture(view), view);
    plane.current.scale.set(width, height, 1);
    plane.current.position.y = height / 2;
  });
  const [width, height] = sizeOf(texture("stand"), "stand");
  return (
    // upright: it turns about the vertical only, so it never leans back at the isometric camera
    <group ref={card}>
      <mesh ref={plane} name="standee" position={[0, height / 2, 0]} scale={[width, height, 1]}>
        <planeGeometry args={[1, 1]} />
        <meshBasicMaterial map={texture("stand")} transparent alphaTest={0.4} side={DoubleSide} toneMapped={false} />
      </mesh>
    </group>
  );
}
