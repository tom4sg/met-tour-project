export const FLOOR_CONFIG = {
  1: { imgW: 1980, imgH: 1520 },
  2: { imgW: 1980, imgH: 1543 },
} as const;

export const POLY_COEFF: Record<1 | 2, { x: number[]; y: number[] }> = {
  1: {
    x: [155.2165, 9.9711, 0.6041, 10.9756, -1.6691, -42.042],
    y: [-30.4011, -96.3004, 0.5175, 2.4505, -2.5016, 1416.7289],
  },
  2: {
    x: [235.62, 0, 0, 0, 0, -174.21],
    y: [0, -108.05, 0, 0, 0, 1189.30],
  },
};

export function polyToPixel(x: number, y: number, floor: 1 | 2): [number, number] {
  const c = POLY_COEFF[floor];
  const feats = [x, y, x * y, x * x, y * y, 1];
  const px = c.x.reduce((s, ci, i) => s + ci * feats[i], 0);
  const py = c.y.reduce((s, ci, i) => s + ci * feats[i], 0);
  return [px, py];
}

export type PixelTable = Record<string, Record<string, [number, number]>>;

let pixelTableCache: PixelTable | null = null;

export async function loadPixelTable(): Promise<PixelTable> {
  if (pixelTableCache) return pixelTableCache;
  const res = await fetch("/met-gallery-pixels.json");
  pixelTableCache = await res.json();
  return pixelTableCache!;
}

export const LABEL_OFFSET_X = 20;
export const LABEL_OFFSET_Y = 8;
