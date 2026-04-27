"use client";

import { useState, useRef, useEffect } from "react";
import type { GalleryStop } from "../types/tour";

// ── Floor plan image dimensions ──────────────────────────────────────────────
const FLOOR_CONFIG = {
  1: { imgW: 1980, imgH: 1520 },
  2: { imgW: 1980, imgH: 1543 },
} as const;

// ── Fallback polynomial transform (Met coord 0-10 → image pixel) ─────────────
// Used only when gallery number is not in the pre-extracted pixel table.
// Coefficients fitted by least-squares from 173 (F1) and 66 (F2) anchor points.
const POLY_COEFF: Record<1 | 2, { x: number[]; y: number[] }> = {
  1: {
    x: [155.2165, 9.9711, 0.6041, 10.9756, -1.6691, -42.042],
    y: [-30.4011, -96.3004, 0.5175, 2.4505, -2.5016, 1416.7289],
  },
  2: {
    x: [235.62, 0, 0, 0, 0, -174.21],
    y: [0, -108.05, 0, 0, 0, 1189.30],
  },
};

function polyToPixel(x: number, y: number, floor: 1 | 2): [number, number] {
  const c = POLY_COEFF[floor];
  const feats = [x, y, x * y, x * x, y * y, 1];
  const px = c.x.reduce((s, ci, i) => s + ci * feats[i], 0);
  const py = c.y.reduce((s, ci, i) => s + ci * feats[i], 0);
  return [px, py];
}

// ── Gallery pixel lookup (loaded once) ───────────────────────────────────────
type PixelTable = Record<string, Record<string, [number, number]>>;
let pixelTableCache: PixelTable | null = null;

async function loadPixelTable(): Promise<PixelTable> {
  if (pixelTableCache) return pixelTableCache;
  const res = await fetch("/met-gallery-pixels.json");
  pixelTableCache = await res.json();
  return pixelTableCache!;
}

const MAP_DEFAULT_HEIGHT = 620; // px
const MAP_HEIGHT_STEP = 80;    // px per click

// ── Design tokens ────────────────────────────────────────────────────────────
const MET_RED = "#E31837";
const STOP_R = 16;

// PDF text positions are the top-left corner of each gallery number label.
// These offsets shift markers to the visual center of the label.
const LABEL_OFFSET_X = 20;
const LABEL_OFFSET_Y = 8;

interface Props {
  stops: GalleryStop[];
}

export default function TourMapInner({ stops }: Props) {
  const pathRef = useRef<SVGPathElement>(null);
  const [hovered, setHovered] = useState<number | null>(null);
  const [pixelTable, setPixelTable] = useState<PixelTable | null>(null);
  const [mapHeight, setMapHeight] = useState(MAP_DEFAULT_HEIGHT);

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

  const floorStops = stops
    .map((s, i) => ({ ...s, globalIndex: i }))
    .filter((s) => s.floor === activeFloor);

  const cfg = FLOOR_CONFIG[activeFloor];
  const metMapUrl = `https://maps.metmuseum.org/?screenmode=base&floor=${activeFloor}`;

  // Resolve pixel position: prefer lookup table, fall back to polynomial
  function stopToPixel(stop: (typeof floorStops)[0]): [number, number] {
    const galleryNum = stop.stop_label.replace("Gallery ", "").trim();
    const entry = pixelTable?.[String(activeFloor)]?.[galleryNum];
    const [px, py] = entry ?? polyToPixel(stop.x, stop.y, activeFloor);
    return [px + LABEL_OFFSET_X, py + LABEL_OFFSET_Y];
  }

  // Animate path draw when floor or stops change
  useEffect(() => {
    const el = pathRef.current;
    if (!el) return;
    const len = el.getTotalLength();
    el.style.transition = "none";
    el.style.strokeDasharray = `${len}`;
    el.style.strokeDashoffset = `${len}`;
    void el.getBoundingClientRect();
    el.style.transition = "stroke-dashoffset 1.1s ease-in-out";
    el.style.strokeDashoffset = "0";
  }, [activeFloor, floorStops.map((s) => s.stop_label).join(","), pixelTable]);

  const pathD =
    floorStops.length > 1 && pixelTable !== null
      ? `M ${floorStops.map((s) => stopToPixel(s).join(",")).join(" L ")}`
      : "";

  return (
    <div className="w-full">
      {/* Floor tabs + size controls */}
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
      </div>

      {/* Map SVG with floor plan background */}
      <div className="w-full rounded-lg border border-met-gold/20 overflow-hidden bg-[#dce9f0]">
        <svg
          viewBox={`0 0 ${cfg.imgW} ${cfg.imgH}`}
          className="w-full h-auto"
          style={{ display: "block", maxHeight: `${mapHeight}px` }}
        >
          <defs>
            <marker
              id="tour-arrow"
              markerWidth="8"
              markerHeight="8"
              refX="6"
              refY="4"
              orient="auto"
            >
              <polygon points="0 0, 8 4, 0 8" fill={MET_RED} opacity={0.75} />
            </marker>
            <filter id="stop-shadow" x="-30%" y="-30%" width="160%" height="160%">
              <feDropShadow dx="0" dy="2" stdDeviation="3" floodOpacity="0.35" />
            </filter>
          </defs>

          {/* Floor plan image — none preserves aspect so it fills viewBox exactly */}
          <image
            href={`/met-floor${activeFloor}.png`}
            x={0}
            y={0}
            width={cfg.imgW}
            height={cfg.imgH}
            preserveAspectRatio="none"
          />

          {/* Tour path */}
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

          {/* Stop circles — two passes so the hovered stop's tooltip renders on top */}
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
                    <circle
                      cx={px}
                      cy={py}
                      r={STOP_R + 7}
                      fill={MET_RED}
                      fillOpacity={0.18}
                    />
                  )}
                  <circle
                    cx={px}
                    cy={py}
                    r={STOP_R}
                    fill={MET_RED}
                    stroke="white"
                    strokeWidth={2.5}
                    filter="url(#stop-shadow)"
                  />
                  <text
                    x={px}
                    y={py + 1}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    fontSize={13}
                    fontWeight="bold"
                    fill="white"
                    fontFamily="system-ui, sans-serif"
                    style={{ userSelect: "none", pointerEvents: "none" }}
                  >
                    {stop.globalIndex + 1}
                  </text>

                  {/* Tooltip — only rendered in second pass so it's always on top */}
                  {isHovered && withTooltip && (
                    <g style={{ pointerEvents: "none" }}>
                      <rect
                        x={tipX}
                        y={py - 14}
                        width={stop.stop_label.length * 7 + 12}
                        height={24}
                        rx={4}
                        fill="#1a1a1a"
                        fillOpacity={0.88}
                      />
                      <text
                        x={tipX + 6}
                        y={py + 1}
                        dominantBaseline="middle"
                        fontSize={12}
                        fill="white"
                        fontFamily="system-ui, sans-serif"
                      >
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

      {/* Stop legend */}
      {floorStops.length > 0 && (
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
              <span className="text-[11px] text-met-charcoal/70">
                {stop.stop_label}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Link to official map */}
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
