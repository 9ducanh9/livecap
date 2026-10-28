import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LiveKitPublisher, connectLiveKitViewer } from './livekitTransport';

const mocks = vi.hoisted(() => ({ instances: [] as Array<{
  connect: ReturnType<typeof vi.fn>; disconnect: ReturnType<typeof vi.fn>;
  localParticipant: { publishTrack: ReturnType<typeof vi.fn>; unpublishTrack: ReturnType<typeof vi.fn> };
  handlers: Map<string, (...args: any[]) => void>;
}> }));

vi.mock('livekit-client', () => ({
  Track: { Source: { ScreenShare: 'screen_share', Microphone: 'microphone' } },
  RoomEvent: { TrackSubscribed: 'subscribed', TrackUnsubscribed: 'unsubscribed', Disconnected: 'disconnected' },
  Room: class {
    connect = vi.fn().mockResolvedValue(undefined);
    disconnect = vi.fn().mockResolvedValue(undefined);
    handlers = new Map();
    localParticipant = {
      publishTrack: vi.fn(async (track: MediaStreamTrack) => ({ track })),
      unpublishTrack: vi.fn().mockResolvedValue(undefined),
    };
    on(event: string, handler: (...args: any[]) => void) { this.handlers.set(event, handler); }
    constructor() { mocks.instances.push(this); }
  },
}));

const credential = { token: 'test-token', provider: 'livekit' as const, url: 'wss://test.livekit.cloud' };
describe('LiveKit media transport', () => {
  beforeEach(() => { mocks.instances.length = 0; });
  it('publishes existing tracks and preserves capture when removing video', async () => {
    const publisher = new LiveKitPublisher(credential);
    const video = { id: 'screen', kind: 'video', stop: vi.fn() } as unknown as MediaStreamTrack;
    const audio = { id: 'mix', kind: 'audio', stop: vi.fn() } as unknown as MediaStreamTrack;
    await publisher.join();
    await publisher.update([video, audio]);
    await publisher.update([audio]);
    const room = mocks.instances[0];
    expect(room.connect).toHaveBeenCalledWith(credential.url, credential.token, { autoSubscribe: false });
    expect(room.localParticipant.publishTrack).toHaveBeenCalledTimes(2);
    expect(room.localParticipant.publishTrack).toHaveBeenCalledWith(video, expect.objectContaining({
      source: 'screen_share', screenShareEncoding: { maxBitrate: 3_000_000, maxFramerate: 30 },
    }));
    expect(video.contentHint).toBe('motion');
    expect(room.localParticipant.publishTrack).toHaveBeenCalledWith(audio, expect.objectContaining({
      audioPreset: { maxBitrate: 128_000 }, forceStereo: true, dtx: false, red: true,
    }));
    expect(room.localParticipant.unpublishTrack).toHaveBeenCalledWith(video, false);
    expect(video.stop).not.toHaveBeenCalled();
    await publisher.leave();
    expect(room.disconnect).toHaveBeenCalledWith(false);
  });
  it('updates viewer media on subscribe, unpublish and disconnect without publishing', async () => {
    const changed = vi.fn();
    const viewer = await connectLiveKitViewer(credential, changed);
    const room = mocks.instances[0];
    const track = { sid: 'remote-screen', mediaStreamTrack: { kind: 'video' } };
    room.handlers.get('subscribed')!(track);
    expect(changed).toHaveBeenLastCalledWith([track.mediaStreamTrack]);
    room.handlers.get('unsubscribed')!(track);
    expect(changed).toHaveBeenLastCalledWith([]);
    expect(room.localParticipant.publishTrack).not.toHaveBeenCalled();
    await viewer.leave();
    expect(room.disconnect).toHaveBeenCalled();
  });
  it('attaches and detaches remote tracks through the SDK for adaptive stream', async () => {
    const element = document.createElement('video');
    const viewer = await connectLiveKitViewer(credential, vi.fn(), element);
    const room = mocks.instances[0];
    const track = { sid: 'screen', mediaStreamTrack: { kind: 'video' }, attach: vi.fn(), detach: vi.fn() };
    room.handlers.get('subscribed')!(track);
    expect(track.attach).toHaveBeenCalledWith(element);
    room.handlers.get('unsubscribed')!(track);
    expect(track.detach).toHaveBeenCalledWith(element);
    room.handlers.get('subscribed')!(track);
    await viewer.leave();
    expect(track.detach).toHaveBeenCalledTimes(2);
  });
});
