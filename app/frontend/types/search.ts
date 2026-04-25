export type SearchMode = "text" | "image" | "joint";

export interface ArtworkResult {
  object_id: number;
  title: string;
  artist_display_name: string | null;
  object_date: string | null;
  department: string | null;
  medium: string | null;
  primary_image_small: string | null;
  primary_image: string | null;
  object_url: string;
  score: number;
  is_highlight: boolean;
}

export interface SearchResponse {
  results: ArtworkResult[];
  query_mode: SearchMode;
  total_results: number;
  text_weight?: number;
}

export interface SearchParams {
  mode: SearchMode;
  query?: string;
  image?: File;
  top_k: number;
  text_weight?: number;
}

export class ApiError extends Error {
  detail: string;

  constructor(message: string, detail: string) {
    super(message);
    this.name = "ApiError";
    this.detail = detail;
  }
}
