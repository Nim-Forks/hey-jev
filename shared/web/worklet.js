// resamples the browser input (typically 44.1/48 kHz mono f32) to 16 kHz
class Resample16k extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / 16000;
    this.carry = new Float32Array(0);
    this.chunk = 1600; // 100 ms at 16 kHz
  }

  process(inputs) {
    const input = inputs[0][0];
    if (!input) return true;
    const merged = new Float32Array(this.carry.length + input.length);
    merged.set(this.carry);
    merged.set(input, this.carry.length);

    const outFrames = Math.floor(merged.length / this.ratio);
    if (outFrames >= this.chunk) {
      const out = new Float32Array(outFrames);
      for (let i = 0; i < outFrames; i++) {
        const pos = i * this.ratio;
        const i0 = Math.floor(pos), frac = pos - i0;
        const a = merged[i0], b = merged[Math.min(i0 + 1, merged.length - 1)];
        out[i] = a + (b - a) * frac;
      }
      this.port.postMessage(out.buffer, [out.buffer]);
      this.carry = merged.slice(outFrames * this.ratio);
    } else {
      this.carry = merged;
    }
    return true;
  }
}
registerProcessor("resample16k", Resample16k);
