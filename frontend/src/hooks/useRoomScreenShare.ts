import { useCallback, useEffect, useRef, useState } from 'react';
import type { Stage as IvsStage, StageStrategy } from 'amazon-ivs-web-broadcast';
import type { HostedRoom } from '../services/roomService';
import { createHostMediaToken, stopRoomMedia } from '../services/roomService';
import { useWebSocket } from './useWebSocket';

export function useRoomScreenShare(room: HostedRoom | null) {
  const [status, setStatus] = useState<'idle' | 'starting' | 'live'>('idle');
  const [error, setError] = useState<string | null>(null);
  const stageRef = useRef<IvsStage | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const workletRef = useRef<AudioWorkletNode | null>(null);
  const remoteActiveRef = useRef(false);
  const { connect, disconnect, sendAudioChunk } = useWebSocket({
    sourceLanguage: 'en-US',
    targetLanguage: 'vi',
    roomCode: room?.roomCode,
    roomToken: room?.hostToken,
    forceSingleStream: true,
    reconnectOnUnexpectedClose: status === 'live',
    onError: (message) => setError(message),
  });

  const cleanupLocal = useCallback(() => {
    workletRef.current?.disconnect();
    workletRef.current = null;
    void audioContextRef.current?.close();
    audioContextRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    stageRef.current?.leave();
    stageRef.current = null;
    disconnect();
    setStatus('idle');
  }, [disconnect]);

  const stop = useCallback(async () => {
    cleanupLocal();
    if (room && remoteActiveRef.current) {
      await stopRoomMedia(room);
      remoteActiveRef.current = false;
    }
  }, [cleanupLocal, room]);

  const start = useCallback(async () => {
    if (!room || status !== 'idle') return;
    setStatus('starting');
    setError(null);
    try {
      const display = await navigator.mediaDevices.getDisplayMedia({
        video: { frameRate: { ideal: 30, max: 30 } },
        audio: true,
      });
      if (display.getVideoTracks().length === 0) throw new Error('No screen video track was selected.');
      streamRef.current = display;
      const { LocalStageStream, Stage, SubscribeType } = await import('amazon-ivs-web-broadcast');
      const token = await createHostMediaToken(room);
      remoteActiveRef.current = true;
      const localStreams = display.getTracks().map((track) => new LocalStageStream(track));
      const strategy: StageStrategy = {
        stageStreamsToPublish: () => localStreams,
        shouldPublishParticipant: () => true,
        shouldSubscribeToParticipant: () => SubscribeType.NONE,
      };
      const stage = new Stage(token, strategy);
      stageRef.current = stage;
      await stage.join();

      const audioTrack = display.getAudioTracks()[0];
      if (audioTrack) {
        try {
          await connect();
          const context = new AudioContext({ sampleRate: 16_000 });
          audioContextRef.current = context;
          await context.audioWorklet.addModule('/worklets/pcm-processor.js');
          const source = context.createMediaStreamSource(new MediaStream([audioTrack]));
          const worklet = new AudioWorkletNode(context, 'pcm-processor');
          workletRef.current = worklet;
          worklet.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
            if (event.data instanceof ArrayBuffer) sendAudioChunk(event.data);
          };
          source.connect(worklet);
          if (context.state === 'suspended') await context.resume();
        } catch {
          workletRef.current?.disconnect();
          workletRef.current = null;
          void audioContextRef.current?.close();
          audioContextRef.current = null;
          disconnect();
          setError('Screen sharing is live, but captions from shared audio are unavailable.');
        }
      }
      display.getVideoTracks()[0].addEventListener('ended', () => void stop(), { once: true });
      setStatus('live');
    } catch (caught) {
      cleanupLocal();
      if (room && remoteActiveRef.current) {
        try {
          await stopRoomMedia(room);
          remoteActiveRef.current = false;
        } catch {
          // The backend retains cleanup_pending state so a later retry can finish.
        }
      }
      setError(caught instanceof Error ? caught.message : 'Could not start screen sharing.');
    }
  }, [cleanupLocal, connect, room, sendAudioChunk, status, stop]);

  useEffect(() => () => {
    cleanupLocal();
    if (room && remoteActiveRef.current) void stopRoomMedia(room);
  }, [cleanupLocal, room]);
  return { status, error, start, stop };
}
