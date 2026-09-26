import { describe, expect, it } from 'vitest';
import { captionChunks } from './captionChunks';

describe('captionChunks', () => {
  it('keeps all words in order while splitting long captions', () => {
    const text = 'Anh bạn tôi đang đề cập đến một bài hát và tôi không biết tên bài hát đó';
    const chunks = captionChunks(text, 28);
    expect(chunks.length).toBeGreaterThan(1);
    expect(chunks.join(' ')).toBe(text);
    expect(chunks.every((chunk) => chunk.length <= 28)).toBe(true);
  });

  it('handles empty and single-word captions', () => {
    expect(captionChunks('  ', 50)).toEqual([]);
    expect(captionChunks('Hello', 2)).toEqual(['Hello']);
  });
});
