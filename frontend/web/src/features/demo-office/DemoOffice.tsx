// The demo office on the public site (D-155): the back office's 3D office, playing a script.
// Nothing here talks to the API: the store is filled by the player alone, and emptied again when
// the page goes, so the demo never reaches the back office (which uses the same store).
"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";

import { OfficeCanvas, terminalVars, type OfficeView } from "@/office3d/OfficeCanvas";
import { realtimeStore } from "@/stores/realtime";
import { uiStore } from "@/stores/ui";

import { createDemoPlayer, type Script } from "./player";
import scriptJson from "./script.json";

const SCRIPT = scriptJson as Script;

/**
 * ``active``: whether its page is on screen. A kept office (D-176) lives on while the reader is
 * elsewhere on the site: then the script waits and nothing is drawn.
 */
export function DemoOffice({ lang, active = true }: { lang: string; active?: boolean }) {
  const [ready, setReady] = useState(false);
  const player = useRef<ReturnType<typeof createDemoPlayer> | null>(null);
  const shown = useRef(active);
  shown.current = active;
  const [view, setView] = useState<OfficeView>("auto");
  const [mode, setMode] = useState<"2d" | "3d">("3d");

  // before paint: the office is drawn with its people already in it, never empty for a frame
  useLayoutEffect(() => {
    const playing = createDemoPlayer({ store: realtimeStore.getState(), script: SCRIPT });
    player.current = playing;
    playing.start();
    if (!shown.current) playing.pause();
    setReady(true);
    // a hidden tab plays nothing, and picks up where it was when it comes back
    const onVisible = () =>
      document.visibilityState === "visible" && shown.current ? playing.resume() : playing.pause();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      playing.stop();
      player.current = null;
      uiStore.getState().reset();
      setReady(false);
    };
  }, []);

  useEffect(() => {
    if (active && document.visibilityState === "visible") player.current?.resume();
    else player.current?.pause();
  }, [active]);

  // a click on someone selects her; the demo has no panel to open, so the selection is let go
  useEffect(() => uiStore.subscribe((state) => {
    if (state.selectedAgentId) uiStore.getState().selectAgent(null);
  }), []);

  const names = SCRIPT.department_names[lang] ?? SCRIPT.department_names["zh-TW"];
  return (
    // D-174: no colour of its own in 3D — the office's transparent backdrop shows the page
    <div
      className={`relative h-[70dvh] min-h-[480px] overflow-hidden rounded-xl border border-line ${mode === "2d" ? "bg-canvas" : ""}`}
      data-terminal={mode === "2d"}
      style={mode === "2d" ? terminalVars() : undefined}
      data-testid="demo-office"
    >
      {ready ? <OfficeCanvas view={view} onViewChange={setView} onMode={setMode} departmentNames={names} paused={!active} /> : null}
    </div>
  );
}
