"use client";

import dynamic from "next/dynamic";
import type { GalleryStop } from "../types/tour";

interface TourMapOverlayProps {
  stops: GalleryStop[];
}

// Leaflet touches `window` on import, so it must be loaded client-side only.
const TourMapInner = dynamic(() => import("./TourMapInner"), {
  ssr: false,
  loading: () => (
    <div
      className="w-full rounded-lg border border-met-gold/20 bg-[#e8ede8] flex items-center justify-center"
      style={{ aspectRatio: "16/10" }}
    >
      <p className="text-xs text-met-charcoal/50">Loading map…</p>
    </div>
  ),
});

export default function TourMapOverlay({ stops }: TourMapOverlayProps) {
  return <TourMapInner stops={stops} />;
}
