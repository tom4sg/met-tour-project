"use client";

import { useState, useEffect } from "react";
import Image from "next/image";
import type { ArtworkResult } from "../types/search";

interface ArtworkCardProps {
  result: ArtworkResult;
}

export default function ArtworkCard({ result }: ArtworkCardProps) {
  const [imageError, setImageError] = useState(false);
  const [galleryNumber, setGalleryNumber] = useState<string | null>(null);

  const imageUrl = result.primary_image_small || result.primary_image;
  const showPlaceholder = !imageUrl || imageError;
  const matchPercent = Math.round(result.score * 100);

  // Lazy-fetch gallery number from Met Collection API
  useEffect(() => {
    let cancelled = false;
    const fetchGallery = async () => {
      try {
        const resp = await fetch(
          `https://collectionapi.metmuseum.org/public/collection/v1/objects/${result.object_id}`,
        );
        if (!resp.ok) return;
        const data = await resp.json();
        const gn = (data.GalleryNumber || "").trim();
        if (!cancelled && gn) setGalleryNumber(gn);
      } catch {
        // silently ignore — gallery number is supplemental
      }
    };
    fetchGallery();
    return () => { cancelled = true; };
  }, [result.object_id]);

  return (
    <a
      href={result.object_url}
      target="_blank"
      rel="noopener noreferrer"
      className="
        group block relative min-h-[44px] min-w-[44px]
        bg-met-cream border border-met-gold/20 rounded
        overflow-hidden
        transition-all duration-200 ease-in-out
        hover:shadow-lg hover:border-met-gold
      "
    >
      {/* Similarity score badge */}
      <div className="absolute top-2 right-2 z-10 bg-met-charcoal/80 text-met-cream text-xs px-2 py-0.5 rounded-full">
        Match: {matchPercent}%
      </div>

      {/* Image area */}
      <div className="relative w-full aspect-[4/3] bg-met-charcoal">
        {showPlaceholder ? (
          <div className="flex flex-col items-center justify-center w-full h-full bg-met-charcoal text-met-cream gap-1">
            <span className="text-3xl" aria-hidden="true">
              🏛️
            </span>
            <span className="text-xs">No Image Available</span>
          </div>
        ) : (
          <Image
            src={imageUrl!}
            alt={result.title}
            fill
            className="object-cover"
            onError={() => setImageError(true)}
            sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
          />
        )}
      </div>

      {/* Card body */}
      <div className="p-3 flex flex-col gap-0.5">
        <h3 className="font-bold font-serif text-met-charcoal text-sm leading-snug line-clamp-2">
          {result.title}
        </h3>
        <p className="text-xs text-met-charcoal/70">
          {result.artist_display_name ?? "Unknown Artist"}
        </p>
        {result.object_date && (
          <p className="text-xs text-met-charcoal/60">{result.object_date}</p>
        )}
        {(result.department || galleryNumber) && (
          <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
            {result.department && (
              <p className="text-xs text-met-gold font-medium">
                {result.department}
              </p>
            )}
            {galleryNumber && (
              <span className="inline-flex items-center gap-0.5 text-xs text-met-charcoal/60 bg-met-charcoal/5 px-1.5 py-0.5 rounded">
                <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
                Gallery {galleryNumber}
              </span>
            )}
          </div>
        )}
      </div>
    </a>
  );
}
