"use client";

import { useState, useRef, useEffect } from "react";
import type { GalleryStop } from "../types/tour";
import {
  FLOOR_CONFIG,
  polyToPixel,
  loadPixelTable,
  LABEL_OFFSET_X,
  LABEL_OFFSET_Y,
} from "../lib/mapUtils";
import type { PixelTable } from "../lib/mapUtils";

const MAP_DEFAULT_HEIGHT = 620;
const MAP_HEIGHT_STEP = 80;

const MET_RED = "#E31837";
const STOP_R = 16;

type ViewMode = "interactive" | "route";

interface Props {
  stops: GalleryStop[];
}

export default function TourMapInner({ stops }: Props) {
  const pathRef = useRef<SVGPathElement>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  const [viewMode, setViewMode] = useState<ViewMode>("interactive");
  const [hovered, setHovered] = useState<number | null>(null);
  const [pixelTable, setPixelTable] = useState<PixelTable | null>(null);
  const [mapHeight, setMapHeight] = useState(MAP_DEFAULT_HEIGHT);
  const [iframeBlocked, setIframeBlocked] = useState(false);

  const [activeFloor, setActiveFloor] = useState<1 | 2>(() => {
    const f1 = stops.filter((s) => s.floor === 1).length;
    const f2 = stops.filter((s) => s.floor === 2).length;
    return f2 > f1 ? 2 : 1;
  });

  const hasF1 = stops.some((s) => s.floor === 1);
  const hasF2 = stops.some((s) => s.floor === 2);

  useEffect(() => {
    loadPixelTable().then(setPixelTable);
  }, []);

  // Iframe block detection
  useEffect(() => {
    if (viewMode !== "interactive") return;
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
  }, [viewMode, activeFloor]);

  const floorStops = stops
    .map((s, i) => ({ ...s, globalIndex: i }))
    .filter((s) => s.floor === activeFloor);

  const cfg = FLOOR_CONFIG[activeFloor];
  const metMapUrl = `https://maps.metmuseum.org/?screenmode=base&floor=${activeFloor}`;

  function stopToPixel(stop: (typeof floorStops)[0]): [number, number] {
    const galleryNum = stop.stop_label.replace("Gallery ", "").trim();
    const entry = pixelTable?.[String(activeFloor)]?.[galleryNum];
    const [px, py] = entry ?? polyToPixel(stop.x, stop.y, activeFloor);
    return [px + LABEL_OFFSET_X, py + LABEL_OFFSET_Y];
  }

  useEffect(() => {
    if (viewMode !== "route") return;
    const el = pathRef.current;
    if (!el) return;
    const len = el.getTotalLength();
    el.style.transition = "none";
    el.style.strokeDasharray = `${len}`;
    el.style.strokeDashoffset = `${len}`;
    void el.getBoundingClientRect();
    el.style.transition = "stroke-dashoffset 1.1s ease-in-out";
    el.style.strokeDashoffset = "0";
  }, [viewMode, activeFloor, floorStops.map((s) => s.stop_label).join(","), pixelTable]);

  const pathD =
    floorStops.length > 1 && pixelTable !== null
      ? `M ${floorStops.map((s) => stopToPixel(s).join(",")).join(" L ")}`
      : "";

  const tabBtn = (mode: ViewMode, label: string) => (
    <button
      onClick={() => setViewMode(mode)}
      className={`text-xs font-semibold px-3 py-1.5 rounded transition-colors ${
        viewMode === mode
          ? "bg-met-red text-white"
          : "bg-met-cream border border-met-gold/30 text-met-charcoal/60 hover:text-met-charcoal"
      }`}
    >
      {label}
    </button>
  );

  const floorBtn = (f: 1 | 2) => {
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
  };

  return (
    <div className="w-full">
      {/* View mode tabs */}
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="flex gap-2">
          {tabBtn("interactive", "Interactive Map")}
          {tabBtn("route", "Tour Route")}
        </div>
      </div>

      {/* Floor tabs + size controls */}
      <div className="flex items-center justify-between gap-2 mb-3">
        <div className="flex gap-2">
          {([1, 2] as const).map(floorBtn)}
        </div>
        {viewMode === "route" && (
          <div className="flex items-center gap-1">
            <button
              onClick={() => setMapHeight((h) => Math.max(200, h - MAP_HEIGHT_STEP))}
              className="w-7 h-7 flex items-center justify-center rounded border border-met-charcoal/20 text-met-charcoal/60 hover:bg-met-charcoal/10 text-base leading-none"
              title="Shrink map"
            >−</button>
            <button
              onClick={() => setMapHeight((h) => Math.min(1200, h + MAP_HEIGHT_STEP))}
              className="w-7 h-7 flex items-center justify-center rounded border border-met-charcoal/20 text-met-charcoal/60 hover:bg-met-charcoal/10 text-base leading-none"
              title="Grow map"
            >+</button>
          </div>
        )}
      </div>

      {/* ── Interactive iframe ── */}
      {viewMode === "interactive" && (
        <div
          className="w-full rounded-lg border border-met-gold/20 overflow-hidden"
          style={{ height: `${mapHeight}px` }}
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
                The Met&apos;s map can&apos;t be embedded here due to browser security restrictions.
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
      )}

      {/* ── Route overlay ── */}
      {viewMode === "route" && (
        <div className="w-full rounded-lg border border-met-gold/20 overflow-hidden bg-[#dce9f0]">
          <svg
            viewBox={`0 0 ${cfg.imgW} ${cfg.imgH}`}
            className="w-full h-auto"
            style={{ display: "block", maxHeight: `${mapHeight}px` }}
          >
            <defs>
              <marker id="tour-arrow" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
                <polygon points="0 0, 8 4, 0 8" fill={MET_RED} opacity={0.75} />
              </marker>
              <filter id="stop-shadow" x="-30%" y="-30%" width="160%" height="160%">
                <feDropShadow dx="0" dy="2" stdDeviation="3" floodOpacity="0.35" />
              </filter>
            </defs>

            <image
              href={`/met-floor${activeFloor}.png`}
              x={0} y={0}
              width={cfg.imgW} height={cfg.imgH}
              preserveAspectRatio="none"
            />

            {pathD && (
              <path
                ref={pathRef}
                d={pathD}
                stroke={MET_RED}
                strokeWidth={4}
                fill="none"
                strokeLinejoin="round"
                strokeLinecap="round"
                strokeOpacity={0.85}
                markerMid="url(#tour-arrow)"
              />
            )}

            {pixelTable !== null && (() => {
              const renderStop = (stop: typeof floorStops[0], withTooltip: boolean) => {
                const [px, py] = stopToPixel(stop);
                const isHovered = hovered === stop.globalIndex;
                const tipRight = px + 22 + stop.stop_label.length * 7 + 12;
                const tipX =
                  tipRight > cfg.imgW - 4
                    ? px - 22 - (stop.stop_label.length * 7 + 12)
                    : px + 20;
                return (
                  <g
                    key={stop.stop_label}
                    onMouseEnter={() => setHovered(stop.globalIndex)}
                    onMouseLeave={() => setHovered(null)}
                    style={{ cursor: "default" }}
                  >
                    {isHovered && (
                      <circle cx={px} cy={py} r={STOP_R + 7} fill={MET_RED} fillOpacity={0.18} />
                    )}
                    <circle cx={px} cy={py} r={STOP_R} fill={MET_RED} stroke="white" strokeWidth={2.5} filter="url(#stop-shadow)" />
                    <text
                      x={px} y={py + 1}
                      textAnchor="middle" dominantBaseline="middle"
                      fontSize={13} fontWeight="bold" fill="white"
                      fontFamily="system-ui, sans-serif"
                      style={{ userSelect: "none", pointerEvents: "none" }}
                    >
                      {stop.globalIndex + 1}
                    </text>
                    {isHovered && withTooltip && (
                      <g style={{ pointerEvents: "none" }}>
                        <rect x={tipX} y={py - 14} width={stop.stop_label.length * 7 + 12} height={24} rx={4} fill="#1a1a1a" fillOpacity={0.88} />
                        <text x={tipX + 6} y={py + 1} dominantBaseline="middle" fontSize={12} fill="white" fontFamily="system-ui, sans-serif">
                          {stop.stop_label}
                        </text>
                      </g>
                    )}
                  </g>
                );
              };
              return (
                <>
                  {floorStops.filter((s) => hovered !== s.globalIndex).map((s) => renderStop(s, false))}
                  {floorStops.filter((s) => hovered === s.globalIndex).map((s) => renderStop(s, true))}
                </>
              );
            })()}
          </svg>
        </div>
      )}

      {/* Stop legend (route view only) */}
      {viewMode === "route" && floorStops.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5">
          {floorStops.map((stop) => (
            <div
              key={stop.stop_label}
              className="flex items-center gap-1.5"
              onMouseEnter={() => setHovered(stop.globalIndex)}
              onMouseLeave={() => setHovered(null)}
            >
              <span
                className="inline-flex items-center justify-center w-5 h-5 rounded-full text-[10px] font-bold text-white flex-shrink-0"
                style={{ backgroundColor: MET_RED }}
              >
                {stop.globalIndex + 1}
              </span>
              <span className="text-[11px] text-met-charcoal/70">{stop.stop_label}</span>
            </div>
          ))}
        </div>
      )}

      {/* Footer link */}
      <div className="mt-2 flex items-center justify-between">
        <a
          href={metMapUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-met-gold hover:underline"
        >
          Open official Met map ↗
        </a>
        <span className="text-[10px] text-met-charcoal/40">
          Floor {activeFloor} · maps.metmuseum.org
        </span>
      </div>
    </div>
  );
}
