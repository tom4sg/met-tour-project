import { ArtworkResult, ApiError } from "../types/search";
import { TourRequest, TourResponse } from "../types/tour";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function generateTour(
  artworks: ArtworkResult[],
): Promise<TourResponse> {
  const body: TourRequest = {
    artworks: artworks.map((a) => ({
      object_id: a.object_id,
      title: a.title,
      artist_display_name: a.artist_display_name,
      primary_image_small: a.primary_image_small,
      object_url: a.object_url,
      department: a.department,
      gallery_number: a.gallery_number,
    })),
  };

  let response: Response;
  try {
    response = await fetch(`${API_URL}/tour`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new Error(
      `Cannot reach the tour API at ${API_URL}. Is the backend running? (${msg})`,
    );
  }

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const errorBody = await response.json();
      detail = errorBody?.detail ?? detail;
    } catch {
      // non-JSON error body — keep the status code message
    }
    throw new ApiError(detail, detail);
  }

  return response.json() as Promise<TourResponse>;
}
