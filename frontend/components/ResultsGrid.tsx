"use client";

import type { ArtworkResult, SearchMode } from "../types/search";
import ArtworkCard from "./ArtworkCard";

interface ResultsGridProps {
  results: ArtworkResult[];
  totalResults: number;
  queryMode: SearchMode;
  textWeight?: number;
}

function SearchModeBadge({
  queryMode,
  textWeight,
}: {
  queryMode: SearchMode;
  textWeight?: number;
}) {
  const imageWeight =
    textWeight !== undefined ? Math.round((1 - textWeight) * 100) : 50;
  const textWeightPct =
    textWeight !== undefined ? Math.round(textWeight * 100) : 50;

  const label =
    queryMode === "text"
      ? "Text Search"
      : queryMode === "image"
        ? "Image Search"
        : "Text + Image Search";

  return (
    <span className="inline-flex items-center gap-1.5 bg-met-gold/10 border border-met-gold/30 text-met-charcoal text-xs font-medium px-3 py-1 rounded-full">
      <span
        className="w-1.5 h-1.5 rounded-full bg-met-gold"
        aria-hidden="true"
      />
      {label}
      {queryMode === "joint" && (
        <span className="text-met-charcoal/60 ml-1">
          · Text {textWeightPct}% · Image {imageWeight}%
        </span>
      )}
    </span>
  );
}

export default function ResultsGrid({
  results,
  totalResults,
  queryMode,
  textWeight,
}: ResultsGridProps) {
  return (
    <section className="bg-met-cream w-full px-4 py-6">
      {/* Header row: count + mode badge */}
      <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
        <p className="text-sm text-met-charcoal/60">
          {results.length === 0
            ? "No artworks found"
            : `Showing ${results.length} of ${totalResults} artworks`}
        </p>
        <SearchModeBadge queryMode={queryMode} textWeight={textWeight} />
      </div>

      {/* Gold divider */}
      <div className="h-px bg-met-gold/30 mb-6" aria-hidden="true" />

      {/* Empty state */}
      {results.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 gap-3 text-met-charcoal/60">
          <span className="text-5xl" aria-hidden="true">
            🔍
          </span>
          <p className="text-sm text-center">
            No artworks found. Try a different search.
          </p>
        </div>
      ) : (
        /* Responsive grid */
        <div className="grid grid-cols-1 min-[375px]:grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-4">
          {results.map((result) => (
            <ArtworkCard key={result.object_id} result={result} />
          ))}
        </div>
      )}
    </section>
  );
}
