"use client";

import { useState } from "react";
import HeroSection from "../components/HeroSection";
import LoadingState from "../components/LoadingState";
import ResultsGrid from "../components/ResultsGrid";
import SearchForm from "../components/SearchForm";
import TourPanel from "../components/TourPanel";
import type { SearchResponse } from "../types/search";

export default function HomePage() {
  const [searchResponse, setSearchResponse] = useState<SearchResponse | null>(
    null,
  );
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>("");

  const showHero = searchResponse === null && !isLoading;

  return (
    <div className="flex flex-col items-center">
      {/* Hero — only shown before first search */}
      {showHero && <HeroSection />}

      {/* Search form — always visible */}
      <div className="w-full px-4 py-6 flex justify-center">
        <div className="w-full max-w-2xl bg-white rounded-lg shadow-md px-4 py-6 md:px-6">
          <SearchForm
            onResults={(response) => {
              setSearchResponse(response);
              setError(null);
            }}
            onLoading={setIsLoading}
            onError={setError}
            onQuery={setSearchQuery}
          />
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div
          role="alert"
          className="w-full max-w-2xl mx-4 mb-4 flex items-center justify-between gap-3 bg-met-red text-white text-sm px-4 py-3 rounded"
        >
          <span>{error}</span>
          <button
            type="button"
            onClick={() => setError(null)}
            aria-label="Dismiss error"
            className="shrink-0 text-white/80 hover:text-white text-lg leading-none"
          >
            &times;
          </button>
        </div>
      )}

      {/* Loading state */}
      {isLoading && <LoadingState />}

      {/* Results */}
      {!isLoading && searchResponse && (
        <div className="w-full transition-opacity duration-300">
          <ResultsGrid
            results={searchResponse.results}
            totalResults={searchResponse.total_results}
            queryMode={searchResponse.query_mode}
            textWeight={searchResponse.text_weight}
          />
          <TourPanel artworks={searchResponse.results} query={searchQuery} />
        </div>
      )}
    </div>
  );
}
