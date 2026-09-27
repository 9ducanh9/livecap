import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useAudioCapture } from './useAudioCapture';

const mocks = vi.hoisted(() => ({
  gains: [] as Array<{ gain: { value: number }; connect: ReturnType<typeof vi.fn>; disconnect: ReturnType<typeof vi.fn> }>,
  worklets: [] as Array<{ port: { onmessage: ((event: MessageEvent<ArrayBuffer>) => void) | null }; connect: ReturnType<typeof vi.fn>; disconnect: ReturnType<typeof vi.fn> }>,
}));

function fakeTrack() {
  return { kind: 'audio', stop: vi.fn() };
}

class FakeMediaStream {
  constructor(private tracks = [fakeTrack()]) {}
  getTracks() { return this.tracks; }
  getAudioTracks() { return this.tracks; }
}

class FakeAudioContext {
  sampleRate = 16_000;
  state = 'running';
  destination = {};
  audioWorklet = { addModule: vi.fn().mockResolvedValue(undefined) };
  createMediaStreamSource() { return { connect: vi.fn() }; }
  createGain() {
    const node = { gain: { value: 1 }, connect: vi.fn(), disconnect: vi.fn() };
    mocks.gains.push(node);
    return node;
  }
  createMediaStreamDestination() { return { stream: new FakeMediaStream() }; }
  close = vi.fn().mockResolvedValue(undefined);
  resume = vi.fn().mockResolvedValue(undefined);
}

class FakeAudioWorkletNode {
  port = { onmessage: null as ((event: MessageEvent<ArrayBuffer>) => void) | null };
  connect = vi.fn();
  disconnect = vi.fn();
  constructor() { mocks.worklets.push(this); }
}

describe('useAudioCapture microphone gain', () => {
  beforeEach(() => {
    mocks.gains.length = 0;
    mocks.worklets.length = 0;
    vi.stubGlobal('AudioContext', FakeAudioContext);
    vi.stubGlobal('AudioWorkletNode', FakeAudioWorkletNode);
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        getUserMedia: vi.fn().mockResolvedValue(new FakeMediaStream()),
        enumerateDevices: vi.fn().mockResolvedValue([]),
      },
    });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('applies mic volume to the caption and outgoing room-audio paths', async () => {
    const onChunk = vi.fn();
    const { result } = renderHook(() => useAudioCapture({ onChunk }));
    let outgoing!: MediaStream;
    await act(async () => { outgoing = await result.current.startCapture(); });
    expect(outgoing.getAudioTracks()).toHaveLength(1);
    expect(result.current.isCapturing).toBe(true);
    expect(mocks.gains[0].connect).toHaveBeenCalledTimes(2);

    act(() => { result.current.setMicrophoneGain(150); });
    expect(result.current.microphoneGain).toBe(150);
    expect(mocks.gains[0].gain.value).toBe(1.5);

    const chunk = new Int16Array([0, 16_000, -16_000]).buffer;
    act(() => { mocks.worklets[0].port.onmessage?.({ data: chunk } as MessageEvent<ArrayBuffer>); });
    expect(onChunk).toHaveBeenCalledWith(chunk);
    expect(result.current.inputLevel).toBeGreaterThan(0);

    act(() => { result.current.stopCapture(); });
    expect(result.current.isCapturing).toBe(false);
    expect(result.current.inputLevel).toBe(0);
  });
});
