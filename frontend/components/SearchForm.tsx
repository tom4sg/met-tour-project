"use client";

import { useState } from "react";
import { searchArtworks } from "../lib/api";
import { ApiError, SearchResponse } from "../types/search";

interface SearchFormProps {
  onResults: (response: SearchResponse) => void;
  onLoading: (loading: boolean) => void;
  onError: (error: string | null) => void;
  onQuery: (query: string) => void;
}

export default function SearchForm({
  onResults,
  onLoading,
  onError,
  onQuery,
}: SearchFormProps) {
  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState(20);
  const [clipWeight, setClipWeight] = useState(1.0);
  const [stWeight, setStWeight] = useState(1.0);
  const [topClusters, setTopClusters] = useState(2);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();

    // Client-side validation
    if (!query.trim()) {
      setValidationError("Please enter a search query");
      return;
    }

    setValidationError(null);
    onLoading(true);
    onError(null);
    onQuery(query.trim());

    try {
      const response = await searchArtworks({
        mode: "text",
        query: query.trim(),
        top_k: topK,
        clip_weight: clipWeight,
        st_weight: stWeight,
        top_clusters: topClusters,
      });
      onResults(response);
      onLoading(false);
    } catch (err) {
      if (err instanceof ApiError) {
        onError(err.detail);
      } else if (err instanceof Error) {
        onError(err.message);
      } else {
        onError("Something went wrong. Please try again.");
      }
      onLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="w-full space-y-5">
      {/* Text input */}
      <div>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search the collection…"
          className="w-full min-h-[44px] px-4 py-2 border border-met-charcoal rounded text-met-charcoal bg-met-cream placeholder-met-charcoal/50 focus:outline-none focus:ring-2 focus:ring-met-red transition-colors"
        />
      </div>

      {/* Top-K selector */}
      <div className="flex items-center gap-3">
        <label
          htmlFor="top-k"
          className="text-sm font-medium text-met-charcoal whitespace-nowrap"
        >
          Results
        </label>
        <input
          id="top-k"
          type="number"
          min={1}
          max={100}
          step={1}
          value={topK}
          onChange={(e) => setTopK(Math.min(100, Math.max(1, parseInt(e.target.value) || 1)))}
          className="min-h-[44px] w-20 px-3 py-2 border border-met-charcoal rounded bg-met-cream text-met-charcoal focus:outline-none focus:ring-2 focus:ring-met-red"
        />
      </div>

      {/* Advanced settings */}
      <div className="border border-met-gold/30 rounded">
        <button
          type="button"
          onClick={() => setShowAdvanced((v) => !v)}
          className="w-full flex items-center justify-between px-4 py-2 text-sm font-medium text-met-charcoal hover:bg-met-gold/10 transition-colors"
        >
          <span>Advanced</span>
          <span className="text-met-charcoal/50">{showAdvanced ? "▲" : "▼"}</span>
        </button>

        {showAdvanced && (
          <div className="px-4 pb-4 space-y-4 border-t border-met-gold/30 pt-3">
            {/* CLIP weight */}
            <div className="space-y-1">
              <label className="block text-sm font-medium text-met-charcoal">
                CLIP weight
              </label>
              <div className="min-h-[44px] flex items-center">
                <input
                  type="range"
                  min={0}
                  max={2}
                  step={0.05}
                  value={clipWeight}
                  onChange={(e) => setClipWeight(parseFloat(e.target.value))}
                  className="w-full accent-met-red"
                />
              </div>
              <p className="text-xs text-met-charcoal/70">{clipWeight.toFixed(2)}</p>
            </div>

            {/* ST text weight */}
            <div className="space-y-1">
              <label className="block text-sm font-medium text-met-charcoal">
                Text embedding weight
              </label>
              <div className="min-h-[44px] flex items-center">
                <input
                  type="range"
                  min={0}
                  max={2}
                  step={0.05}
                  value={stWeight}
                  onChange={(e) => setStWeight(parseFloat(e.target.value))}
                  className="w-full accent-met-red"
                />
              </div>
              <p className="text-xs text-met-charcoal/70">{stWeight.toFixed(2)}</p>
            </div>

            {/* GMM clusters */}
            <div className="flex items-center gap-3">
              <label
                htmlFor="top-clusters"
                className="text-sm font-medium text-met-charcoal whitespace-nowrap"
              >
                GMM clusters
              </label>
              <select
                id="top-clusters"
                value={topClusters}
                onChange={(e) => setTopClusters(Number(e.target.value))}
                className="min-h-[44px] min-w-[44px] px-3 py-2 border border-met-charcoal rounded bg-met-cream text-met-charcoal focus:outline-none focus:ring-2 focus:ring-met-red"
              >
                {[1, 2, 3, 4, 5].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </div>
          </div>
        )}
      </div>

      {/* Submit button */}
      <button
        type="submit"
        className="w-full sm:w-auto min-h-[44px] min-w-[44px] px-8 py-2 bg-met-red text-white font-semibold rounded hover:bg-red-700 transition-colors focus:outline-none focus:ring-2 focus:ring-met-red focus:ring-offset-2 flex items-center justify-center gap-2"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="h-5 w-5"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M21 21l-4.35-4.35M17 11A6 6 0 1 1 5 11a6 6 0 0 1 12 0z"
          />
        </svg>
        Search
      </button>

      {/* Validation error */}
      {validationError && (
        <p role="alert" className="text-met-red text-sm mt-1">
          {validationError}
        </p>
      )}
    </form>
  );
}
