"use client";

import { useState, useCallback } from "react";
import type { ArtworkResult } from "../types/search";
import type { TourResponse, GalleryStop } from "../types/tour";
import { generateTour } from "../lib/tourApi";
import GalleryStopCard from "./GalleryStopCard";
import TourMapOverlay from "./TourMapOverlay";
import {
  FLOOR_CONFIG,
  polyToPixel,
  loadPixelTable,
  LABEL_OFFSET_X,
  LABEL_OFFSET_Y,
} from "../lib/mapUtils";

interface TourPanelProps {
  artworks: ArtworkResult[];
  query: string;
}

type TourState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; data: TourResponse }
  | { status: "error"; message: string };


function galleryRoute(stops: GalleryStop[]): string[] {
  return stops
    .filter((s) => s.stop_label.startsWith("Gallery "))
    .map((s) => s.stop_label.replace("Gallery ", ""));
}

async function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(reader.result as string);
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

async function exportTourPDF(stops: GalleryStop[], query: string, excludedCount = 0) {
  const pixelTable = await loadPixelTable();
  const floors = Array.from(new Set(stops.map((s) => s.floor))).sort() as (1 | 2)[];
  const MET_RED = "#E31837";
  const STOP_R = 16;

  function resolvePixel(stop: GalleryStop & { globalIndex: number }, floor: 1 | 2): [number, number] {
    const galleryNum = stop.stop_label.replace("Gallery ", "").trim();
    const entry = pixelTable[String(floor)]?.[galleryNum];
    const [px, py] = entry ?? polyToPixel(stop.x, stop.y, floor);
    return [px + LABEL_OFFSET_X, py + LABEL_OFFSET_Y];
  }

  // Embed floor images as base64 so they always render in print
  const floorDataUrls: Record<number, string> = {};
  await Promise.all(
    floors.map(async (f) => {
      const res = await fetch(`/met-floor${f}.png`);
      const blob = await res.blob();
      floorDataUrls[f] = await blobToDataUrl(blob);
    }),
  );

  const stopsWithIdx = stops.map((s, i) => ({ ...s, globalIndex: i }));

  const floorSections = floors
    .map((f) => {
      const cfg = FLOOR_CONFIG[f];
      const floorStops = stopsWithIdx.filter((s) => s.floor === f);

      const pathD =
        floorStops.length > 1
          ? `M ${floorStops.map((s) => resolvePixel(s, f).join(",")).join(" L ")}`
          : "";

      const circles = floorStops
        .map((s) => {
          const [px, py] = resolvePixel(s, f);
          return `<circle cx="${px}" cy="${py}" r="${STOP_R}" fill="${MET_RED}" stroke="white" stroke-width="2.5"/>
<text x="${px}" y="${py}" text-anchor="middle" dominant-baseline="middle" font-size="13" font-weight="bold" fill="white" font-family="system-ui,sans-serif">${s.globalIndex + 1}</text>`;
        })
        .join("");

      const mapSvg = `<svg viewBox="0 0 ${cfg.imgW} ${cfg.imgH}" style="width:100%;display:block;border:1px solid #ddd;">
  <image href="${floorDataUrls[f]}" x="0" y="0" width="${cfg.imgW}" height="${cfg.imgH}" preserveAspectRatio="none"/>
  ${pathD ? `<path d="${pathD}" stroke="${MET_RED}" stroke-width="4" fill="none" stroke-linecap="round" stroke-linejoin="round" stroke-opacity="0.85"/>` : ""}
  ${circles}
</svg>`;

      const stopItems = floorStops
        .map((stop) => {
          const artworkItems = stop.artworks
            .map(
              (a) =>
                `<li><a href="${a.object_url}" target="_blank">${a.title}</a>${a.artist_display_name ? ` <span class="artist">— ${a.artist_display_name}</span>` : ""}</li>`,
            )
            .join("");
          return `<div class="stop">
  <div class="stop-header">
    <span class="stop-num">${stop.globalIndex + 1}</span>
    <span class="stop-name">${stop.stop_label}</span>
  </div>
  <ul class="artworks">${artworkItems}</ul>
</div>`;
        })
        .join("");

      return `<h2>Floor ${f}</h2>
<div class="map-wrap">${mapSvg}</div>
${stopItems}`;
    })
    .join("");

  const CREAM = "#F5F0E8";
  const CHARCOAL = "#1A1A1A";
  const GOLD = "#C9A84C";
  const route = galleryRoute(stops);

  const html = `<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<title>Met Museum Tour${query ? ` — ${query}` : ""}</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0;}
  body{font-family:Georgia,"Times New Roman",serif;color:${CHARCOAL};background:${CREAM};max-width:840px;margin:0 auto;padding:48px 40px;}
  h1{font-size:24px;font-weight:normal;letter-spacing:.02em;padding-bottom:12px;border-bottom:2px solid ${GOLD};margin-bottom:8px;}
  .theme{font-size:15px;color:#555;margin-bottom:4px;font-style:italic;}
  .meta{font-size:12px;color:#888;margin-bottom:36px;}
  h2{font-size:10px;font-weight:bold;letter-spacing:.14em;text-transform:uppercase;color:${MET_RED};margin:40px 0 14px;}
  .map-wrap{margin-bottom:28px;}
  .stop{padding:12px 0;border-bottom:1px solid rgba(201,168,76,.25);}
  .stop:last-child{border-bottom:none;}
  .stop-header{display:flex;align-items:center;gap:10px;margin-bottom:8px;}
  .stop-num{font-size:11px;font-weight:bold;color:white;background:${MET_RED};border-radius:50%;width:22px;height:22px;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;}
  .stop-name{font-size:15px;font-weight:bold;}
  .artworks{list-style:none;padding-left:32px;}
  .artworks li{font-size:11px;line-height:1.7;}
  .artworks a{color:${CHARCOAL};text-decoration:none;border-bottom:1px solid ${GOLD};}
  .artist{color:#888;}
  .excluded{font-size:12px;color:#aaa;text-align:center;margin-top:36px;padding-top:20px;border-top:1px solid rgba(201,168,76,.25);}
  .print-btn{position:fixed;top:20px;right:20px;background:${MET_RED};color:white;border:none;padding:10px 22px;font-size:13px;font-family:Georgia,serif;cursor:pointer;letter-spacing:.06em;}
  @media print{.print-btn{display:none!important;}body{padding:20px;background:white;}h2{margin-top:24px;}}
</style>
</head><body>
<button class="print-btn" onclick="window.print()">Save as PDF</button>
<h1>The Metropolitan Museum of Art</h1>
${query ? `<p class="theme">${query}</p>` : ""}
<p class="meta">${stops.length} stop${stops.length !== 1 ? "s" : ""} · ${floors.length} floor${floors.length !== 1 ? "s" : ""}${route.length > 0 ? ` · Galleries ${route.join(" → ")}` : ""}</p>
${floorSections}
${excludedCount > 0 ? `<p class="excluded">${excludedCount} artwork${excludedCount !== 1 ? "s" : ""} could not be located in the museum.</p>` : ""}
</body></html>`;

  const blob = new Blob([html], { type: "text/html" });
  const url = URL.createObjectURL(blob);
  const win = window.open(url, "_blank");
  if (!win) alert("Please allow popups to export your tour as PDF.");
  setTimeout(() => URL.revokeObjectURL(url), 120_000);
}

export default function TourPanel({ artworks, query }: TourPanelProps) {
  const [state, setState] = useState<TourState>({ status: "idle" });

  async function handleGenerateTour() {
    setState({ status: "loading" });
    try {
      const data = await generateTour(artworks);
      setState({ status: "success", data });
    } catch (err) {
      const message =
        err instanceof Error
          ? err.message
          : "Tour generation failed. Please try again.";
      setState({ status: "error", message });
    }
  }

  function handleRetry() {
    setState({ status: "idle" });
  }

  const handleExportPDF = useCallback(async () => {
    if (state.status === "success") {
      try {
        await exportTourPDF(state.data.stops, query, state.data.excluded_count);
      } catch {
        alert("Could not generate PDF. Please try again.");
      }
    }
  }, [state, query]);

  if (state.status === "idle") {
    if (artworks.length === 0) return null;
    return (
      <div className="w-full px-4 py-6 flex justify-center">
        <button
          onClick={handleGenerateTour}
          className="
            bg-met-red text-white font-semibold text-sm px-6 py-3 rounded
            hover:bg-met-red/90 active:scale-95
            transition-all duration-150
            min-h-[44px] min-w-[44px]
          "
        >
          Generate Tour
        </button>
      </div>
    );
  }

  if (state.status === "loading") {
    return (
      <div className="flex flex-col items-center justify-center w-full py-12 gap-4">
        <div className="relative w-10 h-10">
          <div className="absolute inset-0 rounded-full border-4 border-met-gold/20" />
          <div className="absolute inset-0 rounded-full border-4 border-t-met-gold animate-spin" />
        </div>
        <p className="text-met-charcoal/70 text-sm tracking-wide">
          Planning your tour…
        </p>
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="w-full px-4 py-6 flex flex-col items-center gap-4">
        <p className="text-sm text-met-charcoal/80 text-center">
          {state.message}
        </p>
        <button
          onClick={handleRetry}
          className="
            border border-met-red text-met-red font-semibold text-sm px-5 py-2.5 rounded
            hover:bg-met-red hover:text-white
            transition-all duration-150
            min-h-[44px] min-w-[44px]
          "
        >
          Try Again
        </button>
      </div>
    );
  }

  // success
  const { data } = state;
  const route = galleryRoute(data.stops);

  return (
    <section className="bg-met-cream w-full px-4 py-6">
      {/* Divider */}
      <div className="h-px bg-met-gold/30 mb-6" aria-hidden="true" />

      {data.stops.length === 0 ? (
        <p className="text-sm text-met-charcoal/70 text-center py-8">
          None of your search results could be located in the museum.
        </p>
      ) : (
        <>
          {/* Summary row */}
          <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
            <p className="text-base font-semibold text-met-charcoal">
              {data.stops.length} {data.stops.length === 1 ? "stop" : "stops"}
            </p>

            <div className="flex items-center gap-3">
              {/* Export PDF button */}
              <button
                onClick={handleExportPDF}
                className="
                  inline-flex items-center gap-1.5 text-sm font-semibold
                  px-3 py-1.5 rounded border border-met-charcoal/20
                  text-met-charcoal hover:bg-met-charcoal hover:text-met-cream
                  transition-colors duration-150
                "
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="7 10 12 15 17 10" />
                  <line x1="12" y1="15" x2="12" y2="3" />
                </svg>
                Export PDF
              </button>

              {/* Map link */}
              <a
                href="https://maps.metmuseum.org"
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-met-gold font-medium hover:underline"
              >
                Open Met Map ↗
              </a>
            </div>
          </div>

          {/* Gallery route */}
          {route.length > 0 && (
            <p className="text-[11px] text-met-charcoal/50 mb-4 leading-relaxed tracking-wide">
              {route.join(" · ")}
            </p>
          )}

          {/* Map */}
          <div className="mb-6">
            <TourMapOverlay stops={data.stops} />
          </div>

          {/* Stop list */}
          <ol className="flex flex-col gap-4">
            {data.stops.map((stop, index) => (
              <li key={`${stop.stop_label}-${index}`}>
                <GalleryStopCard stop={stop} stopNumber={index + 1} />
              </li>
            ))}
          </ol>

          {/* Excluded count note */}
          {data.excluded_count > 0 && (
            <p className="text-xs text-met-charcoal/60 mt-4 text-center">
              {data.excluded_count}{" "}
              {data.excluded_count === 1 ? "artwork" : "artworks"} could not be
              located in the museum.
            </p>
          )}
        </>
      )}
    </section>
  );
}
