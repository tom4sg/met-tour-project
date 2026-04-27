"use client";

import { useState, useCallback } from "react";
import type { ArtworkResult } from "../types/search";
import type { TourResponse, GalleryStop } from "../types/tour";
import { generateTour } from "../lib/tourApi";
import GalleryStopCard from "./GalleryStopCard";
import TourMapOverlay from "./TourMapOverlay";

interface TourPanelProps {
  artworks: ArtworkResult[];
  query: string;
}

type TourState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; data: TourResponse }
  | { status: "error"; message: string };

function extractGalleryNumbers(stopLabels: string[]): string[] {
  return stopLabels
    .filter((label) => label.startsWith("Gallery "))
    .map((label) => label.replace("Gallery ", ""));
}

// ---------------------------------------------------------------------------
// PDF Export — opens a new window with a print-ready tour page
// ---------------------------------------------------------------------------
function exportTourPDF(stops: GalleryStop[], query: string) {
  const floors = Array.from(new Set(stops.map((s) => s.floor))).sort();
  const galleryRoute = extractGalleryNumbers(stops.map((s) => s.stop_label));

  const floorSections = floors
    .map((f) => {
      const floorStops = stops.filter((s) => s.floor === f);
      const mapUrl = `https://maps.metmuseum.org/?screenmode=base&floor=${f}`;

      // Build a visual gallery route diagram instead of an iframe
      // (iframes with cross-origin maps cannot render in print/PDF)
      const routeBubbles = floorStops
        .map((stop, i) => {
          const globalIdx = stops.indexOf(stop) + 1;
          const galleryNum = stop.stop_label.replace("Gallery ", "");
          const arrow =
            i < floorStops.length - 1
              ? `<span style="color:#ccc;font-size:20px;margin:0 4px;">→</span>`
              : "";
          return `<span style="display:inline-flex;align-items:center;margin:4px 0;">
            <span style="display:inline-flex;align-items:center;gap:6px;background:#fff;border:2px solid #E31837;border-radius:20px;padding:4px 12px 4px 4px;">
              <span style="width:24px;height:24px;border-radius:50%;background:#E31837;color:white;display:inline-flex;align-items:center;justify-content:center;font-weight:bold;font-size:12px;flex-shrink:0;">${globalIdx}</span>
              <span style="font-size:13px;font-weight:600;color:#1a1a1a;">${galleryNum}</span>
            </span>${arrow}</span>`;
        })
        .join("");

      const stopItems = floorStops
        .map((stop) => {
          const globalIdx = stops.indexOf(stop) + 1;
          const galleryNum = stop.stop_label.startsWith("Gallery ")
            ? stop.stop_label.replace("Gallery ", "")
            : null;
          const artworkList = stop.artworks
            .map(
              (a) =>
                `<li style="margin:2px 0;font-size:13px;"><a href="${a.object_url}" target="_blank" style="color:#1a1a1a;font-weight:500;text-decoration:none;border-bottom:1px solid #ccc;">${a.title}</a>${a.artist_display_name ? ` <span style="color:#888;">— ${a.artist_display_name}</span>` : ""}${a.gallery_number ? ` <span style="background:#f0ece4;border-radius:4px;padding:1px 5px;color:#666;font-size:11px;font-weight:600;">Gallery ${a.gallery_number}</span>` : ""}</li>`,
            )
            .join("");
          return `
          <div style="margin:12px 0;page-break-inside:avoid;border:1px solid #ddd;border-radius:8px;padding:12px 16px;">
            <div style="display:flex;align-items:center;gap:12px;margin-bottom:6px;">
              <div style="width:28px;height:28px;border-radius:50%;background:#E31837;color:white;display:flex;align-items:center;justify-content:center;font-weight:bold;font-size:14px;flex-shrink:0;">${globalIdx}</div>
              <div>
                <div style="font-weight:bold;font-size:15px;">${stop.stop_label}</div>
                <div style="color:#666;font-size:12px;display:flex;align-items:center;gap:8px;">
                  Floor ${stop.floor}
                  ${galleryNum ? `<span style="background:#E31837;color:white;border-radius:4px;padding:1px 7px;font-size:11px;font-weight:700;">Gallery ${galleryNum}</span>` : ""}
                </div>
              </div>
            </div>
            <ul style="margin:0;padding-left:52px;list-style:disc;">${artworkList}</ul>
          </div>`;
        })
        .join("");

      return `
        <h2 style="font-size:18px;color:#E31837;margin-top:28px;margin-bottom:4px;">Floor ${f}</h2>
        <div style="margin-bottom:12px;page-break-inside:avoid;background:#f8f6f1;border:1px solid #e0dcd4;border-radius:10px;padding:16px 20px;">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">
            <span style="font-size:18px;">🗺️</span>
            <span style="font-weight:bold;font-size:14px;color:#1a1a1a;">Gallery Route — Floor ${f}</span>
          </div>
          <div style="display:flex;flex-wrap:wrap;align-items:center;gap:2px;margin-bottom:12px;">${routeBubbles}</div>
          <div style="border-top:1px solid #e0dcd4;padding-top:10px;display:flex;align-items:center;gap:8px;">
            <span style="font-size:14px;">📍</span>
            <span style="font-size:12px;color:#666;">View interactive map: </span>
            <a href="${mapUrl}" style="font-size:12px;color:#E31837;font-weight:600;word-break:break-all;">${mapUrl}</a>
          </div>
        </div>
        ${stopItems}`;
    })
    .join("");

  const html = `<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<title>Met Museum Tour</title>
<style>
  body{font-family:Georgia,serif;margin:40px;color:#1a1a1a;max-width:800px;margin-left:auto;margin-right:auto;}
  h1{font-size:24px;border-bottom:2px solid #E31837;padding-bottom:8px;}
  .summary{background:#f5f0e8;padding:12px 16px;border-radius:8px;margin:16px 0;font-size:13px;}
  .print-btn{display:inline-flex;align-items:center;gap:6px;background:#E31837;color:white;border:none;padding:10px 20px;border-radius:6px;font-size:14px;font-weight:600;cursor:pointer;margin-bottom:24px;}
  .print-btn:hover{opacity:.9;}
  @media print{.no-print{display:none!important;}body{margin:20px;}a{color:#E31837!important;}}
</style>
</head><body>
  <div class="no-print">
    <button class="print-btn" onclick="window.print()">🖨️ Save as PDF / Print</button>
  </div>
  <h1>🏛️ Met Museum Tour</h1>
  ${query ? `<div style="font-size:15px;color:#555;margin-bottom:4px;">Theme: <em>${query}</em></div>` : ""}
  <div class="summary">
    <strong>${stops.length} stop${stops.length !== 1 ? "s" : ""}</strong> across ${floors.length} floor${floors.length !== 1 ? "s" : ""}
    ${galleryRoute.length > 0 ? `<br/>Route: ${galleryRoute.join(" → ")}` : ""}
  </div>
  ${floorSections}
  <p style="margin-top:32px;font-size:11px;color:#aaa;text-align:center;">Generated from Met Museum Tour Planner</p>
</body></html>`;

  const blob = new Blob([html], { type: "text/html" });
  const url = URL.createObjectURL(blob);
  const win = window.open(url, "_blank");
  if (!win) {
    alert("Please allow popups to export your tour as PDF.");
  }
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
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

  const handleExportPDF = useCallback(() => {
    if (state.status === "success") {
      exportTourPDF(state.data.stops, query);
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
  const galleryNumbers = extractGalleryNumbers(
    data.stops.map((s) => s.stop_label),
  );

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

          {/* Gallery route summary */}
          {galleryNumbers.length > 0 && (
            <p className="text-sm text-met-charcoal/60 mb-4">
              Galleries: {galleryNumbers.join(" → ")}
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
