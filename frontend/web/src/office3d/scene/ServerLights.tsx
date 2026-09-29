// The server room's lights (D-121): the racks stand for the system itself, and their lights say
// whether it is running. Read from the realtime connection each frame, so the scene does not
// re-render for it: live, the status lights twinkle green and the beacons glow steady; while the
// stream is (re)connecting everything blinks amber; when it is lost, red. The top light of each
// column flickers blue for a moment after every event, as a disk light does when work passes.
import { useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import { BoxGeometry, Color, CylinderGeometry, InstancedMesh, MeshBasicMaterial, Object3D } from "three";

import { realtimeStore, type ConnectionStatus } from "@/stores/realtime";

import { SERVER_LIGHT_ROWS, serverLightSpots } from "./furniture";

export type Health = "ok" | "starting" | "down";

export function healthOf(status: ConnectionStatus): Health {
  if (status === "live") return "ok";
  if (status === "offline" || status === "unauthorized" || status === "not_found") return "down";
  return "starting";
}

const GREEN = "#3ee07a";
const AMBER = "#ffb020";
const RED = "#ff3b3b";
const BLUE = "#4aa8ff";
const OFF = "#1d2320";

/** How long after an event the activity lights keep flickering (ms). */
export const BUSY_MS = 1500;

/** A light's colour: ``index`` is its place in ``serverLightSpots().leds``, ``t`` seconds. */
export function ledColor(health: Health, index: number, t: number, busy: boolean, out: Color): Color {
  if (health === "down") return out.set(Math.sin(t * 6) > 0 ? RED : OFF);
  if (health === "starting") return out.set(Math.sin(t * 4) > 0 ? AMBER : OFF);
  if (index % SERVER_LIGHT_ROWS === 0) return out.set(busy && Math.sin(t * 40 + index) > 0 ? BLUE : OFF);
  // each light twinkles at its own rate and phase; mostly on
  const phase = (index * 2.39996) % (Math.PI * 2);
  const rate = 1.3 + ((index * 7) % 11) / 5;
  return out.set(Math.sin(t * rate + phase) > -0.6 ? GREEN : OFF);
}

export function beaconColor(health: Health, t: number, out: Color): Color {
  if (health === "down") return out.set(Math.sin(t * 6) > 0 ? RED : OFF);
  if (health === "starting") return out.set(Math.sin(t * 4) > 0 ? AMBER : OFF);
  // a slow breath, never dark
  return out.set(GREEN).multiplyScalar(0.75 + 0.25 * Math.sin(t * 1.6));
}

function instanced(geometry: BoxGeometry | CylinderGeometry, spots: readonly (readonly [number, number, number])[]): InstancedMesh {
  const mesh = new InstancedMesh(geometry, new MeshBasicMaterial({ toneMapped: false }), spots.length);
  const dummy = new Object3D();
  spots.forEach((pos, i) => {
    dummy.position.set(pos[0], pos[1], pos[2]);
    dummy.updateMatrix();
    mesh.setMatrixAt(i, dummy.matrix);
    mesh.setColorAt(i, new Color(OFF));
  });
  return mesh;
}

export function ServerLights() {
  const meshes = useMemo(() => {
    const { leds, beacons } = serverLightSpots();
    return {
      leds: instanced(new BoxGeometry(0.06, 0.03, 0.01), leds),
      beacons: instanced(new CylinderGeometry(0.045, 0.05, 0.1, 12), beacons),
    };
  }, []);
  useEffect(
    () => () => {
      for (const mesh of [meshes.leds, meshes.beacons]) {
        mesh.geometry.dispose();
        (mesh.material as MeshBasicMaterial).dispose();
        mesh.dispose();
      }
    },
    [meshes],
  );
  const color = useRef(new Color());
  useFrame(({ clock }) => {
    const t = clock.elapsedTime;
    const { status, lastEventAt } = realtimeStore.getState().connection;
    const health = healthOf(status);
    const busy = lastEventAt !== null && Date.now() - lastEventAt < BUSY_MS;
    for (let i = 0; i < meshes.leds.count; i++) meshes.leds.setColorAt(i, ledColor(health, i, t, busy, color.current));
    for (let i = 0; i < meshes.beacons.count; i++) meshes.beacons.setColorAt(i, beaconColor(health, t + i * 0.4, color.current));
    meshes.leds.instanceColor!.needsUpdate = true;
    meshes.beacons.instanceColor!.needsUpdate = true;
  });
  return (
    <group name="server-lights">
      <primitive object={meshes.leds} />
      <primitive object={meshes.beacons} />
    </group>
  );
}
