export function captionChunks(text: string, maxChars: number): string[] {
  const chunks: string[] = [];
  const normalized = text.trim().replace(/\s+/g, ' ');
  if (!normalized) return chunks;

  // Sentence boundaries always start a new card, even when ASR omitted the
  // space after punctuation ("work.Next"), so two sentences never join.
  const sentences: string[] = [];
  let start = 0;
  for (const match of normalized.matchAll(/[.!?…]+["”']?(?=\s|$|\p{Lu})/gu)) {
    const end = match.index + match[0].length;
    sentences.push(normalized.slice(start, end).trim());
    start = end;
  }
  if (start < normalized.length) sentences.push(normalized.slice(start).trim());

  for (const sentence of sentences) {
    let current = '';
    for (const word of sentence.split(/\s+/).filter(Boolean)) {
      if (current && current.length + word.length + 1 > maxChars) {
        chunks.push(current);
        current = word;
      } else {
        current = current ? `${current} ${word}` : word;
      }
    }
    if (current) chunks.push(current);
  }
  return chunks;
}
