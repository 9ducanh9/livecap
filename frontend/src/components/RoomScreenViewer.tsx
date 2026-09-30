import { useEffect, useRef, useState } from 'react';
import type { Stage as IvsStage, StageStrategy, StageStream } from 'amazon-ivs-web-broadcast';
import { createViewerMediaToken } from '../services/roomService';
import type { Segment } from '../types';
import { captionChunks } from './captionChunks';

type VideoRect = { left: number; top: number; width: number; height: number };

export default function RoomScreenViewer({ roomCode, active, subtitleSegments, subtitleLanguage = 'vi', muted = false, onVideoStateChange }: { roomCode: string; active: boolean; subtitleSegments?: Segment[]; subtitleLanguage?: 'vi' | 'en'; muted?: boolean; onVideoStateChange?: (hasVideo: boolean) => void }) {
  const frameRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [needsGesture, setNeedsGesture] = useState(false);
  const [mediaKind, setMediaKind] = useState<'none' | 'audio' | 'video'>('none');
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
      setError(null);
      setNeedsGesture(false);
      setMediaKind('none');
      onVideoStateChange?.(false);
      return undefined;
    }
    setError(null);
    setNeedsGesture(false);
    let disposed = false;
    let stage: IvsStage | null = null;
    const tracks = new Map<string, MediaStreamTrack>();
    const updateMedia = () => {
      const video = videoRef.current;
      if (!video || disposed) return;
      const currentTracks = [...tracks.values()];
      video.srcObject = currentTracks.length ? new MediaStream(currentTracks) : null;
      const hasVideo = currentTracks.some((track) => track.kind === 'video');
      setMediaKind(hasVideo ? 'video' : currentTracks.length ? 'audio' : 'none');
      onVideoStateChange?.(hasVideo);
      if (currentTracks.length) {
        void video.play().catch(() => {
          if (!muted) {
            setNeedsGesture(true);
            setError('Your browser paused live audio. Tap Enable sound.');
          }
        });
      }
    };
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
          streams.forEach((stream) => tracks.set(stream.mediaStreamTrack.id, stream.mediaStreamTrack));
          updateMedia();
        });
        stage.on(StageEvents.STAGE_PARTICIPANT_STREAMS_REMOVED, (_participant, streams: StageStream[]) => {
          streams.forEach((stream) => tracks.delete(stream.mediaStreamTrack.id));
          updateMedia();
        });
        await stage.join();
      } catch (caught) {
        if (!disposed) setError(caught instanceof Error ? caught.message : 'Could not load the shared screen.');
      }
    })();
    return () => {
      disposed = true;
      stage?.leave();
      tracks.clear();
    };
  }, [active, muted, onVideoStateChange, roomCode]);

  return (
    <div ref={frameRef} className="relative aspect-video overflow-hidden rounded-2xl bg-[#071225] shadow-brutal">
      <video ref={videoRef} autoPlay playsInline controls={!muted} muted={muted} className="h-full w-full object-contain" />
      {subtitleSegments && (
        <div className="pointer-events-none absolute" style={videoRect}>
          <VideoSubtitle key={`${roomCode}:${subtitleLanguage}`} segments={subtitleSegments} language={subtitleLanguage} videoWidth={videoRect.width} />
        </div>
      )}
      {!active && <div className="absolute inset-0 grid place-items-center text-sm font-semibold text-white/60">Waiting for the host to share a screen</div>}
      {active && mediaKind === 'none' && <div className="pointer-events-none absolute inset-0 grid place-items-center text-sm font-semibold text-white/60">Connecting live media...</div>}
      {active && mediaKind === 'audio' && <div className="pointer-events-none absolute inset-0 grid place-items-center text-sm font-semibold text-white/60">Host microphone is live · screen not shared</div>}
      {needsGesture && !muted && (
        <button
          type="button"
          onClick={() => void videoRef.current?.play().then(() => { setNeedsGesture(false); setError(null); }).catch(() => setError('Could not start audio. Check this tab’s sound permissions.'))}
          className="absolute bottom-12 left-1/2 z-10 -translate-x-1/2 rounded-lg bg-white px-4 py-2 text-xs font-bold text-ink shadow-lg"
        >Enable sound</button>
      )}
      {error && <div className="absolute bottom-3 left-3 right-3 rounded-lg bg-black/75 px-3 py-2 text-xs text-white">{error}</div>}
    </div>
  );
}

function VideoSubtitle({ segments, language, videoWidth }: { segments: Segment[]; language: 'vi' | 'en'; videoWidth: number }) {
  const [queue, setQueue] = useState<Array<{ id: string; text: string }>>([]);
  const seenCountRef = useRef(Math.max(0, segments.length - 1));
  const initializedRef = useRef(segments.length > 0);
  const baseFontSize = Math.min(22, Math.max(11, videoWidth * 0.028));
  const maxChars = Math.max(12, Math.floor(videoWidth * 0.82 / (baseFontSize * 0.7)));

  useEffect(() => {
    // A late joiner starts with the newest caption, not the whole archive.
    const start = !initializedRef.current && segments.length > 0
      ? segments.length - 1
      : Math.min(seenCountRef.current, segments.length);
    const incoming = segments.slice(start).flatMap((segment) =>
      captionChunks(language === 'vi' ? segment.textVi : segment.textEn, maxChars)
        .map((text, index) => ({ id: `${segment.segmentId}:${index}`, text })),
    );
    seenCountRef.current = segments.length;
    if (segments.length > 0) initializedRef.current = true;
    if (incoming.length) setQueue((current) => [...current, ...incoming]);
  }, [language, maxChars, segments]);

  const current = queue[0];
  useEffect(() => {
    if (!current) return undefined;
    const duration = Math.max(1_300, Math.min(2_600, current.text.length * 55));
    const timer = window.setTimeout(() => setQueue((pending) => pending.slice(1)), duration);
    return () => window.clearTimeout(timer);
  }, [current?.id]);

  if (!current) return null;

  const fontSize = Math.min(baseFontSize, videoWidth * 0.82 / (current.text.length * 0.7));

  const captionStyle = {
    fontSize,
    WebkitTextStroke: '0.5px rgba(0, 0, 0, 0.95)',
    paintOrder: 'stroke fill' as const,
  };

  return (
    <div className="absolute inset-x-0 bottom-[9%] flex justify-center text-center font-semibold leading-[1.15] text-white">
      <p className="max-w-[82%] whitespace-nowrap" style={captionStyle}>{current.text}</p>
    </div>
  );
}
