import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { HostedRoom } from '../services/roomService';
import { useRoomScreenShare } from './useRoomScreenShare';

const mocks = vi.hoisted(() => ({
  createToken: vi.fn<() => Promise<string>>(),
  stopMedia: vi.fn<() => Promise<void>>(),
  connect: vi.fn<() => Promise<void>>(),
  disconnect: vi.fn(),
  disconnectAndWait: vi.fn<() => Promise<void>>(),
  sendAudioChunk: vi.fn(),
  stageInstances: [] as Array<{
    strategy: { stageStreamsToPublish: () => Array<{ mediaStreamTrack: MediaStreamTrack }> };
    join: ReturnType<typeof vi.fn>;
    leave: ReturnType<typeof vi.fn>;
    refreshStrategy: ReturnType<typeof vi.fn>;
  }>,
}));

vi.mock('../services/roomService', () => ({
  createHostMediaToken: mocks.createToken,
  stopRoomMedia: mocks.stopMedia,
}));

vi.mock('./useWebSocket', () => ({
  useWebSocket: () => ({
    connect: mocks.connect,
    disconnect: mocks.disconnect,
    disconnectAndWait: mocks.disconnectAndWait,
    sendAudioChunk: mocks.sendAudioChunk,
  }),
}));

vi.mock('amazon-ivs-web-broadcast', () => ({
  LocalStageStream: class {
    constructor(public mediaStreamTrack: MediaStreamTrack) {}
  },
  SubscribeType: { NONE: 0 },
  Stage: class {
    join = vi.fn().mockResolvedValue(undefined);
    leave = vi.fn();
    refreshStrategy = vi.fn();
    constructor(_token: string, public strategy: { stageStreamsToPublish: () => Array<{ mediaStreamTrack: MediaStreamTrack }> }) {
      mocks.stageInstances.push(this);
    }
  },
}));

type FakeTrack = MediaStreamTrack & { stop: ReturnType<typeof vi.fn> };

function track(kind: 'audio' | 'video'): FakeTrack {
  const result = {
    kind,
    readyState: 'live',
    id: `${kind}-${Math.random()}`,
    addEventListener: vi.fn(),
    stop: vi.fn(() => { result.readyState = 'ended'; }),
  };
  return result as unknown as FakeTrack;
}

class FakeMediaStream {
  constructor(private tracks: MediaStreamTrack[] = []) {}
  getTracks() { return this.tracks; }
  getAudioTracks() { return this.tracks.filter((item) => item.kind === 'audio'); }
  getVideoTracks() { return this.tracks.filter((item) => item.kind === 'video'); }
}

class FakeAudioContext {
  state = 'running';
  createMediaStreamDestination() {
    return { stream: new FakeMediaStream([track('audio')]) };
  }
  createMediaStreamSource() {
    return { connect: vi.fn(), disconnect: vi.fn() };
  }
  close = vi.fn().mockResolvedValue(undefined);
  resume = vi.fn().mockResolvedValue(undefined);
}

const room = {
  roomCode: 'ABC234', hostToken: 'host-token', title: 'Test room',
  joinUrl: 'https://livecap.logantai.com/rooms/ABC234',
  status: 'live', mediaStatus: 'idle', createdAt: '', liveExpiresAt: '', expiresAt: '',
} as HostedRoom;

describe('useRoomScreenShare room media', () => {
  beforeEach(() => {
    mocks.stageInstances.length = 0;
    mocks.createToken.mockReset().mockResolvedValue('ivs-token');
    mocks.stopMedia.mockReset().mockResolvedValue(undefined);
    mocks.connect.mockReset().mockResolvedValue(undefined);
    mocks.disconnectAndWait.mockReset().mockResolvedValue(undefined);
    vi.stubGlobal('MediaStream', FakeMediaStream);
    vi.stubGlobal('AudioContext', FakeAudioContext);
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getDisplayMedia: vi.fn().mockResolvedValue(new FakeMediaStream([track('video')])) },
    });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('keeps microphone audio live when screen sharing stops', async () => {
    const { result, unmount } = renderHook(() => useRoomScreenShare(room, true));
    await act(async () => {
      await result.current.setMicrophoneStream(new FakeMediaStream([track('audio')]) as unknown as MediaStream);
    });
    expect(result.current.microphonePublished).toBe(true);
    expect(mocks.stageInstances).toHaveLength(1);
    expect(mocks.stageInstances[0].strategy.stageStreamsToPublish().map((stream) => stream.mediaStreamTrack.kind)).toEqual(['audio']);

    await act(async () => { await result.current.start(); });
    expect(result.current.status).toBe('live');
    expect(mocks.createToken).toHaveBeenCalledOnce();
    expect(mocks.stageInstances[0].strategy.stageStreamsToPublish().map((stream) => stream.mediaStreamTrack.kind)).toEqual(['video', 'audio']);

    await act(async () => { await result.current.stop(); });
    expect(result.current.status).toBe('idle');
    expect(mocks.stopMedia).not.toHaveBeenCalled();
    expect(mocks.stageInstances[0].strategy.stageStreamsToPublish().map((stream) => stream.mediaStreamTrack.kind)).toEqual(['audio']);

    await act(async () => { await result.current.setMicrophoneStream(null); });
    expect(result.current.microphonePublished).toBe(false);
    expect(mocks.stageInstances[0].leave).toHaveBeenCalledOnce();
    expect(mocks.stopMedia).toHaveBeenCalledOnce();
    unmount();
  });
});
