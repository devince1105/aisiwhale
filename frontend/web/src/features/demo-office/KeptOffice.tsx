// The AI 編輯部 kept between pages on a computer that can afford it (D-176).
//
// Leaving a page unmounts it, and with it the 3D office's canvas: coming back, the browser hands
// the GPU the same models again before the first frame (D-175). On a computer with the memory and
// cores to spare, the office is kept instead: one office lives in the site's layout, rendered into
// a node of its own; on the AI 編輯部 page that node is moved into the page, and elsewhere it is
// parked off screen — paused, drawing nothing, its WebGL context and the demo's place in the
// script kept. Moving a node does not remount what React rendered into it, so coming back is
// immediate. Phones and older computers are not asked to hold a GPU's worth of office while the
// reader is on an article: there the page renders its own office, as before.
"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { create } from "zustand";

import { NARROW_QUERY } from "@/office3d/OfficeCanvas";

import { DemoOffice } from "./DemoOffice";

/** The page's place for the kept office, while the AI 編輯部 page is shown. */
export const keptOffice = create<{ wanted: boolean; slot: HTMLElement | null }>(() => ({
  wanted: false,
  slot: null,
}));

export const KEEP_MIN_CORES = 8;
export const KEEP_MIN_MEMORY_GB = 8;

/** A computer, not a phone or a tablet, with the cores and — where the browser says — the memory
 * to keep a 3D office it is not showing. Safari and Firefox do not say how much memory: cores
 * then decide alone. */
export function keepsOfficeAlive(win: Window = window): boolean {
  const nav = win.navigator as Navigator & { deviceMemory?: number };
  const media = (query: string) => win.matchMedia?.(query).matches ?? false;
  if (media(NARROW_QUERY) || !media("(pointer: fine)")) return false;
  if ((nav.hardwareConcurrency ?? 0) < KEEP_MIN_CORES) return false;
  return nav.deviceMemory === undefined || nav.deviceMemory >= KEEP_MIN_MEMORY_GB;
}

const FRAME = "h-[70dvh] min-h-[480px]";

/** On the AI 編輯部 page: the office itself, or — where it is kept — the place it moves into. */
export function OfficeSlot({ lang, keep = keepsOfficeAlive }: { lang: string; keep?: () => boolean }) {
  const [kept, setKept] = useState<boolean | null>(null);
  const place = useRef<HTMLDivElement>(null);
  useEffect(() => setKept(keep()), [keep]);
  useLayoutEffect(() => {
    if (!kept || !place.current) return;
    keptOffice.setState({ wanted: true, slot: place.current });
    return () => keptOffice.setState({ slot: null });
  }, [kept]);
  if (kept === false) return <DemoOffice lang={lang} />;
  return <div ref={place} className={FRAME} data-testid="office-slot" />;
}

/** In the site's layout: renders the kept office once a page wanted it, and moves it about. */
export function KeptOffice({ lang }: { lang: string }) {
  const wanted = keptOffice((s) => s.wanted);
  const slot = keptOffice((s) => s.slot);
  const [host, setHost] = useState<HTMLDivElement | null>(null);
  const park = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!wanted || host) return;
    const node = document.createElement("div");
    node.className = "h-full";
    setHost(node);
  }, [wanted, host]);

  useLayoutEffect(() => {
    if (!host || !park.current) return;
    if (slot) {
      slot.appendChild(host);
      return;
    }
    // parked at the size it had, so coming back does not resize the canvas
    const { width, height } = host.getBoundingClientRect();
    if (width && height) Object.assign(park.current.style, { width: `${width}px`, height: `${height}px` });
    park.current.appendChild(host);
  }, [host, slot]);

  // leaving the site's pages altogether (the back office): the office goes with them
  useEffect(() => () => keptOffice.setState({ wanted: false, slot: null }), []);

  return (
    <>
      <div ref={park} aria-hidden className="pointer-events-none invisible fixed top-0 -left-[10000px] h-[70dvh] w-[1100px]" />
      {host ? createPortal(<DemoOffice lang={lang} active={slot !== null} />, host) : null}
    </>
  );
}
