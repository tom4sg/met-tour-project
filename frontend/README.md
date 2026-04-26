# Frontend

Next.js 14 app (App Router) for searching and touring the Met Museum collection.

## Stack

- **Next.js 14** (App Router, `"use client"` components)
- **TypeScript**
- **Tailwind CSS** with a custom Met palette (`met-red`, `met-gold`, `met-cream`, `met-charcoal`)

## File Tree

```
frontend/
├── app/
│   ├── globals.css          # Tailwind base + custom CSS variables
│   ├── layout.tsx           # Root layout (font, metadata)
│   └── page.tsx             # Single-page app shell — owns all top-level state
│
├── components/
│   ├── HeroSection.tsx      # Intro banner shown before the first search
│   ├── SearchForm.tsx       # Mode selector, text input, image upload, top-k picker
│   ├── LoadingState.tsx     # Spinner shown while a search is in flight
│   ├── ResultsGrid.tsx      # Artwork card grid rendered after a search
│   ├── ArtworkCard.tsx      # Single artwork tile (image, title, artist, score)
│   ├── TourPanel.tsx        # "Generate Tour" button + tour results + PDF export
│   ├── TourMapOverlay.tsx   # Floor-tab wrapper that renders the map
│   ├── TourMapInner.tsx     # Met Museum iframe map with fallback link
│   └── GalleryStopCard.tsx  # One stop in the tour list (gallery, artworks)
│
├── lib/
│   ├── api.ts               # searchArtworks() — POST /search
│   └── tourApi.ts           # generateTour()  — POST /tour
│
└── types/
    ├── search.ts            # SearchMode, ArtworkResult, SearchResponse, SearchParams, ApiError
    └── tour.ts              # TourArtwork, GalleryStop, TourResponse, TourRequest
```

## How It Works

### Search flow

1. `page.tsx` renders `SearchForm` and holds `searchResponse` state.
2. `SearchForm` lets the user pick a mode (**Text**, **Image**, or **Text + Image**), enter a query and/or upload an image, choose how many results to return (10 / 20 / 50 / 100), and optionally adjust the text/image blend weight.
3. On submit, `lib/api.ts → searchArtworks()` sends a `multipart/form-data` POST to `POST /search`.
4. Results are passed back to `page.tsx`, which renders `ResultsGrid` (the artwork cards) and `TourPanel`.

### Tour flow

1. After a search, `TourPanel` shows a **Generate Tour** button.
2. Clicking it calls `lib/tourApi.ts → generateTour()`, which sends a `POST /tour` with the artwork list.
3. The backend returns an ordered list of `GalleryStop` objects.
4. `TourPanel` renders a floor-by-floor map (`TourMapOverlay` / `TourMapInner`) and a numbered stop list (`GalleryStopCard`).
5. An **Export PDF** button opens a print-ready page in a new tab.

### Environment

Copy `.env.local.example` to `.env.local`:

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Running

```bash
npm install
npm run dev   # http://localhost:3000
```
