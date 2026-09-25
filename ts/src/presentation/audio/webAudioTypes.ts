/*
 * Synth が使う Web Audio の機能だけを書き出した型。
 *
 * ブラウザの `AudioContext` はそのままこの型に当てはまる。テストでは
 * ここに書いたものだけを手書きした偽物を差す。DOM の型をそのまま使うと、
 * 偽物が使いもしない何十ものメンバーを揃えることになる。
 */

/** 時刻を指定して値を変えられる音の設定値（周波数・音量など）。 */
export interface AudioParamLike {
  value: number;
  setValueAtTime(value: number, time: number): unknown;
  exponentialRampToValueAtTime(value: number, time: number): unknown;
}

/** 音の通り道の1段。 */
export interface AudioNodeLike {
  connect(destination: AudioNodeLike): unknown;
}

/** 音量を変える段。 */
export interface GainNodeLike extends AudioNodeLike {
  readonly gain: AudioParamLike;
}

/** 決まった時刻に鳴り始めて止まる音源。 */
export interface ScheduledSourceLike extends AudioNodeLike {
  start(when: number): void;
  stop(when: number): void;
}

/** 波形を出す音源。 */
export interface OscillatorNodeLike extends ScheduledSourceLike {
  type: OscillatorType;
  readonly frequency: AudioParamLike;
}

/** 録音済みの波形を流す音源。ノイズに使う。 */
export interface BufferSourceNodeLike extends ScheduledSourceLike {
  buffer: AudioBufferLike | null;
  loop: boolean;
}

/** 周波数で削る段。 */
export interface BiquadFilterNodeLike extends AudioNodeLike {
  type: BiquadFilterType;
  readonly frequency: AudioParamLike;
  readonly Q: AudioParamLike;
}

/** 波形の入れ物。 */
export interface AudioBufferLike {
  getChannelData(channel: number): Float32Array;
}

/** 音を鳴らす仕組み（AudioContext）。上に並べた部品を作る。 */
export interface AudioContextLike {
  readonly currentTime: number;
  readonly sampleRate: number;
  readonly state: string;
  readonly destination: AudioNodeLike;
  resume(): Promise<void>;
  createGain(): GainNodeLike;
  createOscillator(): OscillatorNodeLike;
  createBufferSource(): BufferSourceNodeLike;
  createBiquadFilter(): BiquadFilterNodeLike;
  createBuffer(channels: number, length: number, sampleRate: number): AudioBufferLike;
}
