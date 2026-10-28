import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { test } from 'node:test';
import assert from 'node:assert/strict';

const source = readFileSync(new URL('../public/worklets/pcm-processor.js', import.meta.url), 'utf8');

function capture(rate, frequency) {
  const chunks = [];
  let Processor;
  runInNewContext(source, {
    sampleRate: rate,
    AudioWorkletProcessor: class {
      port = { postMessage: buffer => chunks.push(new Int16Array(buffer)) };
    },
    registerProcessor: (_, implementation) => { Processor = implementation; },
  });
  const processor = new Processor();
  for (let start = 0; start < rate; start += 128) {
    const block = Float32Array.from({ length: Math.min(128, rate - start) },
      (_, i) => 0.5 * Math.sin(2 * Math.PI * frequency * (start + i) / rate));
    processor.process([[block]]);
  }
  const samples = chunks.flatMap(chunk => Array.from(chunk));
  const stable = samples.slice(1600);
  const rms = Math.sqrt(stable.reduce((sum, value) => sum + (value / 32768) ** 2, 0) / stable.length);
  return { samples, chunks, rms };
}

for (const rate of [16000, 44100, 48000]) {
  test(`${rate} Hz emits one second of mono PCM in 100 ms chunks`, () => {
    const result = capture(rate, 1000);
    assert.equal(result.samples.length, 16000);
    assert.ok(result.chunks.every(chunk => chunk.length === 1600));
    assert.ok(result.rms > 0.33 && result.rms < 0.37, `speech band RMS: ${result.rms}`);
  });
}

for (const rate of [44100, 48000]) {
  test(`${rate} Hz rejects high frequencies before downsampling`, () => {
    const result = capture(rate, 12000);
    assert.ok(result.rms < 0.005, `aliased RMS: ${result.rms}`);
  });
}
