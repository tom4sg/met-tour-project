"use client";

import { useEffect, useRef, useCallback, useState } from "react";
import type { VizDataResponse, SearchViz } from "../types/viz";

type Projection = "pca" | "umap";

interface Props {
  backdrop: VizDataResponse | null;
  viz: SearchViz | null;
  isLoading?: boolean;
}

function clusterColors(n: number): string[] {
  return Array.from({ length: n }, (_, i) => {
    const hue = Math.round((i * 360) / n);
    return `hsl(${hue}, 65%, 55%)`;
  });
}

function scaleCoords(
  points: [number, number][],
  bounds: { xMin: number; xMax: number; yMin: number; yMax: number },
  W: number,
  H: number,
  pad: number,
): [number, number][] {
  const { xMin, xMax, yMin, yMax } = bounds;
  const xRange = xMax - xMin || 1;
  const yRange = yMax - yMin || 1;
  const inner = 1 - 2 * pad;
  return points.map(([x, y]) => [
    ((x - xMin) / xRange) * W * inner + W * pad,
    H - (((y - yMin) / yRange) * H * inner + H * pad),
  ]);
}

export default function ClusterViz({ backdrop, viz, isLoading }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [projection, setProjection] = useState<Projection>("pca");

  // Viewport state stored in refs to avoid re-render on every drag frame
  const panRef = useRef({ x: 0, y: 0 });
  const zoomRef = useRef(1);
  const dragRef = useRef({ active: false, lastX: 0, lastY: 0 });

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || !backdrop) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const W = canvas.width;
    const H = canvas.height;
    if (W === 0 || H === 0) return;
    const dpr = window.devicePixelRatio || 1;
    // Logical (CSS-pixel) dimensions
    const lW = W / dpr;
    const lH = H / dpr;

    ctx.save();
    ctx.clearRect(0, 0, W, H);
    ctx.scale(dpr, dpr);

    // Pan/zoom: zoom around canvas centre
    const { x: panX, y: panY } = panRef.current;
    const zoom = zoomRef.current;
    ctx.translate(lW / 2 + panX, lH / 2 + panY);
    ctx.scale(zoom, zoom);
    ctx.translate(-lW / 2, -lH / 2);

    const backdropPoints =
      projection === "pca" ? backdrop.backdrop_pca : backdrop.backdrop_umap;
    const queryPos = viz
      ? projection === "pca"
        ? viz.query_pca
        : viz.query_umap
      : null;
    const resultPositions: [number, number][] = viz
      ? projection === "pca"
        ? viz.results_pca
        : viz.results_umap
      : [];

    const xs = backdropPoints.map((p) => p[0]);
    const ys = backdropPoints.map((p) => p[1]);
    const bounds = {
      xMin: Math.min(...xs),
      xMax: Math.max(...xs),
      yMin: Math.min(...ys),
      yMax: Math.max(...ys),
    };
    const pad = 0.06;
    const colors = clusterColors(backdrop.n_clusters);

    // Keep visual radii constant in screen space regardless of zoom
    const dotR = 2.5 / zoom;
    const ringR = 7 / zoom;
    const queryR = 9 / zoom;
    const lw = 2 / zoom;

    // Batch draws by cluster
    const byCluster = new Map<number, [number, number][]>();
    for (const [x, y, cid] of backdropPoints) {
      if (!byCluster.has(cid)) byCluster.set(cid, []);
      byCluster.get(cid)!.push([x, y]);
    }
    ctx.globalAlpha = 0.6;
    for (const [cid, pts] of byCluster) {
      ctx.fillStyle = colors[cid % colors.length];
      ctx.beginPath();
      for (const [x, y] of pts) {
        const [[cx, cy]] = scaleCoords([[x, y]], bounds, lW, lH, pad);
        ctx.moveTo(cx + dotR, cy);
        ctx.arc(cx, cy, dotR, 0, Math.PI * 2);
      }
      ctx.fill();
    }
    ctx.globalAlpha = 1;

    // Gold rings on results
    const scaledResults = scaleCoords(
      resultPositions.map((p) => [p[0], p[1]]),
      bounds,
      lW,
      lH,
      pad,
    );
    ctx.strokeStyle = "#b8972e";
    ctx.lineWidth = lw;
    for (const [cx, cy] of scaledResults) {
      ctx.beginPath();
      ctx.arc(cx, cy, ringR, 0, Math.PI * 2);
      ctx.stroke();
    }

    // Red query dot
    if (queryPos) {
      const [[cx, cy]] = scaleCoords(
        [[queryPos[0], queryPos[1]]],
        bounds,
        lW,
        lH,
        pad,
      );
      ctx.fillStyle = "#c41e3a";
      ctx.strokeStyle = "#fff";
      ctx.lineWidth = lw;
      ctx.beginPath();
      ctx.arc(cx, cy, queryR, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
    }

    ctx.restore();
  }, [backdrop, viz, projection]);

  // Resize observer — sets physical canvas pixels = CSS pixels × DPR
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const ro = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      const canvas = canvasRef.current;
      if (!canvas) return;
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      draw();
    });
    ro.observe(container);
    return () => ro.disconnect();
  }, [draw]);

  useEffect(() => {
    draw();
  }, [draw]);

  // ── Mouse interaction ──────────────────────────────────────────────────

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    dragRef.current = { active: true, lastX: e.clientX, lastY: e.clientY };
  }, []);

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (!dragRef.current.active) return;
      panRef.current.x += e.clientX - dragRef.current.lastX;
      panRef.current.y += e.clientY - dragRef.current.lastY;
      dragRef.current.lastX = e.clientX;
      dragRef.current.lastY = e.clientY;
      draw();
    },
    [draw],
  );

  const handleMouseUp = useCallback(() => {
    dragRef.current.active = false;
  }, []);

  const handleWheel = useCallback(
    (e: React.WheelEvent) => {
      e.preventDefault();
      const canvas = canvasRef.current;
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      const lW = canvas.width / dpr;
      const lH = canvas.height / dpr;

      // Mouse position relative to canvas centre (in logical pixels)
      const mx = e.clientX - rect.left - lW / 2;
      const my = e.clientY - rect.top - lH / 2;

      const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
      const newZoom = Math.max(0.1, Math.min(30, zoomRef.current * factor));
      const scale = newZoom / zoomRef.current;

      // Zoom toward cursor: adjust pan so the world point under the mouse stays fixed
      panRef.current.x = mx + (panRef.current.x - mx) * scale;
      panRef.current.y = my + (panRef.current.y - my) * scale;
      zoomRef.current = newZoom;
      draw();
    },
    [draw],
  );

  const handleDoubleClick = useCallback(() => {
    panRef.current = { x: 0, y: 0 };
    zoomRef.current = 1;
    draw();
  }, [draw]);

  return (
    <div className="space-y-3">
      {/* Projection toggle */}
      <div className="flex items-center gap-2 flex-wrap">
        {(["pca", "umap"] as Projection[]).map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => setProjection(p)}
            className={`px-4 py-1.5 rounded-full text-sm font-semibold border transition-colors ${
              projection === p
                ? "bg-met-red text-white border-met-red"
                : "bg-met-cream text-met-charcoal border-met-gold hover:border-met-red"
            }`}
          >
            {p.toUpperCase()}
          </button>
        ))}
        <span className="text-xs text-met-charcoal/50 ml-1">
          {backdrop?.n_clusters} clusters
          {viz && " · red = query · gold = results"}
          {" · scroll to zoom · drag to pan · double-click to reset"}
        </span>
      </div>

      {/* Canvas */}
      <div
        ref={containerRef}
        className="relative w-full aspect-[4/3] rounded border border-met-gold/30 overflow-hidden bg-white cursor-grab active:cursor-grabbing select-none"
      >
        {!backdrop || isLoading ? (
          <div className="absolute inset-0 flex items-center justify-center text-met-charcoal/40 text-sm">
            {isLoading ? "Searching…" : "Loading cluster data…"}
          </div>
        ) : (
          <canvas
            ref={canvasRef}
            className="w-full h-full"
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseUp}
            onWheel={handleWheel}
            onDoubleClick={handleDoubleClick}
          />
        )}
      </div>

      {/* Legend */}
      {backdrop && (
        <div className="flex flex-wrap gap-2">
          {clusterColors(backdrop.n_clusters).map((color, i) => (
            <span
              key={i}
              className="flex items-center gap-1 text-xs text-met-charcoal/60"
            >
              <span
                className="inline-block w-3 h-3 rounded-full"
                style={{ background: color }}
              />
              {i}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
