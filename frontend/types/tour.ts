export interface TourArtwork {
  object_id: number;
  title: string;
  artist_display_name: string | null;
  primary_image_small: string | null;
  object_url: string;
  gallery_number: string | null;
}

export interface GalleryStop {
  stop_label: string;
  floor: number;
  x: number;
  y: number;
  artworks: TourArtwork[];
}

export interface TourResponse {
  stops: GalleryStop[];
  total_input: number;
  routable_count: number;
  excluded_count: number;
}

export interface TourArtworkInput {
  object_id: number;
  title: string;
  artist_display_name: string | null;
  primary_image_small: string | null;
  object_url: string;
  department: string | null;
  gallery_number: string | null;
}

export interface TourRequest {
  artworks: TourArtworkInput[];
}
