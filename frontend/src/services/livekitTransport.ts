import { Room, RoomEvent, Track, type LocalTrackPublication } from 'livekit-client';

export type MediaCredential = { token: string; provider: 'livekit'; url: string };

/** Publishes existing capture tracks; capture ownership stays with the caller. */
export class LiveKitPublisher {
  private room = new Room({ adaptiveStream: true, dynacast: true });
  private publications = new Map<string, LocalTrackPublication>();
  private updates = Promise.resolve();
  constructor(private credential: MediaCredential) {}

  async join() { await this.room.connect(this.credential.url, this.credential.token, { autoSubscribe: false }); }

  update(tracks: MediaStreamTrack[]) {
    this.updates = this.updates.catch(() => undefined).then(async () => {
      const ids = new Set(tracks.map(track => track.id));
      for (const [id, publication] of this.publications) {
        if (!ids.has(id) && publication.track) {
          await this.room.localParticipant.unpublishTrack(publication.track, false);
          this.publications.delete(id);
        }
      }
      for (const track of tracks) {
        if (this.publications.has(track.id)) continue;
        if (track.kind === 'video') track.contentHint = 'motion';
        const publication = await this.room.localParticipant.publishTrack(track, {
          source: track.kind === 'video' ? Track.Source.ScreenShare : Track.Source.Microphone,
          screenShareEncoding: { maxBitrate: 3_000_000, maxFramerate: 30 },
          audioPreset: { maxBitrate: 128_000 },
          forceStereo: true,
          dtx: false,
          red: true,
          simulcast: true,
        });
        this.publications.set(track.id, publication);
      }
    });
    return this.updates;
  }

  async leave() {
    await this.updates.catch(() => undefined);
    await this.room.disconnect(false);
    this.publications.clear();
  }
}

export async function connectLiveKitViewer(
  credential: MediaCredential,
  onTracks: (tracks: MediaStreamTrack[]) => void,
  element?: HTMLVideoElement,
) {
  const room = new Room({ adaptiveStream: true });
  const tracks = new Map<string, MediaStreamTrack>();
  const attached = new Set<import('livekit-client').RemoteTrack>();
  room.on(RoomEvent.TrackSubscribed, track => {
    if (element) { track.attach(element); attached.add(track); }
    tracks.set(track.sid!, track.mediaStreamTrack);
    onTracks([...tracks.values()]);
  });
  room.on(RoomEvent.TrackUnsubscribed, track => {
    if (element) track.detach(element);
    attached.delete(track);
    tracks.delete(track.sid!);
    onTracks([...tracks.values()]);
  });
  room.on(RoomEvent.Disconnected, () => { tracks.clear(); onTracks([]); });
  try { await room.connect(credential.url, credential.token); }
  catch (error) { await room.disconnect(); throw error; }
  return { leave: async () => {
    await room.disconnect();
    if (element) for (const track of attached) track.detach(element);
    attached.clear();
  } };
}
