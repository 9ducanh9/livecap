/**
 * useAudioCapture — Microphone capture hook.
 *
 * Responsibilities (Requirements 1.1, 1.2, 1.3, 1.4, 2.3):
 *  - On startCapture: request microphone access via getUserMedia with explicit
 *    audio constraints (sampleRate: 16000, channelCount: 1).
 *  - Build the Web Audio pipeline:
 *      AudioContext (16 kHz) → MediaStreamSource → AudioWorkletNode('pcm-processor')
 *  - Forward every ArrayBuffer chunk emitted by the worklet to the onChunk
 *    callback so the WebSocket client can stream it to the backend.
 *  - Expose permissionDenied so the UI can display
 *    "Microphone access is required to capture audio" (Requirement 1.3).
 *  - On stopCapture: stop all MediaStream tracks and close the AudioContext
 *    (Requirement 1.4).
 */

import { useCallback, useEffect, useRef, useState } from 'react';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** The sample rate required by the backend's Expected_Audio_Format. */
const AUDIO_SAMPLE_RATE = 16_000;

/** Enable verbose audio pipeline logs with VITE_AUDIO_DEBUG=true. */
const DEBUG = import.meta.env.VITE_AUDIO_DEBUG === 'true';

const DEFAULT_AUDIO_INPUT_ID = 'default';

// ---------------------------------------------------------------------------
// Public interface
// ---------------------------------------------------------------------------

export interface UseAudioCaptureOptions {
  /** Called with each PCM ArrayBuffer chunk emitted by the AudioWorklet. */
  onChunk: (chunk: ArrayBuffer) => void;
}

export interface AudioInputDevice {
  deviceId: string;
  label: string;
}

export interface UseAudioCaptureReturn {
  /** True while microphone capture is active. */
  isCapturing: boolean;
  /**
   * True when the user denied the microphone permission prompt.
   * The UI should show "Microphone access is required to capture audio".
   */
  permissionDenied: boolean;
  /** Available microphone input devices reported by the browser. */
  audioInputDevices: AudioInputDevice[];
  /** Selected microphone deviceId. "default" lets the browser choose. */
  selectedDeviceId: string;
  /** Select the microphone used by the next startCapture call. */
  setSelectedDeviceId: (deviceId: string) => void;
  /** Refresh the browser audio input device list. */
  refreshAudioInputDevices: () => Promise<void>;
  /** Start capturing audio. Resolves once the pipeline is ready (or rejects on error). */
  startCapture: () => Promise<void>;
  /** Stop capturing audio and release the microphone. */
  stopCapture: () => void;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useAudioCapture(
  options: UseAudioCaptureOptions
): UseAudioCaptureReturn {
  const onChunkRef = useRef(options.onChunk);
  // Keep the ref current so callers can pass a fresh callback each render
  // without triggering unnecessary effect re-runs.
  onChunkRef.current = options.onChunk;

  const [isCapturing, setIsCapturing] = useState(false);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [audioInputDevices, setAudioInputDevices] = useState<AudioInputDevice[]>([]);
  const [selectedDeviceId, setSelectedDeviceIdState] = useState(DEFAULT_AUDIO_INPUT_ID);

  // Hold live references so stopCapture() can tear everything down regardless
  // of how many times the component re-renders between start and stop.
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const selectedDeviceIdRef = useRef(DEFAULT_AUDIO_INPUT_ID);

  const setSelectedDeviceId = useCallback((deviceId: string) => {
    const nextDeviceId = deviceId || DEFAULT_AUDIO_INPUT_ID;
    selectedDeviceIdRef.current = nextDeviceId;
    setSelectedDeviceIdState(nextDeviceId);
  }, []);

  const refreshAudioInputDevices = useCallback(async () => {
    if (!navigator.mediaDevices?.enumerateDevices) return;

    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      const inputs = devices
        .filter(
          (device) =>
            device.kind === 'audioinput' &&
            device.deviceId !== '' &&
            device.deviceId !== DEFAULT_AUDIO_INPUT_ID
        )
        .map((device, index) => ({
          deviceId: device.deviceId || DEFAULT_AUDIO_INPUT_ID,
          label: device.label || `Microphone ${index + 1}`,
        }));

      setAudioInputDevices(inputs);

      const currentDeviceId = selectedDeviceIdRef.current;
      const selectedDeviceStillExists =
        currentDeviceId === DEFAULT_AUDIO_INPUT_ID ||
        inputs.some((device) => device.deviceId === currentDeviceId);

      if (!selectedDeviceStillExists) {
        setSelectedDeviceId(DEFAULT_AUDIO_INPUT_ID);
      }
    } catch (err) {
      debugLog('audio-input-enumeration-failed', { error: err });
    }
  }, [setSelectedDeviceId]);

  useEffect(() => {
    void refreshAudioInputDevices();

    if (!navigator.mediaDevices?.addEventListener) return undefined;

    const handleDeviceChange = () => {
      void refreshAudioInputDevices();
    };

    navigator.mediaDevices.addEventListener('devicechange', handleDeviceChange);
    return () => {
      navigator.mediaDevices.removeEventListener('devicechange', handleDeviceChange);
    };
  }, [refreshAudioInputDevices]);

  // ------------------------------------------------------------------
  // startCapture — build the capture pipeline
  // ------------------------------------------------------------------
  const startCapture = useCallback(async () => {
    // Guard against a double-start.
    if (mediaStreamRef.current !== null) return;

    // Reset any previous permission-denied state so the user can retry.
    setPermissionDenied(false);

    // 1. Request microphone access with explicit audio constraints (Req 1.1, 1.2).
    //    Requesting sampleRate: 16000 and channelCount: 1 hints to the browser
    //    to open the device at the target rate. Some browsers may ignore the
    //    sampleRate hint; the PCM worklet handles downsampling internally.
    let stream: MediaStream;
    const requestedDeviceId = selectedDeviceIdRef.current;
    const audioConstraints: MediaTrackConstraints = {
      sampleRate: AUDIO_SAMPLE_RATE,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
      channelCount: 1,
      ...(requestedDeviceId !== DEFAULT_AUDIO_INPUT_ID
        ? { deviceId: { exact: requestedDeviceId } }
        : {}),
    };

    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: audioConstraints,
      });
      debugLog('microphone-started', {
        trackCount: stream.getAudioTracks().length,
        requestedSampleRate: AUDIO_SAMPLE_RATE,
        requestedDeviceId,
      });
      void refreshAudioInputDevices();
    } catch (err) {
      // NotAllowedError / PermissionDeniedError → user denied (Requirement 1.3).
      const isDenied =
        err instanceof DOMException &&
        (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError');

      if (isDenied) {
        setPermissionDenied(true);
      } else {
        // Other errors (NotFoundError, hardware failure, etc.) are surfaced
        // to the caller via the thrown exception.
        console.error('[useAudioCapture] getUserMedia failed:', err);
      }
      throw err;
    }

    mediaStreamRef.current = stream;

    // 2. Create an AudioContext at 16 kHz.
    //    Some browsers ignore the sampleRate hint and create the context at
    //    their native rate (e.g. 48 kHz); the PCM worklet handles downsampling
    //    to 16 kHz internally, so the pipeline is correct regardless.
    let audioCtx: AudioContext;
    try {
      audioCtx = new AudioContext({ sampleRate: AUDIO_SAMPLE_RATE });
    } catch (err) {
      // Clean up the stream if we cannot create the context.
      releaseStream(stream);
      mediaStreamRef.current = null;
      console.error('[useAudioCapture] Failed to create AudioContext:', err);
      throw err;
    }

    audioContextRef.current = audioCtx;
    debugLog('audio-context-created', {
      frontendSampleRate: audioCtx.sampleRate,
      targetSampleRate: AUDIO_SAMPLE_RATE,
    });

    // 3. Load the PCM processor worklet module. Keep this as a plain JS file
    //    in public/ because browsers load AudioWorklet modules directly.
    try {
      await audioCtx.audioWorklet.addModule('/worklets/pcm-processor.js');
    } catch (err) {
      audioCtx.close().catch(() => undefined);
      releaseStream(stream);
      audioContextRef.current = null;
      mediaStreamRef.current = null;
      console.error('[useAudioCapture] Failed to load AudioWorklet module:', err);
      throw err;
    }

    // 4. Wire up: MediaStreamSource → AudioWorkletNode('pcm-processor').
    const source = audioCtx.createMediaStreamSource(stream);
    const workletNode = new AudioWorkletNode(audioCtx, 'pcm-processor');
    workletNodeRef.current = workletNode;

    // 5. Receive PCM chunks from the worklet and forward them to the caller
    //    (Requirement 2.3).
    workletNode.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
      if (event.data instanceof ArrayBuffer) {
        debugLog('audio-chunk-produced', {
          frontendSampleRate: audioCtx.sampleRate,
          resampledChunkLength: event.data.byteLength / 2,
          pcmByteLength: event.data.byteLength,
          rms: computePcm16Rms(event.data),
        });
        onChunkRef.current(event.data);
      }
    };

    // Connect the graph — do NOT connect to destination (no audio playback).
    source.connect(workletNode);

    // If the AudioContext was created in a suspended state (autoplay policy),
    // resume it so audio flows.
    if (audioCtx.state === 'suspended') {
      await audioCtx.resume();
    }

    setIsCapturing(true);
  }, [refreshAudioInputDevices]);

  // ------------------------------------------------------------------
  // stopCapture — tear down the pipeline and release the microphone
  // ------------------------------------------------------------------
  const stopCapture = useCallback(() => {
    // Disconnect the worklet node first to stop message callbacks.
    if (workletNodeRef.current !== null) {
      workletNodeRef.current.port.onmessage = null;
      workletNodeRef.current.disconnect();
      workletNodeRef.current = null;
    }

    // Close the AudioContext (releases all associated resources).
    if (audioContextRef.current !== null) {
      audioContextRef.current.close().catch((err) => {
        console.warn('[useAudioCapture] Error closing AudioContext:', err);
      });
      audioContextRef.current = null;
    }

    // Stop all microphone tracks and release the MediaStream (Requirement 1.4).
    if (mediaStreamRef.current !== null) {
      releaseStream(mediaStreamRef.current);
      mediaStreamRef.current = null;
    }

    setIsCapturing(false);
  }, []);

  return {
    isCapturing,
    permissionDenied,
    audioInputDevices,
    selectedDeviceId,
    setSelectedDeviceId,
    refreshAudioInputDevices,
    startCapture,
    stopCapture,
  };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Stop every track on a MediaStream to release the hardware resource. */
function releaseStream(stream: MediaStream): void {
  stream.getTracks().forEach((track) => track.stop());
}

function computePcm16Rms(chunk: ArrayBuffer): number {
  const samples = new Int16Array(chunk);
  if (samples.length === 0) return 0;

  let sumSquares = 0;
  for (let i = 0; i < samples.length; i += 1) {
    const normalized = samples[i] / 32768;
    sumSquares += normalized * normalized;
  }

  return Math.sqrt(sumSquares / samples.length);
}

function debugLog(message: string, data: Record<string, unknown>): void {
  if (!DEBUG) return;
  console.debug(`[useAudioCapture] ${message}`, data);
}
