import { useEffect, useRef, useState } from 'react';
import type { Stage as IvsStage, StageStrategy, StageStream } from 'amazon-ivs-web-broadcast';
import { createViewerMediaToken } from '../services/roomService';

export default function RoomScreenViewer({ roomCode, active }: { roomCode: string; active: boolean }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!active) {
      if (videoRef.current) videoRef.current.srcObject = null;
      return undefined;
    }
    let disposed = false;
    let stage: IvsStage | null = null;
    void (async () => {
      try {
        const { Stage, StageEvents, SubscribeType } = await import('amazon-ivs-web-broadcast');
        const token = await createViewerMediaToken(roomCode);
        if (disposed) return;
        const strategy: StageStrategy = {
          stageStreamsToPublish: () => [],
          shouldPublishParticipant: () => false,
          shouldSubscribeToParticipant: () => SubscribeType.AUDIO_VIDEO,
        };
        stage = new Stage(token, strategy);
        stage.on(StageEvents.STAGE_PARTICIPANT_STREAMS_ADDED, (_participant, streams: StageStream[]) => {
          if (!videoRef.current) return;
          videoRef.current.srcObject = new MediaStream(streams.map((stream) => stream.mediaStreamTrack));
          void videoRef.current.play().catch(() => setError('Tap the video to enable playback audio.'));
        });
        await stage.join();
      } catch (caught) {
        if (!disposed) setError(caught instanceof Error ? caught.message : 'Could not load the shared screen.');
      }
    })();
    return () => {
      disposed = true;
      stage?.leave();
    };
  }, [active, roomCode]);

  return (
    <div className="relative aspect-video overflow-hidden rounded-2xl bg-[#071225] shadow-brutal">
      <video ref={videoRef} autoPlay playsInline controls className="h-full w-full object-contain" />
      {!active && <div className="absolute inset-0 grid place-items-center text-sm font-semibold text-white/60">Waiting for the host to share a screen</div>}
      {error && <div className="absolute bottom-3 left-3 right-3 rounded-lg bg-black/75 px-3 py-2 text-xs text-white">{error}</div>}
    </div>
  );
}
