// Runtime AudioWorklet loaded directly by useAudioCapture.ts.
const TARGET_SAMPLE_RATE = 16000;
const CHUNK_DURATION_S = 0.1;
const CHUNK_SAMPLES = Math.round(TARGET_SAMPLE_RATE * CHUNK_DURATION_S);
class PcmProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = new Int16Array(CHUNK_SAMPLES);
    this.writePos = 0;
    this.inputPhase = 0;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;

    const channel = input[0];
    if (!channel || channel.length === 0) return true;

    const stepSize = sampleRate / TARGET_SAMPLE_RATE;
    let pos = this.inputPhase;

    while (pos < channel.length) {
      const i0 = Math.floor(pos);
      const i1 = Math.min(i0 + 1, channel.length - 1);
      const t = pos - i0;
      const sample = channel[i0] * (1 - t) + channel[i1] * t;
      const clamped = Math.max(-1, Math.min(1, sample));

      this.buffer[this.writePos] =
        clamped < 0
          ? Math.round(clamped * 0x8000)
          : Math.round(clamped * 0x7fff);
      this.writePos += 1;

      if (this.writePos >= CHUNK_SAMPLES) {
        this.flush();
      }

      pos += stepSize;
    }

    this.inputPhase = pos - channel.length;
    if (this.inputPhase < 0) this.inputPhase = 0;

    return true;
  }

  flush() {
    const transferBuffer = new ArrayBuffer(this.writePos * 2);
    const view = new DataView(transferBuffer);

    for (let i = 0; i < this.writePos; i += 1) {
      view.setInt16(i * 2, this.buffer[i], true);
    }

    this.writePos = 0;
    this.buffer.fill(0);

    this.port.postMessage(transferBuffer, [transferBuffer]);
  }
}

registerProcessor('pcm-processor', PcmProcessor);
