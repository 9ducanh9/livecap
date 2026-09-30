import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  forgetHostedRoom,
  partialFromWire,
  rememberHostedRoom,
  restoreHostedRoom,
  segmentFromWire,
  type HostedRoom,
} from './roomService';

describe('segmentFromWire', () => {
  it('accepts a finalized room caption contract', () => {
    expect(segmentFromWire({
      segment_id: 'segment-1', speaker_label: 'Speaker 1', text_vi: 'Xin chào',
      text_en: 'Hello', spoken_language: 'vi', timestamp_start: 1, timestamp_end: 2,
    })).toMatchObject({ segmentId: 'segment-1', textVi: 'Xin chào', textEn: 'Hello', isFinal: true });
  });

  it('rejects partial or malformed captions', () => {
    expect(segmentFromWire({ segment_id: 'segment-1' })).toBeNull();
  });
});

describe('partialFromWire', () => {
  it('accepts a revisable room caption without archive timestamps', () => {
    expect(partialFromWire({
      segment_id: 'segment-1', speaker_label: 'Speaker 1', text_vi: '',
      text_en: 'Speaking now', spoken_language: 'en', is_final: false,
    })).toMatchObject({ segmentId: 'segment-1', textEn: 'Speaking now', isFinal: false });
  });

  it('rejects finalized captions', () => {
    expect(partialFromWire({ segment_id: 'segment-1', is_final: true })).toBeNull();
  });
});

const room: HostedRoom = {
  roomCode: 'ABCDEF', hostToken: 'private-host-token', joinUrl: 'https://example.com/rooms/ABCDEF',
  title: 'Live room', status: 'live', mediaStatus: 'live', createdAt: '2026-09-30T00:00:00Z',
  liveExpiresAt: '2099-01-01T00:00:00Z', expiresAt: '2099-01-15T00:00:00Z',
};

describe('hosted room recovery', () => {
  beforeEach(() => { localStorage.clear(); vi.unstubAllGlobals(); });

  it('restores a still-live room and its host credential after reload', async () => {
    rememberHostedRoom(room);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true, status: 200,
      json: async () => ({ status: 'live', media_status: 'idle' }),
    }));
    expect(await restoreHostedRoom()).toEqual({ ...room, mediaStatus: 'idle' });
  });

  it('discards the host credential when the room ended', async () => {
    rememberHostedRoom(room);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true, status: 200,
      json: async () => ({ status: 'ended' }),
    }));
    expect(await restoreHostedRoom()).toBeNull();
    expect(localStorage.length).toBe(0);
  });

  it('discards expired room credentials without calling the backend', async () => {
    rememberHostedRoom({ ...room, liveExpiresAt: '2000-01-01T00:00:00Z' });
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    expect(await restoreHostedRoom()).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
    forgetHostedRoom();
  });
});
