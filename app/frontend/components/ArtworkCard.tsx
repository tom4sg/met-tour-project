"use client";

import { useState } from "react";
import Image from "next/image";
import type { ArtworkResult } from "../types/search";

interface ArtworkCardProps {
  result: ArtworkResult;
}

export default function ArtworkCard({ result }: ArtworkCardProps) {
  const [imageError, setImageError] = useState(false);

  const imageUrl = result.primary_image_small || result.primary_image;
  const showPlaceholder = !imageUrl || imageError;
  const matchPercent = Math.round(result.score * 100);

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
        {result.department && (
          <p className="text-xs text-met-gold font-medium">
            {result.department}
          </p>
        )}
      </div>
    </a>
  );
}
