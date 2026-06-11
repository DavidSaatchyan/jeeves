export function searchMemories(memories, query, options = {}) {
  const { limit = 10, tag, key, fuzzy = false } = options;
  const q = (query || "").toLowerCase().trim();

  let results = memories;

  if (key) {
    results = results.filter(m => m.key === key);
  }

  if (tag) {
    const tags = Array.isArray(tag) ? tag : [tag];
    results = results.filter(m => tags.some(t => m.tags.includes(t.toLowerCase())));
  }

  if (q) {
    const terms = q.split(/\s+/).filter(Boolean);
    results = results.map(m => {
      let score = 0;
      const content = m.content.toLowerCase();
      const keyText = m.key.toLowerCase();
      const tags = (m.tags || []).join(" ").toLowerCase();

      for (const term of terms) {
        if (keyText === term) score += 100;
        else if (keyText.includes(term)) score += 50;
        if (content.includes(term)) score += 10;
        if (tags.includes(term)) score += 5;

        if (fuzzy && term.length >= 4) {
          if (levenshteinRatio(keyText, term) > 0.7) score += 25;
          if (levenshteinRatio(content, term) > 0.7) score += 3;
        }
      }

      return { ...m, _score: score };
    })
      .filter(m => m._score > 0)
      .sort((a, b) => b._score - a._score)
      .slice(0, limit);
  } else {
    results = [...results].sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt)).slice(0, limit);
  }

  return results.map(({ _score, ...m }) => m);
}

function levenshteinRatio(a, b) {
  const maxLen = Math.max(a.length, b.length);
  if (maxLen === 0) return 1;
  const dist = levenshtein(a.slice(0, maxLen), b.slice(0, maxLen));
  return 1 - dist / maxLen;
}

function levenshtein(a, b) {
  if (a.length === 0) return b.length;
  if (b.length === 0) return a.length;
  const matrix = [];
  for (let i = 0; i <= b.length; i++) matrix[i] = [i];
  for (let j = 0; j <= a.length; j++) matrix[0][j] = j;
  for (let i = 1; i <= b.length; i++) {
    for (let j = 1; j <= a.length; j++) {
      matrix[i][j] = b[i - 1] === a[j - 1]
        ? matrix[i - 1][j - 1]
        : Math.min(matrix[i - 1][j - 1] + 1, matrix[i][j - 1] + 1, matrix[i - 1][j] + 1);
    }
  }
  return matrix[b.length][a.length];
}
