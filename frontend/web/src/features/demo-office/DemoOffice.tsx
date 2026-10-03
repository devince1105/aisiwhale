// The demo office on the public site (D-155): the back office's 3D office, playing a script.
// Nothing here talks to the API: the store is filled by the player alone, and emptied again when
// the page goes, so the demo never reaches the back office (which uses the same store).
"use client";

import { useEffect, useLayoutEffect, useState } from "react";

import { OfficeCanvas, terminalVars, type OfficeView } from "@/office3d/OfficeCanvas";
import { realtimeStore } from "@/stores/realtime";
import { uiStore } from "@/stores/ui";

import { createDemoPlayer, type Script } from "./player";
import scriptJson from "./script.json";

const SCRIPT = scriptJson as Script;

export function DemoOffice({ lang }: { lang: string }) {
  const [ready, setReady] = useState(false);
  const [view, setView] = useState<OfficeView>("auto");
  const [mode, setMode] = useState<"2d" | "3d">("3d");

  // before paint: the office is drawn with its people already in it, never empty for a frame
  useLayoutEffect(() => {
    const player = createDemoPlayer({ store: realtimeStore.getState(), script: SCRIPT });
    player.start();
    setReady(true);
    // a hidden tab plays nothing, and picks up where it was when it comes back
    const onVisible = () => (document.visibilityState === "visible" ? player.resume() : player.pause());
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      player.stop();
      uiStore.getState().reset();
      setReady(false);
    };
  }, []);

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
      {ready ? <OfficeCanvas view={view} onViewChange={setView} onMode={setMode} departmentNames={names} /> : null}
    </div>
  );
}
