import { useCallback, useEffect, useRef, useState } from 'react';
import type { LocalStageStream as IvsLocalStream, Stage as IvsStage, StageStrategy } from 'amazon-ivs-web-broadcast';
import type { HostedRoom } from '../services/roomService';
import { createHostMediaToken, stopRoomMedia } from '../services/roomService';
import { useWebSocket } from './useWebSocket';

/** One IVS participant publishes the screen and a mixed microphone/screen-audio track. */
export function useRoomScreenShare(room: HostedRoom | null, microphoneActive: boolean) {
  const [status, setStatus] = useState<'idle' | 'starting' | 'live'>('idle');
  const [audioCaptionsActive, setAudioCaptionsActive] = useState(false);
  const [microphonePublished, setMicrophonePublished] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const stageRef = useRef<IvsStage | null>(null);
  const stageStartRef = useRef<Promise<void> | null>(null);
  const stageStreamsRef = useRef<IvsLocalStream[]>([]);
  const remoteActiveRef = useRef(false);
  const displayRef = useRef<MediaStream | null>(null);
  const mixContextRef = useRef<AudioContext | null>(null);
  const mixDestinationRef = useRef<MediaStreamAudioDestinationNode | null>(null);
  const screenMixSourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const microphoneMixSourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const captionContextRef = useRef<AudioContext | null>(null);
  const captionWorkletRef = useRef<AudioWorkletNode | null>(null);
  const captionSinkRef = useRef<GainNode | null>(null);
  const captionStartRef = useRef<Promise<void> | null>(null);
  const microphoneActiveRef = useRef(microphoneActive);
  const screenGenerationRef = useRef(0);
  microphoneActiveRef.current = microphoneActive;

  const { connect, disconnect, disconnectAndWait, sendAudioChunk } = useWebSocket({
    sourceLanguage: 'en-US',
    targetLanguage: 'vi',
    roomCode: room?.roomCode,
    roomToken: room?.hostToken,
    forceSingleStream: true,
    reconnectOnUnexpectedClose: status === 'live' && audioCaptionsActive,
    onError: (message) => setError(message),
  });

  const ensureMixer = useCallback(() => {
    if (!mixContextRef.current || !mixDestinationRef.current) {
      const context = new AudioContext();
      mixContextRef.current = context;
      mixDestinationRef.current = context.createMediaStreamDestination();
    }
    return { context: mixContextRef.current, destination: mixDestinationRef.current };
  }, []);

  const releaseStage = useCallback(async () => {
    await stageStartRef.current?.catch(() => undefined);
    stageRef.current?.leave();
    stageRef.current = null;
    stageStreamsRef.current = [];
    try {
      if (room && remoteActiveRef.current) {
        await stopRoomMedia(room);
        remoteActiveRef.current = false;
      }
    } finally {
      mixDestinationRef.current?.stream.getTracks().forEach((track) => track.stop());
      mixDestinationRef.current = null;
      await mixContextRef.current?.close();
      mixContextRef.current = null;
    }
  }, [room]);

  const publishCurrentMedia = useCallback(async () => {
    if (!room || room.status !== 'live') return;
    const videoTrack = displayRef.current?.getVideoTracks().find((track) => track.readyState === 'live');
    const hasAudio = Boolean(screenMixSourceRef.current || microphoneMixSourceRef.current);
    if (!videoTrack && !hasAudio) {
      await releaseStage();
      return;
    }
    const { LocalStageStream, Stage, SubscribeType } = await import('amazon-ivs-web-broadcast');
    const tracks: MediaStreamTrack[] = [];
    if (videoTrack) tracks.push(videoTrack);
    if (hasAudio) {
      const { context, destination } = ensureMixer();
      if (context.state === 'suspended') await context.resume();
      tracks.push(destination.stream.getAudioTracks()[0]);
    }
    const previous = stageStreamsRef.current;
    const previousByTrack = new Map(previous.map((stream) => [stream.mediaStreamTrack.id, stream]));
    const nextStreams = tracks.map((track) => previousByTrack.get(track.id) ?? new LocalStageStream(track));
    const streamsChanged = previous.length !== nextStreams.length || previous.some((stream, index) => stream !== nextStreams[index]);
    stageStreamsRef.current = nextStreams;
    if (stageRef.current) {
      if (streamsChanged) stageRef.current.refreshStrategy();
      return;
    }
    if (stageStartRef.current) {
      await stageStartRef.current;
      const joinedStage = stageRef.current as IvsStage | null;
      joinedStage?.refreshStrategy();
      return;
    }
    const starting = (async () => {
      const token = await createHostMediaToken(room);
      remoteActiveRef.current = true;
      const strategy: StageStrategy = {
        stageStreamsToPublish: () => stageStreamsRef.current,
        shouldPublishParticipant: () => true,
        shouldSubscribeToParticipant: () => SubscribeType.NONE,
      };
      const stage = new Stage(token, strategy);
      stageRef.current = stage;
      await stage.join();
    })();
    stageStartRef.current = starting;
    try {
      await starting;
    } catch (caught) {
      const failedStage = stageRef.current as IvsStage | null;
      failedStage?.leave();
      stageRef.current = null;
      if (remoteActiveRef.current) {
        try { await stopRoomMedia(room); remoteActiveRef.current = false; } catch { /* Retry on next stop. */ }
      }
      throw caught;
    } finally {
      stageStartRef.current = null;
    }
  }, [ensureMixer, releaseStage, room]);

  const pauseSharedAudioCaptions = useCallback(async () => {
    const closed = disconnectAndWait().then(() => null, (caught: unknown) => caught);
    await captionStartRef.current?.catch(() => undefined);
    captionWorkletRef.current?.disconnect();
    captionWorkletRef.current = null;
    captionSinkRef.current?.disconnect();
    captionSinkRef.current = null;
    await captionContextRef.current?.close();
    captionContextRef.current = null;
    setAudioCaptionsActive(false);
    const closeError = await closed;
    if (closeError) throw closeError;
  }, [disconnectAndWait]);

  const resumeSharedAudioCaptions = useCallback(async () => {
    const audioTrack = displayRef.current?.getAudioTracks()[0];
    if (!audioTrack || audioTrack.readyState !== 'live' || captionContextRef.current || captionStartRef.current) return;
    const starting = (async () => {
      await connect();
      try {
        const context = new AudioContext({ sampleRate: 16_000 });
        captionContextRef.current = context;
        await context.audioWorklet.addModule('/worklets/pcm-processor.js');
        const source = context.createMediaStreamSource(new MediaStream([audioTrack]));
        const worklet = new AudioWorkletNode(context, 'pcm-processor');
        captionWorkletRef.current = worklet;
        const sink = context.createGain();
        sink.gain.value = 0;
        captionSinkRef.current = sink;
        worklet.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
          if (event.data instanceof ArrayBuffer) sendAudioChunk(event.data);
        };
        source.connect(worklet);
        worklet.connect(sink);
        sink.connect(context.destination);
        if (context.state === 'suspended') await context.resume();
        setAudioCaptionsActive(true);
        setError(null);
      } catch (caught) {
        captionWorkletRef.current?.disconnect();
        captionWorkletRef.current = null;
        captionSinkRef.current?.disconnect();
        captionSinkRef.current = null;
        await captionContextRef.current?.close();
        captionContextRef.current = null;
        disconnect();
        throw caught;
      }
    })();
    captionStartRef.current = starting;
    try { await starting; } finally { captionStartRef.current = null; }
  }, [connect, disconnect, sendAudioChunk]);

  const setMicrophoneStream = useCallback(async (stream: MediaStream | null) => {
    microphoneMixSourceRef.current?.disconnect();
    microphoneMixSourceRef.current = null;
    const track = stream?.getAudioTracks()[0];
    if (track?.readyState === 'live') {
      const { context, destination } = ensureMixer();
      const source = context.createMediaStreamSource(new MediaStream([track]));
      source.connect(destination);
      microphoneMixSourceRef.current = source;
      if (context.state === 'suspended') await context.resume();
    }
    try {
      await publishCurrentMedia();
      setMicrophonePublished(Boolean(microphoneMixSourceRef.current));
    } catch (caught) {
      microphoneMixSourceRef.current?.disconnect();
      microphoneMixSourceRef.current = null;
      setMicrophonePublished(false);
      throw caught;
    }
  }, [ensureMixer, publishCurrentMedia]);

  const stop = useCallback(async () => {
    screenGenerationRef.current += 1;
    try { await pauseSharedAudioCaptions(); } catch { disconnect(); }
    screenMixSourceRef.current?.disconnect();
    screenMixSourceRef.current = null;
    displayRef.current?.getTracks().forEach((track) => track.stop());
    displayRef.current = null;
    setStatus('idle');
    await publishCurrentMedia();
  }, [disconnect, pauseSharedAudioCaptions, publishCurrentMedia]);

  const stopAll = useCallback(async () => {
    try { await stop(); }
    finally { await setMicrophoneStream(null); }
  }, [setMicrophoneStream, stop]);

  const start = useCallback(async () => {
    if (!room || room.status !== 'live' || status !== 'idle') return;
    const generation = ++screenGenerationRef.current;
    setStatus('starting');
    setError(null);
    try {
      const display = await navigator.mediaDevices.getDisplayMedia({
        video: { frameRate: { ideal: 30, max: 30 } },
        audio: true,
      });
      if (generation !== screenGenerationRef.current) {
        display.getTracks().forEach((track) => track.stop());
        return;
      }
      const videoTrack = display.getVideoTracks()[0];
      if (!videoTrack) throw new Error('No screen video track was selected.');
      displayRef.current = display;
      const audioTrack = display.getAudioTracks()[0];
      if (audioTrack) {
        const { context, destination } = ensureMixer();
        const source = context.createMediaStreamSource(new MediaStream([audioTrack]));
        source.connect(destination);
        screenMixSourceRef.current = source;
        if (context.state === 'suspended') await context.resume();
      }
      await publishCurrentMedia();
      if (generation !== screenGenerationRef.current) return;
      videoTrack.addEventListener('ended', () => void stop(), { once: true });
      setStatus('live');
      if (audioTrack && !microphoneActiveRef.current) {
        try { await resumeSharedAudioCaptions(); }
        catch { setError('Screen sharing is live, but captions from shared audio are unavailable.'); }
      }
    } catch (caught) {
      screenMixSourceRef.current?.disconnect();
      screenMixSourceRef.current = null;
      displayRef.current?.getTracks().forEach((track) => track.stop());
      displayRef.current = null;
      setStatus('idle');
      try { await publishCurrentMedia(); } catch { /* Keep original error. */ }
      setError(caught instanceof Error ? caught.message : 'Could not start screen sharing.');
    }
  }, [ensureMixer, publishCurrentMedia, resumeSharedAudioCaptions, room, status, stop]);

  useEffect(() => () => {
    screenGenerationRef.current += 1;
    captionWorkletRef.current?.disconnect();
    captionSinkRef.current?.disconnect();
    void captionContextRef.current?.close();
    disconnect();
    screenMixSourceRef.current?.disconnect();
    microphoneMixSourceRef.current?.disconnect();
    displayRef.current?.getTracks().forEach((track) => track.stop());
    stageRef.current?.leave();
    mixDestinationRef.current?.stream.getTracks().forEach((track) => track.stop());
    void mixContextRef.current?.close();
    if (room && remoteActiveRef.current) void stopRoomMedia(room);
  }, [disconnect, room]);

  return { status, error, audioCaptionsActive, microphonePublished, start, stop, stopAll, setMicrophoneStream, pauseSharedAudioCaptions, resumeSharedAudioCaptions };
}
