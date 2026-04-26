"use client";

import type { GalleryStop } from "../types/tour";

interface GalleryStopCardProps {
  stop: GalleryStop;
  stopNumber: number;
}

export default function GalleryStopCard({
  stop,
  stopNumber,
}: GalleryStopCardProps) {
  return (
    <div className="bg-met-cream border border-met-gold/20 rounded overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-met-gold/20">
        <span className="flex-shrink-0 w-7 h-7 rounded-full bg-met-red text-white text-xs font-bold flex items-center justify-center">
          {stopNumber}
        </span>
        <div className="flex-1 min-w-0">
          <p className="font-bold text-met-charcoal text-sm leading-tight">
            {stop.stop_label}
          </p>
          <p className="text-xs text-met-charcoal/60 mt-0.5">
            Floor {stop.floor}
          </p>
        </div>
      </div>

      {/* Artwork thumbnail row */}
      <div className="flex gap-3 overflow-x-auto px-4 py-3 scrollbar-thin">
        {stop.artworks.map((artwork) => (
          <a
            key={artwork.object_id}
            href={artwork.object_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex-shrink-0 w-24 group"
          >
            {/* Thumbnail */}
            <div className="w-24 h-24 bg-met-charcoal rounded overflow-hidden mb-1.5">
              {artwork.primary_image_small ? (
                <img
                  src={artwork.primary_image_small}
                  alt={artwork.title}
                  className="w-full h-full object-cover group-hover:opacity-90 transition-opacity"
                />
              ) : (
                <div className="w-full h-full flex flex-col items-center justify-center text-met-cream gap-1">
                  <span className="text-2xl" aria-hidden="true">
                    🏛️
                  </span>
                  <span className="text-xs text-center leading-tight px-1">
                    No Image
                  </span>
                </div>
              )}
            </div>

            {/* Title */}
            <p className="text-xs font-medium text-met-charcoal leading-tight line-clamp-2">
              {artwork.title}
            </p>

            {/* Artist */}
            {artwork.artist_display_name && (
              <p className="text-xs text-met-charcoal/60 mt-0.5 line-clamp-1">
                {artwork.artist_display_name}
              </p>
            )}

            {/* Gallery number */}
            {artwork.gallery_number && (
              <p className="inline-flex items-center gap-0.5 text-[10px] text-met-charcoal/50 mt-0.5">
                <svg xmlns="http://www.w3.org/2000/svg" width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
                Gallery {artwork.gallery_number}
              </p>
            )}
          </a>
        ))}
      </div>
    </div>
  );
}
