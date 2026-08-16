import { describe, expect, it } from 'vitest';
import { segmentFromWire } from './roomService';

describe('segmentFromWire', () => {
  it('accepts a finalized room caption contract', () => {
    expect(segmentFromWire({
      segment_id: 'segment-1',
      speaker_label: 'Speaker 1',
      text_vi: 'Xin chào',
      text_en: 'Hello',
      spoken_language: 'vi',
      timestamp_start: 1,
      timestamp_end: 2,
    })).toMatchObject({
      segmentId: 'segment-1',
      textVi: 'Xin chào',
      textEn: 'Hello',
      isFinal: true,
    });
  });

  it('rejects partial or malformed captions', () => {
    expect(segmentFromWire({ segment_id: 'segment-1' })).toBeNull();
  });
});
