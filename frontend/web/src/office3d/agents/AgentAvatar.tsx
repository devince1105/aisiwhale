// One agent in the office (T-405, 04 §3): a clone of its character, seated at its desk, posed from
// the realtime store. The store is read with a plain subscription and in the frame loop — never
// through React state — so a burst of events re-renders nothing (05 §5). While a walk cue is
// running (T-408) the avatar itself is the courier: up, along the corridor with a document, a
// hand-over, and back; when the walk ends or is aborted (a new run) it is back in its chair.
import { createPortal, useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import { Vector3, type AnimationClip, type Group, type Mesh, type Object3D } from "three";
import { clone as cloneSkinned } from "three/examples/jsm/utils/SkeletonUtils.js";

import { effectiveState, realtimeStore, serverNow } from "@/stores/realtime";

import type { Seat } from "../scene/layout";
import { routeFor, useCues, type Route } from "../visual/CueRunner";
import { visualForAgent, type Pose } from "../visual/mapping";
import { avatarHandlers } from "../interaction/picking";
import type { Outfit } from "../assets/outfits";
import { AvatarController, gazeToward } from "./AvatarController";
import type { Character } from "../assets/characters";
import { dress, strip } from "./dress";
import { isSeated, Standee, standeeLift, type Pictures, type Waiting } from "./Standee";
import { AVATAR_SCALE, SEAT_FORWARD, SEAT_LIFT, SIT_HIP, STAND_BACK } from "./body";

export { AVATAR_SCALE, SEAT_LIFT };
import { courierState } from "./courier";
import { useRoster } from "./roster";

/** The click target around a figure, in model units (the group is scaled by AVATAR_SCALE). */
const HIT_BOX: [number, number, number] = [0.5, 0.95, 0.5];
/** Without events, re-read the store this often (COMPLETED turns IDLE on the clock). */
const RECHECK_MS = 1000;

export interface AvatarModel {
  scene: Object3D;
  animations: AnimationClip[];
}

export function placeFor(seat: Seat, pose: Pose, forward = 0): [number, number, number] {
  // standing up is a step back from the desk: toward +z, or -z at a turned desk (D-119); sitting,
  // ``forward`` nearer the desk (an own figure, D-201)
  const back = seat.turn ? -1 : 1;
  return pose === "stand" ? [seat.chair[0], 0, seat.chair[1] + back * STAND_BACK] : [seat.chair[0], SEAT_LIFT, seat.chair[1] - back * forward];
}

export function AgentAvatar({
  agentId,
  seat,
  model,
  outfit = null,
  figure = null,
  character,
  headScale,
  bodyScale = 1,
}: {
  /** Her figure: what it leaves off applies dressed or not (D-186). */
  character?: Character;
  agentId: string;
  seat: Seat;
  model: AvatarModel;
  /** Dressed as herself (D-115): her own palette and colours on the clone. */
  outfit?: Outfit | null;
  /** Her Q-version pictures (D-118, D-123, D-124): a standee facing the camera instead of the
   * model, standing or seated, from the front or behind. */
  figure?: Pictures | null;
  /** The head bone's scale (default: the pack's figures' smaller heads, T-413). */
  headScale?: number;
  /** How much larger than the pack's figures the model is drawn (an own figure, D-201). */
  bodyScale?: number;
}) {
  const { body, dressed } = useMemo(() => {
    const copy = cloneSkinned(model.scene);
    copy.traverse((o) => {
      if ((o as Mesh).isMesh) o.castShadow = true;
    });
    return { body: copy, dressed: outfit ? dress(copy, outfit) : character ? strip(copy, character) : null };
  }, [model.scene, outfit, character]);
  useEffect(() => () => dressed?.dispose(), [dressed]);
  const controller = useMemo(() => new AvatarController(body, model.animations, headScale), [body, model.animations, headScale]);
  // an own figure's bending arms (D-201): she sits nearer the desk, and carries a document in her hand
  const hand = useMemo(() => body.getObjectByName("forearm-right") ?? null, [body]);
  const forward = hand ? SEAT_FORWARD : 0;
  const eye = useMemo(() => new Vector3(), []);
  const group = useRef<Group>(null);
  const paper = useRef<Mesh>(null);
  const dirty = useRef(true);
  const nextCheck = useRef(0);
  /** Whether she is idle (閒置) - with nothing to do, not waiting on anything - read with her pose. */
  const idle = useRef(true);
  const cues = useCues();
  const roster = useRoster();
  const latestRoster = useRef(roster);
  latestRoster.current = roster;
  const walk = useRef<{ seq: number; startedAt: number; route: Route | null } | null>(null);
  const handlers = useMemo(() => avatarHandlers(agentId), [agentId]);
  const standee = useRef<Group>(null);
  /** What she waits for (D-128), read with her pose: her standee shows it. */
  const waiting = useRef<Waiting>(null);

  useEffect(() => realtimeStore.subscribe(() => void (dirty.current = true)), []);
  useEffect(() => () => controller.dispose(), [controller]);

  useFrame(({ camera }, dt) => {
    const now = performance.now();
    const g = group.current;
    // idle in her seat, an own figure looks at the camera (D-203, D-215): her head turns toward it, up to
    // GAZE_LIMIT either way and not round to look behind her, and lifts toward it as it looks down on her
    // (a share of its height above her, up to GAZE_UP_LIMIT). Busy or waiting, she minds her desk.
    if (hand && g) {
      const looking = idle.current && !walk.current && isSeated(controller.pose);
      [controller.gaze, controller.gazeUp] = gazeToward(g.worldToLocal(eye.copy(camera.position)), looking);
    }

    // a walk cue in progress: the courier
    const active = cues?.queue.walk(agentId);
    if (active && (walk.current?.seq !== active.cue.seq || walk.current.startedAt !== active.startedAt)) {
      walk.current = { seq: active.cue.seq, startedAt: active.startedAt, route: routeFor(active.cue, latestRoster.current) };
    }
    const step = active && walk.current?.route ? courierState(walk.current.route, now - active.startedAt) : null;
    if (step && step.phase !== "done") {
      // at the far end: standing (a hand-over, a coffee), or sitting down (a lounge seat, D-136)
      const seated = step.phase === "handover" && walk.current?.route?.sitting === true;
      controller.setPose(seated ? "sit_idle" : step.phase === "handover" ? "stand" : "walk");
      g?.position.set(step.position[0], seated ? SEAT_LIFT : 0, step.position[1]);
      // stepped out of the office (D-136): out of sight until the walk back begins
      if (g) g.visible = !(step.phase === "handover" && walk.current?.route?.outside === true);
      if (g) g.rotation.y = step.heading;
      if (paper.current) paper.current.visible = step.carrying;
      controller.update(Math.min(dt, 0.1));
      seatModel();
      if (standee.current) standee.current.position.y = standeeLift(controller.pose, now / 1000, Boolean(figure?.sit));
      return;
    }
    if (walk.current) {
      // the walk is over or was aborted: back in the chair, whatever the state says next
      walk.current = null;
      dirty.current = true;
      if (paper.current) paper.current.visible = false;
      if (g) g.rotation.y = seat.facing;
      if (g) g.visible = true; // back in, if it had stepped out
      controller.pose = null;
    }

    if (dirty.current || now >= nextCheck.current) {
      dirty.current = false;
      nextCheck.current = now + RECHECK_MS;
      const state = realtimeStore.getState();
      const agent = state.company?.agents[agentId];
      const at = serverNow(state);
      const pose = (agent && visualForAgent(agent, at)?.pose) || "sit_idle";
      idle.current = !agent?.activity || effectiveState(agent.activity, at) === "IDLE";
      waiting.current =
        agent?.activity?.stored_state === "WAITING" ? (agent.activity.detail.reason === "approval" ? "approval" : "other") : null;
      if (pose !== controller.pose) {
        controller.setPose(pose);
        group.current?.position.set(...placeFor(seat, pose, forward));
      }
    }
    controller.update(Math.min(dt, 0.1));
    seatModel();
    if (standee.current) standee.current.position.y = standeeLift(controller.pose, now / 1000, Boolean(figure?.sit));
  });

  /** A larger model sits a little lower, so its hips stay on the seat. */
  function seatModel() {
    body.position.y = isSeated(controller.pose) ? -(bodyScale - 1) * SIT_HIP : 0;
  }

  return (
    <group
      ref={group}
      position={placeFor(seat, "sit_idle", forward)}
      rotation-y={seat.facing}
      scale={AVATAR_SCALE}
      userData={{ agentId }}
      {...handlers}
    >
      {figure ? (
        <group ref={standee}>
          <Standee pictures={figure} pose={() => controller.pose} waiting={() => waiting.current} />
        </group>
      ) : (
        <primitive object={body} scale={bodyScale} />
      )}
      {/*
        What a click hits: a box a bit larger than the figure (and its chair), never drawn. At the
        overview a figure is a few dozen pixels tall; its mesh alone is a small target (T-413:
        with the smaller head, clicks just under the tag fell on the chair).
      */}
      <mesh name="hit-box" visible={false} position={[0, HIT_BOX[1] / 2, 0]}>
        <boxGeometry args={HIT_BOX} />
      </mesh>
      {/* the document a courier carries: the pack's figures hold it at the chest (model units: the group is scaled) */}
      {hand ? (
        // gripped by its edge in her right fist, hanging flat at her side (the bone's units: the figure's
        // own, so the size of a sheet of A4 once she is drawn at the standees' height)
        createPortal(
          <mesh ref={paper} name="paper" visible={false} position={[-0.17, 0, 0.005]}>
            <boxGeometry args={[0.1, 0.006, 0.072]} />
            <meshStandardMaterial color="#fbfbf7" />
          </mesh>,
          hand,
        )
      ) : (
        <mesh ref={paper} name="paper" visible={false} position={[0, 0.3, 0.17]} rotation-x={-0.35}>
          <boxGeometry args={[0.11, 0.15, 0.01]} />
          <meshStandardMaterial color="#fbfbf7" />
        </mesh>
      )}
    </group>
  );
}
