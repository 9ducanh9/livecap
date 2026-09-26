import { useEffect, useRef, useState } from 'react';
import type { Stage as IvsStage, StageStrategy, StageStream } from 'amazon-ivs-web-broadcast';
import { createViewerMediaToken } from '../services/roomService';
import { captionChunks } from './captionChunks';

type Subtitle = { id: string; textVi: string; textEn: string; language: 'vi' | 'en' | 'both' };
type VideoRect = { left: number; top: number; width: number; height: number };

export default function RoomScreenViewer({ roomCode, active, subtitle }: { roomCode: string; active: boolean; subtitle?: Subtitle }) {
  const frameRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [videoRect, setVideoRect] = useState<VideoRect>({ left: 0, top: 0, width: 320, height: 180 });

  useEffect(() => {
    const frame = frameRef.current;
    const video = videoRef.current;
    if (!frame || !video) return;
    const measure = () => {
      const width = frame.clientWidth;
      const height = frame.clientHeight;
      if (!width || !height) return;
      const frameRatio = width / height;
      const videoRatio = video.videoWidth && video.videoHeight ? video.videoWidth / video.videoHeight : frameRatio;
      if (videoRatio > frameRatio) {
        const contentHeight = width / videoRatio;
        setVideoRect({ left: 0, top: (height - contentHeight) / 2, width, height: contentHeight });
      } else {
        const contentWidth = height * videoRatio;
        setVideoRect({ left: (width - contentWidth) / 2, top: 0, width: contentWidth, height });
      }
    };
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure);
    observer?.observe(frame);
    video.addEventListener('loadedmetadata', measure);
    video.addEventListener('resize', measure);
    measure();
    return () => {
      observer?.disconnect();
      video.removeEventListener('loadedmetadata', measure);
      video.removeEventListener('resize', measure);
    };
  }, []);

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
    <div ref={frameRef} className="relative aspect-video overflow-hidden rounded-2xl bg-[#071225] shadow-brutal">
      <video ref={videoRef} autoPlay playsInline controls className="h-full w-full object-contain" />
      {subtitle && (
        <div className="pointer-events-none absolute" style={videoRect}>
          <VideoSubtitle key={`${subtitle.id}:${subtitle.language}`} subtitle={subtitle} videoWidth={videoRect.width} />
        </div>
      )}
      {!active && <div className="absolute inset-0 grid place-items-center text-sm font-semibold text-white/60">Waiting for the host to share a screen</div>}
      {error && <div className="absolute bottom-3 left-3 right-3 rounded-lg bg-black/75 px-3 py-2 text-xs text-white">{error}</div>}
    </div>
  );
}

function VideoSubtitle({ subtitle, videoWidth }: { subtitle: Subtitle; videoWidth: number }) {
  const [chunkIndex, setChunkIndex] = useState(0);
  const fontSize = Math.min(22, Math.max(11, videoWidth * 0.028));
  const lineCount = subtitle.language === 'both' ? 1 : 2;
  const maxChars = Math.max(20, Math.floor((videoWidth * 0.84 / (fontSize * 0.58)) * lineCount * 0.72));
  const viChunks = captionChunks(subtitle.textVi, maxChars);
  const enChunks = captionChunks(subtitle.textEn, maxChars);
  const totalChunks = subtitle.language === 'both'
    ? Math.max(viChunks.length, enChunks.length)
    : subtitle.language === 'vi' ? viChunks.length : enChunks.length;

  useEffect(() => {
    if (totalChunks <= 1) return;
    const timer = window.setInterval(() => setChunkIndex((index) => (index + 1) % totalChunks), 3500);
    return () => window.clearInterval(timer);
  }, [totalChunks]);

  const captionStyle = {
    fontSize,
    WebkitTextStroke: '0.5px rgba(0, 0, 0, 0.95)',
    paintOrder: 'stroke fill' as const,
  };

  return (
    <div className="absolute inset-x-0 bottom-[9%] flex flex-col items-center gap-0.5 text-center font-semibold leading-[1.15] text-white">
      {(subtitle.language === 'vi' || subtitle.language === 'both') && (
        <p className="w-[84%] overflow-hidden [display:-webkit-box] [-webkit-box-orient:vertical] [-webkit-line-clamp:2]" style={{ ...captionStyle, WebkitLineClamp: lineCount }}>
          {viChunks[Math.min(chunkIndex, viChunks.length - 1)]}
        </p>
      )}
      {(subtitle.language === 'en' || subtitle.language === 'both') && (
        <p className="w-[84%] overflow-hidden [display:-webkit-box] [-webkit-box-orient:vertical] [-webkit-line-clamp:2]" style={{ ...captionStyle, WebkitLineClamp: lineCount }}>
          {enChunks[Math.min(chunkIndex, enChunks.length - 1)]}
        </p>
      )}
    </div>
  );
}
