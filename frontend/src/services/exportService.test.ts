import { describe, expect, it, vi } from 'vitest';

import { generateMeetingSummary, MeetingSummaryError } from './exportService';
import type { Segment } from '../types';

const segments: Segment[] = [
  {
    segmentId: 'seg-1', speakerLabel: 'Speaker 1', textVi: 'Xin chao', textEn: 'Hello',
    spokenLanguage: 'vi', isFinal: true, timestampStart: 0, timestampEnd: 1,
  },
];

describe('generateMeetingSummary', () => {
  it('posts finalized captions only after the user requests notes', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ summary_en: 'Summary', keywords: ['launch'] }),
    });
    vi.stubGlobal('fetch', fetchMock);

    const summary = await generateMeetingSummary('session one', segments, 'https://api.example.test');

    expect(summary.summary_en).toBe('Summary');
    expect(fetchMock).toHaveBeenCalledWith(
      'https://api.example.test/api/sessions/session%20one/summary',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      segments: [
        expect.objectContaining({ segment_id: 'seg-1', text_vi: 'Xin chao', text_en: 'Hello' }),
      ],
    });
  });

  it('surfaces the backend explanation when notes are unavailable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
      statusText: 'Conflict',
      json: async () => ({ detail: 'AI meeting notes are not enabled' }),
    }));

    await expect(generateMeetingSummary('session-1', segments, 'https://api.example.test'))
      .rejects.toEqual(expect.objectContaining<Partial<MeetingSummaryError>>({
        name: 'MeetingSummaryError',
        message: 'AI meeting notes are not enabled',
        statusCode: 409,
      }));
  });
});
