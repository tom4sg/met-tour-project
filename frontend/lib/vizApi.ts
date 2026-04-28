import type { VizDataResponse } from "../types/viz";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function fetchVizData(): Promise<VizDataResponse> {
  const response = await fetch(`${API_URL}/viz-data`);
  if (!response.ok) throw new Error(`Failed to load viz data: HTTP ${response.status}`);
  return response.json();
}
