import { CosmeticRng } from '../CosmeticRng.js';
import type {
  GainNodeLike,
  AudioBufferLike,
  AudioContextLike,
} from './webAudioTypes.js';

/** `base` から半音 `steps` 個ぶん上げた周波数。 */
export function semitone(base: number, steps: number): number {
  return base * 2 ** (steps / 12);
}

/** 音を流す系統。効果音と曲で音量を分けて持つ。 */
export type Bus = 'sfx' | 'bgm';

/** 系統ごとの音量。原型の値をそのまま使う。 */
export const BUS_LEVEL: Readonly<Record<Bus, number>> = { sfx: 0.55, bgm: 0.15 };

/**
 * 波形の種類。
 *
 * DOM の `OscillatorType` には 'custom' も含まれるが、それを直接代入すると
 * ブラウザが例外を投げるので、ここでは選べないようにしておく。
 */
export type Wave = 'sine' | 'square' | 'sawtooth' | 'triangle';

/** ノイズの削り方。 */
export type FilterKind = 'lowpass' | 'highpass' | 'bandpass';

/** 波形の音1つ。省いた値は原型の既定値になる。 */
export interface ToneOptions {
  /** 鳴り始めの周波数（Hz）。 */
  readonly f0?: number;
  /** 鳴り終わりの周波数。省くと変えない。 */
  readonly f1?: number;
  readonly type?: Wave;
  /** 長さ（秒）。 */
  readonly dur?: number;
  readonly vol?: number;
  /** いまから何秒後に鳴らすか。 */
  readonly delay?: number;
  /** 立ち上がりの長さ（秒）。省くと長さの 2 割（最大 0.02 秒）。 */
  readonly attack?: number;
  readonly bus?: Bus;
}

/** 削ったノイズ1つ。省いた値は原型の既定値になる。 */
export interface NoiseOptions {
  readonly dur?: number;
  /** 削る境目の、鳴り始めの周波数。 */
  readonly f0?: number;
  /** 削る境目の、鳴り終わりの周波数。 */
  readonly f1?: number;
  readonly vol?: number;
  readonly type?: FilterKind;
  readonly q?: number;
  readonly delay?: number;
  readonly bus?: Bus;
}

/** 音の作り方の表が使う2つの部品。 */
export interface Voice {
  readonly tone: (options: ToneOptions) => void;
  readonly noiseBurst: (options: NoiseOptions) => void;
}

// 指数で変化させる先に 0 以下を渡すとブラウザが例外を投げる。
// 無音の代わりに、聞こえないほど小さい値で止める。
const SILENT = 0.0001;
const FADED = 0.0008;
const MIN_TONE_HZ = 20;
const MIN_FILTER_HZ = 40;
/** 音量が下がりきってから止めるまでの余り。ぴったりで止めるとプツッと鳴る。 */
const TAIL = 0.02;

/**
 * Web Audio で音を合成する部品。
 *
 * 音を鳴らす仕組み（AudioContext）は `unlock()` で初めて作る。ブラウザは
 * 利用者が画面を触る前に音を出すことを禁じていて、触る前に作ったものは
 * 止まったまま鳴らない。`unlock()` の前に鳴らそうとしても何も起きない。
 */
export class Synth implements Voice {
  #ctx: AudioContextLike | null = null;
  #buses: Record<Bus, GainNodeLike> | null = null;
  #noise: AudioBufferLike | null = null;
  // `unlock()` の前に入/切を変えられても、呼んだときに反映する。
  readonly #on: Record<Bus, boolean> = { sfx: true, bgm: true };

  /**
   * @param createContext 音を鳴らす仕組みを作る。省くとブラウザの `AudioContext`
   * @param cosmetic ノイズの波形を作る乱数
   */
  constructor(
    private readonly createContext: () => AudioContextLike | null = browserAudioContext,
    private readonly cosmetic: CosmeticRng = new CosmeticRng(),
  ) {}

  /** 音を出せる状態か。 */
  get ready(): boolean {
    return this.#ctx !== null;
  }

  /** 音を鳴らす仕組みの時計（秒）。曲の刻みはこれに合わせて予約する。 */
  get now(): number {
    return this.#ctx?.currentTime ?? 0;
  }

  /**
   * 音を出せるようにする。画面の操作（クリック・キー・パッド）の中から呼ぶ。
   *
   * 何度呼んでもよい。2回目からは、止まっている仕組みを動かし直すだけになる。
   * 止まった仕組みは画面の操作の中でしか動かし直せないので、原型と同じく
   * 操作のたびに呼ぶ。
   */
  unlock(): void {
    if (this.#ctx === null) this.#open();
    const ctx = this.#ctx;
    if (ctx !== null && ctx.state === 'suspended') {
      // 動かし直せなくても遊べるので、失敗は無音のまま捨てる。
      ctx.resume().catch(() => undefined);
    }
  }

  /** 系統ごとの入/切。 */
  setBusOn(bus: Bus, on: boolean): void {
    this.#on[bus] = on;
    const node = this.#buses?.[bus];
    if (node !== undefined) node.gain.value = on ? BUS_LEVEL[bus] : 0;
  }

  /** その系統が入になっているか。 */
  isBusOn(bus: Bus): boolean {
    return this.#on[bus];
  }

  /** 波形の音を1つ予約する。音量は立ち上がったあと指数で消えていく。 */
  tone(options: ToneOptions): void {
    const ctx = this.#ctx;
    const out = this.#buses?.[options.bus ?? 'sfx'];
    if (ctx === null || out === undefined) return;
    const { f0 = 440, f1, type = 'square', dur = 0.12, vol = 0.22, delay = 0 } = options;
    const t = ctx.currentTime + delay;
    const attack = options.attack ?? Math.min(0.02, dur * 0.2);

    const osc = ctx.createOscillator();
    osc.type = type;
    osc.frequency.setValueAtTime(f0, t);
    if (f1 !== undefined) {
      osc.frequency.exponentialRampToValueAtTime(Math.max(MIN_TONE_HZ, f1), t + dur);
    }
    const gain = ctx.createGain();
    gain.gain.setValueAtTime(SILENT, t);
    gain.gain.exponentialRampToValueAtTime(Math.max(SILENT, vol), t + attack);
    gain.gain.exponentialRampToValueAtTime(FADED, t + dur);
    osc.connect(gain);
    gain.connect(out);
    osc.start(t);
    osc.stop(t + dur + TAIL);
  }

  /** 削ったノイズを1つ予約する。削る境目と音量が同時に動く。 */
  noiseBurst(options: NoiseOptions): void {
    const ctx = this.#ctx;
    const out = this.#buses?.[options.bus ?? 'sfx'];
    if (ctx === null || out === undefined) return;
    const { dur = 0.4, f0 = 1800, f1 = 120, vol = 0.8, type = 'lowpass', q = 1 } = options;
    const t = ctx.currentTime + (options.delay ?? 0);

    // 1 秒のノイズを繰り返し流す。長い音でも同じ波形で足りる。
    const source = ctx.createBufferSource();
    source.buffer = this.#noise;
    source.loop = true;
    const filter = ctx.createBiquadFilter();
    filter.type = type;
    filter.Q.value = q;
    filter.frequency.setValueAtTime(f0, t);
    filter.frequency.exponentialRampToValueAtTime(Math.max(MIN_FILTER_HZ, f1), t + dur);
    const gain = ctx.createGain();
    gain.gain.setValueAtTime(Math.max(SILENT, vol), t);
    gain.gain.exponentialRampToValueAtTime(FADED, t + dur);
    source.connect(filter);
    filter.connect(gain);
    gain.connect(out);
    source.start(t);
    source.stop(t + dur + TAIL);
  }

  #open(): void {
    const ctx = this.createContext();
    if (ctx === null) return;
    const bus = (name: Bus): GainNodeLike => {
      const node = ctx.createGain();
      node.gain.value = this.#on[name] ? BUS_LEVEL[name] : 0;
      node.connect(ctx.destination);
      return node;
    };
    this.#buses = { sfx: bus('sfx'), bgm: bus('bgm') };

    const noise = ctx.createBuffer(1, ctx.sampleRate, ctx.sampleRate);
    const data = noise.getChannelData(0);
    for (let i = 0; i < data.length; i += 1) data[i] = this.cosmetic.between(-1, 1);
    this.#noise = noise;
    this.#ctx = ctx;
  }
}

/** ブラウザの音を鳴らす仕組み。使えない環境（テストの node など）では null。 */
function browserAudioContext(): AudioContextLike | null {
  if (typeof AudioContext === 'undefined') return null;
  try {
    return new AudioContext();
  } catch {
    // 同時に作れる数の上限などで作れないことがある。音なしで遊べるようにする。
    return null;
  }
}
