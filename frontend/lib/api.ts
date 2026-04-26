import { SearchParams, SearchResponse, ApiError } from "../types/search";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function searchArtworks(
  params: SearchParams,
): Promise<SearchResponse> {
  const formData = new FormData();

  formData.append("mode", params.mode);

  if (params.query && (params.mode === "text" || params.mode === "joint")) {
    formData.append("query", params.query);
  }

  if (params.image && (params.mode === "image" || params.mode === "joint")) {
    formData.append("image", params.image);
  }

  formData.append("top_k", String(params.top_k));

  if (params.mode === "joint" && params.text_weight !== undefined) {
    formData.append("text_weight", String(params.text_weight));
  }

  if (params.clip_weight !== undefined) {
    formData.append("clip_weight", String(params.clip_weight));
  }

  if (params.st_weight !== undefined) {
    formData.append("st_weight", String(params.st_weight));
  }

  if (params.top_clusters !== undefined) {
    formData.append("top_clusters", String(params.top_clusters));
  }

  let response: Response;
  try {
    response = await fetch(`${API_URL}/search`, {
      method: "POST",
      body: formData,
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new Error(
      `Cannot reach the search API at ${API_URL}. Is the backend running? (${msg})`,
    );
  }

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      detail = body?.detail ?? detail;
    } catch {
      // non-JSON error body — keep the status code message
    }
    throw new ApiError(detail, detail);
  }

  return response.json() as Promise<SearchResponse>;
}

export async function checkHealth(): Promise<{ status: string; rows: number }> {
  const response = await fetch(`${API_URL}/health`);
  return response.json();
}
