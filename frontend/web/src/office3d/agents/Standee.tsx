// A standee (D-118): someone's Q-version figure, cut out of its portrait, standing in the office
// on an upright card that always turns to the camera. It takes the model's place in AgentAvatar,
// so where she sits, the walk to the next desk and the click that opens her panel are unchanged;
// what a model shows with its limbs, the standee shows by how high it stands and how it bobs.
import { useTexture } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useRef } from "react";
import { DoubleSide, Quaternion, SRGBColorSpace, Vector3, type Group, type Mesh, type MeshBasicMaterial, type Object3D, type Texture } from "three";

import type { Pose } from "../visual/mapping";

/** Model units (the avatar group is scaled by AVATAR_SCALE): a little taller than the chibi
 * figures (0.78), so a face reads at the overview. */
export const STANDEE_HEIGHT = 0.95;

/** How high the standee stands for a pose, at time ``t`` (seconds). Seated, it sinks so the
 * desk hides her legs; typing and walking bob; slumping sinks further. */
export function standeeLift(pose: Pose | null, t: number): number {
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

function widthOf(texture: Texture): number {
  const image = texture.image as { width: number; height: number } | undefined;
  return image ? (STANDEE_HEIGHT * image.width) / image.height : STANDEE_HEIGHT * 0.6;
}

export function Standee({ url, back = null }: { url: string; back?: string | null }) {
  const card = useRef<Group>(null);
  const plane = useRef<Mesh>(null);
  const showingBack = useRef(false);
  const textures = useTexture(back ? [url, back] : [url], (t) => {
    for (const loaded of Array.isArray(t) ? t : [t]) {
      loaded.colorSpace = SRGBColorSpace;
      loaded.anisotropy = 4;
    }
  });
  const [front, behind] = textures;
  useFrame(({ camera }) => {
    if (!card.current) return;
    camera.getWorldDirection(lookDirection);
    const avatar = card.current.parent;
    const wasBack = showingBack.current;
    const isBack = Boolean(behind && avatar && seesBack(avatar, lookDirection, wasBack));
    // seen from behind she sits in her chair, its back in front of her as a sitter's is; seen
    // from the front she stands a step out of it, or the chair's back would hide her
    faceCamera(card.current, lookDirection, isBack ? 0 : CARD_FORWARD);
    if (isBack === wasBack || !behind || !plane.current) return;
    showingBack.current = isBack;
    const texture = isBack ? behind : front;
    const material = plane.current.material as MeshBasicMaterial;
    material.map = texture;
    material.needsUpdate = true;
    plane.current.scale.x = widthOf(texture);
  });
  return (
    // upright: it turns about the vertical only, so it never leans back at the isometric camera
    <group ref={card}>
      <mesh ref={plane} name="standee" position={[0, STANDEE_HEIGHT / 2, 0]} scale={[widthOf(front), STANDEE_HEIGHT, 1]}>
        <planeGeometry args={[1, 1]} />
        <meshBasicMaterial map={front} transparent alphaTest={0.4} side={DoubleSide} toneMapped={false} />
      </mesh>
    </group>
  );
}
