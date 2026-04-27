export interface SearchViz {
  query_pca: [number, number];
  query_umap: [number, number];
  results_pca: [number, number][];
  results_umap: [number, number][];
}

export interface VizDataResponse {
  backdrop_pca: [number, number, number][];   // [x, y, cluster_id]
  backdrop_umap: [number, number, number][];
  n_clusters: number;
}
