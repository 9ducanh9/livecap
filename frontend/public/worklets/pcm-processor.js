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
    // Low-pass before decimation so high frequencies cannot alias into speech.
    this.filter = null;
    if (sampleRate > TARGET_SAMPLE_RATE) {
      const taps = 63;
      const cutoff = TARGET_SAMPLE_RATE * 0.45 / sampleRate;
      this.filter = new Float64Array(taps);
      this.history = new Float32Array(taps);
      this.historyPos = 0;
      let sum = 0;
      for (let i = 0; i < taps; i += 1) {
        const offset = i - (taps - 1) / 2;
        const sinc = offset === 0 ? 2 * cutoff
          : Math.sin(2 * Math.PI * cutoff * offset) / (Math.PI * offset);
        this.filter[i] = sinc * (0.54 - 0.46 * Math.cos(2 * Math.PI * i / (taps - 1)));
        sum += this.filter[i];
      }
      for (let i = 0; i < taps; i += 1) this.filter[i] /= sum;
    }
    this.filteredBlock = new Float32Array(128);
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;

    let channel = input[0];
    if (!channel || channel.length === 0) return true;

    if (this.filter) {
      if (this.filteredBlock.length !== channel.length) {
        this.filteredBlock = new Float32Array(channel.length);
      }
      for (let i = 0; i < channel.length; i += 1) {
        this.history[this.historyPos] = channel[i];
        let value = 0;
        for (let tap = 0; tap < this.filter.length; tap += 1) {
          const index = (this.historyPos - tap + this.filter.length) % this.filter.length;
          value += this.filter[tap] * this.history[index];
        }
        this.filteredBlock[i] = value;
        this.historyPos = (this.historyPos + 1) % this.filter.length;
      }
      channel = this.filteredBlock;
    }

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
