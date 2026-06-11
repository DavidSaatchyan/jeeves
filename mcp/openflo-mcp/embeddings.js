import { pipeline } from "@xenova/transformers";

let extractor = null;
let loadAttempted = false;

export async function getExtractor() {
  if (extractor) return extractor;
  if (loadAttempted) return null;
  loadAttempted = true;
  try {
    process.stderr.write("[openflo-mcp] Loading embedding model (all-MiniLM-L6-v2)...\n");
    extractor = await pipeline("feature-extraction", "Xenova/all-MiniLM-L6-v2", {
      quantized: true,
    });
    process.stderr.write("[openflo-mcp] Embedding model ready\n");
    return extractor;
  } catch (err) {
    process.stderr.write(`[openflo-mcp] Embedding model failed: ${err.message}\n`);
    return null;
  }
}

export async function embed(text) {
  const pipe = await getExtractor();
  if (!pipe) return null;
  try {
    const result = await pipe(text, { pooling: "mean", normalize: true });
    return result.tolist()[0];
  } catch {
    return null;
  }
}

export function cosineSimilarity(a, b) {
  if (!a || !b || a.length !== b.length) return 0;
  let dot = 0, na = 0, nb = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    na += a[i] * a[i];
    nb += b[i] * b[i];
  }
  const denom = Math.sqrt(na) * Math.sqrt(nb);
  return denom === 0 ? 0 : dot / denom;
}

export function cosineSimilarityBatch(queryVec, vectors) {
  const qNorm = Math.sqrt(queryVec.reduce((s, v) => s + v * v, 0));
  const results = vectors.map((vec, i) => {
    const dot = vec.reduce((s, v, j) => s + v * queryVec[j], 0);
    const vNorm = Math.sqrt(vec.reduce((s, v) => s + v * v, 0));
    return { index: i, score: qNorm * vNorm === 0 ? 0 : dot / (qNorm * vNorm) };
  });
  return results.sort((a, b) => b.score - a.score);
}
