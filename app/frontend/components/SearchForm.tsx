"use client";

import { useEffect, useRef, useState } from "react";
import { searchArtworks } from "../lib/api";
import { ApiError, SearchMode, SearchResponse } from "../types/search";

interface SearchFormProps {
  onResults: (response: SearchResponse) => void;
  onLoading: (loading: boolean) => void;
  onError: (error: string | null) => void;
}

export default function SearchForm({
  onResults,
  onLoading,
  onError,
}: SearchFormProps) {
  const [mode, setMode] = useState<SearchMode>("text");
  const [query, setQuery] = useState("");
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [imagePreviewUrl, setImagePreviewUrl] = useState<string | null>(null);
  const [textWeight, setTextWeight] = useState(0.5);
  const [topK, setTopK] = useState(20);
  const [validationError, setValidationError] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Revoke object URL on unmount or when imagePreviewUrl changes
  useEffect(() => {
    return () => {
      if (imagePreviewUrl) {
        URL.revokeObjectURL(imagePreviewUrl);
      }
    };
  }, [imagePreviewUrl]);

  function handleModeChange(newMode: SearchMode) {
    setMode(newMode);
    setValidationError(null);
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] ?? null;
    if (imagePreviewUrl) {
      URL.revokeObjectURL(imagePreviewUrl);
    }
    if (file) {
      setImageFile(file);
      setImagePreviewUrl(URL.createObjectURL(file));
    } else {
      setImageFile(null);
      setImagePreviewUrl(null);
    }
  }

  function handleRemoveImage() {
    if (imagePreviewUrl) {
      URL.revokeObjectURL(imagePreviewUrl);
    }
    setImageFile(null);
    setImagePreviewUrl(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();

    // Client-side validation
    if (mode === "text" && !query.trim()) {
      setValidationError("Please enter a search query");
      return;
    }
    if (mode === "image" && !imageFile) {
      setValidationError("Please upload an image");
      return;
    }
    if (mode === "joint" && (!query.trim() || !imageFile)) {
      setValidationError(
        "Text + Image mode requires both a query and an image",
      );
      return;
    }

    setValidationError(null);
    onLoading(true);
    onError(null);

    try {
      const response = await searchArtworks({
        mode,
        query: query.trim(),
        image: imageFile ?? undefined,
        top_k: topK,
        text_weight: textWeight,
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

  const modes: { value: SearchMode; label: string }[] = [
    { value: "text", label: "Text" },
    { value: "image", label: "Image" },
    { value: "joint", label: "Text + Image" },
  ];

  return (
    <form onSubmit={handleSubmit} noValidate className="w-full space-y-5">
      {/* Mode selector */}
      <div className="flex gap-2 flex-wrap">
        {modes.map(({ value, label }) => (
          <button
            key={value}
            type="button"
            onClick={() => handleModeChange(value)}
            className={`min-h-[44px] min-w-[44px] px-5 py-2 rounded-full text-sm font-semibold border transition-colors focus:outline-none focus:ring-2 focus:ring-met-red focus:ring-offset-1 ${
              mode === value
                ? "bg-met-red text-white border-met-red"
                : "bg-met-cream text-met-charcoal border-met-gold hover:border-met-red"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Text input */}
      <div>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search the collection…"
          disabled={mode === "image"}
          className={`w-full min-h-[44px] px-4 py-2 border rounded text-met-charcoal bg-met-cream placeholder-met-charcoal/50 focus:outline-none focus:ring-2 focus:ring-met-red transition-colors ${
            mode === "image"
              ? "border-met-charcoal/20 opacity-40 cursor-not-allowed"
              : "border-met-charcoal"
          }`}
        />
      </div>

      {/* Image upload */}
      <div>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          onChange={handleFileChange}
          disabled={mode === "text"}
          className="hidden"
          id="image-upload"
        />
        <label
          htmlFor="image-upload"
          className={`inline-flex items-center min-h-[44px] min-w-[44px] px-5 py-2 border rounded text-sm font-semibold cursor-pointer transition-colors focus-within:ring-2 focus-within:ring-met-red ${
            mode === "text"
              ? "bg-met-cream text-met-charcoal/40 border-met-charcoal/20 opacity-40 cursor-not-allowed pointer-events-none"
              : "bg-met-cream text-met-charcoal border-met-gold hover:border-met-red"
          }`}
        >
          {imageFile ? "Change Image" : "Upload Image"}
        </label>

        {imagePreviewUrl && imageFile && (
          <div className="mt-3 flex items-start gap-3">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={imagePreviewUrl}
              alt="Preview"
              className="w-20 h-20 object-cover rounded border border-met-gold"
            />
            <div className="flex flex-col gap-1">
              <span className="text-xs text-met-charcoal/70 break-all max-w-[200px]">
                {imageFile.name}
              </span>
              <button
                type="button"
                onClick={handleRemoveImage}
                className="min-h-[44px] min-w-[44px] px-3 py-1 text-xs text-met-red border border-met-red rounded hover:bg-met-red hover:text-white transition-colors self-start"
              >
                Remove
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Weight slider — only visible in joint mode */}
      {mode === "joint" && (
        <div className="space-y-1">
          <label className="block text-sm font-medium text-met-charcoal">
            Text ← Weight → Image
          </label>
          <div className="min-h-[44px] flex items-center">
            <input
              type="range"
              min={0}
              max={1}
              step={0.01}
              value={textWeight}
              onChange={(e) => setTextWeight(parseFloat(e.target.value))}
              className="w-full accent-met-red"
            />
          </div>
          <p className="text-xs text-met-charcoal/70">
            Text {Math.round(textWeight * 100)}% · Image{" "}
            {Math.round((1 - textWeight) * 100)}%
          </p>
        </div>
      )}

      {/* Top-K selector */}
      <div className="flex items-center gap-3">
        <label
          htmlFor="top-k"
          className="text-sm font-medium text-met-charcoal whitespace-nowrap"
        >
          Results
        </label>
        <select
          id="top-k"
          value={topK}
          onChange={(e) => setTopK(Number(e.target.value))}
          className="min-h-[44px] min-w-[44px] px-3 py-2 border border-met-charcoal rounded bg-met-cream text-met-charcoal focus:outline-none focus:ring-2 focus:ring-met-red"
        >
          {[10, 20, 50, 100].map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
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
