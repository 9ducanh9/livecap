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

import { useCallback, useRef, useState } from 'react';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** The sample rate required by the backend's Expected_Audio_Format. */
const AUDIO_SAMPLE_RATE = 16_000;

// ---------------------------------------------------------------------------
// Public interface
// ---------------------------------------------------------------------------

export interface UseAudioCaptureOptions {
  /** Called with each PCM ArrayBuffer chunk emitted by the AudioWorklet. */
  onChunk: (chunk: ArrayBuffer) => void;
}

export interface UseAudioCaptureReturn {
  /** True while microphone capture is active. */
  isCapturing: boolean;
  /**
   * True when the user denied the microphone permission prompt.
   * The UI should show "Microphone access is required to capture audio".
   */
  permissionDenied: boolean;
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

  // Hold live references so stopCapture() can tear everything down regardless
  // of how many times the component re-renders between start and stop.
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);

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
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: AUDIO_SAMPLE_RATE,
          channelCount: 1,
        },
      });
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

    // 3. Load the PCM processor worklet module.
    //    Vite resolves the URL at build time. The worklet registers itself
    //    under the name 'pcm-processor'.
    try {
      const workerUrl = new URL(
        '../workers/pcm-processor.worklet.ts',
        import.meta.url
      );
      await audioCtx.audioWorklet.addModule(workerUrl.href);
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
  }, []);

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
