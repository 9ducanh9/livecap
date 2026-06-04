/**
 * PCM AudioWorklet Processor
 *
 * Runs in the AudioWorklet thread. Receives raw microphone audio from the
 * Web Audio graph, downsamples it to 16 kHz mono, and accumulates samples
 * into ~100ms chunks (1 600 samples × 2 bytes = 3 200-byte Int16 frames)
 * before posting them to the main thread as transferable ArrayBuffers.
 *
 * Requirements: 1.2, 2.3
 */

// AudioWorklet globals are not in the default TypeScript lib; declare the
// minimum set we actually use so the file compiles cleanly.
declare const sampleRate: number; // injected by the AudioWorklet runtime

interface AudioWorkletProcessor {
  readonly port: MessagePort;
  process(
    inputs: Float32Array[][],
    outputs: Float32Array[][],
    parameters: Record<string, Float32Array>,
  ): boolean;
}

declare const AudioWorkletProcessor: {
  new (): AudioWorkletProcessor;
  prototype: AudioWorkletProcessor;
};

declare function registerProcessor(
  name: string,
  processorCtor: new () => AudioWorkletProcessor,
): void;

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Target sample rate required by the backend (Expected_Audio_Format). */
const TARGET_SAMPLE_RATE = 16_000;

/**
 * Target chunk duration in seconds (~100 ms).
 * At 16 kHz this equals exactly 1 600 PCM samples per chunk.
 */
const CHUNK_DURATION_S = 0.1;

/** Number of 16 kHz samples per emitted chunk. */
const CHUNK_SAMPLES = Math.round(TARGET_SAMPLE_RATE * CHUNK_DURATION_S); // 1 600

// ---------------------------------------------------------------------------
// Processor implementation
// ---------------------------------------------------------------------------

class PcmProcessor extends AudioWorkletProcessor {
  /** Resampled 16-bit samples accumulated between flushes. */
  private readonly _buffer: Int16Array;
  /** Write cursor into _buffer. */
  private _writePos = 0;

  /**
   * Fractional position in the input stream used by the linear interpolation
   * downsampler.  Advances by (nativeSampleRate / 16000) per output sample.
   */
  private _inputPhase = 0;

  constructor() {
    super();
    this._buffer = new Int16Array(CHUNK_SAMPLES);
  }

  process(inputs: Float32Array[][]): boolean {
    // Take the first channel of the first input (mono microphone source).
    const input = inputs[0];
    if (!input || input.length === 0) return true;
    const channel = input[0];
    if (!channel || channel.length === 0) return true;

    const nativeSampleRate = sampleRate; // context sample rate (e.g. 48 000 Hz)
    const stepSize = nativeSampleRate / TARGET_SAMPLE_RATE;

    let pos = this._inputPhase;

    while (pos < channel.length) {
      const i0 = Math.floor(pos);
      const i1 = Math.min(i0 + 1, channel.length - 1);
      const t = pos - i0;

      // Linear interpolation between adjacent samples.
      const sample = channel[i0] * (1 - t) + channel[i1] * t;

      // Clamp to [-1, 1] then convert to signed 16-bit integer.
      const clamped = Math.max(-1, Math.min(1, sample));
      this._buffer[this._writePos] =
        clamped < 0
          ? Math.round(clamped * 0x8000)
          : Math.round(clamped * 0x7fff);

      this._writePos++;

      // When the accumulation buffer is full, copy it out and transfer to main.
      if (this._writePos >= CHUNK_SAMPLES) {
        this._flush();
      }

      pos += stepSize;
    }

    // Carry the fractional remainder over to the next process() call.
    this._inputPhase = pos - channel.length;
    if (this._inputPhase < 0) this._inputPhase = 0;

    return true; // keep processor alive
  }

  /** Copy the accumulated samples into a new ArrayBuffer and transfer it. */
  private _flush(): void {
    // Allocate a fresh ArrayBuffer so we can transfer (zero-copy) ownership.
    const transferBuffer = new ArrayBuffer(CHUNK_SAMPLES * 2); // 2 bytes per Int16
    const view = new Int16Array(transferBuffer);
    view.set(this._buffer.subarray(0, this._writePos));

    this._writePos = 0;
    this._buffer.fill(0);

    // Transfer ownership to avoid a copy across the thread boundary.
    this.port.postMessage(transferBuffer, [transferBuffer]);
  }
}

registerProcessor('pcm-processor', PcmProcessor);
