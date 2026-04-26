"use client";

import { useEffect, useRef, useState } from "react";
import type { GalleryStop } from "../types/tour";

const STOP_COLOR = "#f97316";
const MAP_HEIGHT = 420;

interface Props {
  stops: GalleryStop[];
}

export default function TourMapInner({ stops }: Props) {
  const iframeRef = useRef<HTMLIFrameElement>(null);

  const [activeFloor, setActiveFloor] = useState<1 | 2>(() => {
    const f1 = stops.filter((s) => s.floor === 1).length;
    const f2 = stops.filter((s) => s.floor === 2).length;
    return f2 > f1 ? 2 : 1;
  });
  const [iframeBlocked, setIframeBlocked] = useState(false);

  const hasF1 = stops.some((s) => s.floor === 1);
  const hasF2 = stops.some((s) => s.floor === 2);
  const metMapUrl = `https://maps.metmuseum.org/?screenmode=base&floor=${activeFloor}`;

  const floorStops = stops
    .map((s, i) => ({ ...s, globalIndex: i }))
    .filter((s) => s.floor === activeFloor);

  // Iframe block detection
  useEffect(() => {
    setIframeBlocked(false);
    const timer = setTimeout(() => {
      try {
        const doc = iframeRef.current?.contentDocument;
        if (doc && doc.body && doc.body.innerHTML.trim() === "") {
          setIframeBlocked(true);
        }
      } catch {
        // cross-origin SecurityError = loaded fine
      }
    }, 4000);
    return () => clearTimeout(timer);
  }, [activeFloor]);

  return (
    <div className="w-full">
      {/* Floor tabs */}
      <div className="flex items-center justify-between gap-2 mb-3">
        <div className="flex gap-2">
          {([1, 2] as const).map((f) => {
            const hasStops = f === 1 ? hasF1 : hasF2;
            return (
              <button
                key={f}
                onClick={() => setActiveFloor(f)}
                className={`text-xs font-semibold px-3 py-1.5 rounded transition-colors
                  ${activeFloor === f ? "bg-met-charcoal text-met-cream" : "bg-met-cream border border-met-gold/30 text-met-charcoal/60 hover:text-met-charcoal"}
                  ${!hasStops ? "opacity-40 cursor-default" : ""}`}
              >
                Floor {f}
                {hasStops && (
                  <span className="ml-1 text-[10px] opacity-70">
                    ({stops.filter((s) => s.floor === f).length})
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Official Met map iframe */}
      <div
        className="w-full rounded-lg border border-met-gold/20 overflow-hidden relative"
        style={{ height: `${MAP_HEIGHT}px` }}
      >
        {!iframeBlocked ? (
          <iframe
            ref={iframeRef}
            src={metMapUrl}
            width="100%"
            height="100%"
            style={{ border: "none", display: "block" }}
            allow="geolocation"
            title={`Met Museum Official Map - Floor ${activeFloor}`}
            onError={() => setIframeBlocked(true)}
          />
        ) : (
          <div className="w-full h-full flex flex-col items-center justify-center gap-4 bg-met-cream/60 px-6 text-center">
            <p className="text-sm text-met-charcoal/70">
              The Met&apos;s map can&apos;t be embedded here due to browser
              security restrictions.
            </p>
            <a
              href={metMapUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-sm font-semibold text-met-cream bg-met-red px-4 py-2 rounded hover:opacity-90 transition-opacity"
            >
              Open Floor {activeFloor} in Met Map ↗
            </a>
          </div>
        )}
      </div>

      {/* Stop legend */}
      {floorStops.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5">
          {floorStops.map((stop) => (
            <div key={stop.stop_label} className="flex items-center gap-1.5">
              <span
                className="inline-flex items-center justify-center w-5 h-5 rounded-full text-[10px] font-bold text-white flex-shrink-0"
                style={{ backgroundColor: STOP_COLOR }}
              >
                {stop.globalIndex + 1}
              </span>
              <span className="text-[11px] text-met-charcoal/70">
                {stop.stop_label}
              </span>
            </div>
          ))}
        </div>
      )}

      <div className="mt-2 flex items-center justify-between">
        <a
          href={metMapUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-met-gold hover:underline"
        >
          Open official Met map ↗
        </a>
        {!iframeBlocked && (
          <span className="text-[10px] text-met-charcoal/40">
            Floor {activeFloor} · maps.metmuseum.org
          </span>
        )}
      </div>
    </div>
  );
}
