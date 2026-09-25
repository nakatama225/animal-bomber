import { semitone, type Synth } from './Synth.js';

/** 等倍で遊ぶときの速さ（1分あたりの拍数）。 */
export const BASE_TEMPO = 138;

/** 速さを上げるのは2倍まで。上げ過ぎると耳障りになる。 */
const MAX_SPEEDUP = 2;

/** 1拍を4つに刻む（16分音符）。 */
const STEPS_PER_BEAT = 4;

/** 何秒先までの音を予約しておくか。 */
const LOOKAHEAD = 0.16;

/** 予約を足しに起きる間隔（ミリ秒）。先読みより十分短くしておく。 */
const WAKE_MS = 25;

/** 最初の刻みを置くまでの間。いまの時刻に置くと、予約が届くころにはもう過ぎている。 */
const LEAD_IN = 0.06;

/** 基準の音（A3）。 */
const ROOT_HZ = 220;

// イ短調。数は ROOT_HZ からの半音の数。4刻みごとに和音が変わる。
/** ベース。null の刻みは鳴らさない。1オクターブ下で鳴らす。 */
const BASS: readonly (number | null)[] = [
  0, null, 0, null, -5, null, -5, null, -3, null, -3, null, -7, null, -7, null,
];
/** 分散和音。偶数番目の刻みでだけ鳴らす（8分音符）。奇数番目は使わない（原型の表のまま）。 */
const ARP: readonly number[] = [12, 19, 16, 24, 12, 19, 16, 24, 9, 16, 12, 21, 7, 14, 11, 19];

/**
 * 8bit 風の曲。16 刻みを繰り返す。
 *
 * 刻みの時刻は音を鳴らす仕組みの時計で決める。タイマーは「そろそろ次を予約せよ」と
 * 起こすだけで、タイマーの遅れは音の遅れにならない。
 */
export class Music {
  #playing = false;
  #step = 0;
  #next = 0;
  #tempo = BASE_TEMPO;
  #timer: ReturnType<typeof setInterval> | null = null;

  constructor(private readonly synth: Synth) {}

  /** 鳴っているか。 */
  get playing(): boolean {
    return this.#playing;
  }

  /** いまの速さ（1分あたりの拍数）。 */
  get tempo(): number {
    return this.#tempo;
  }

  /** ゲームの速さの倍率に合わせる。体感と曲の速さがずれないように。 */
  setSpeed(multiplier: number): void {
    this.#tempo = Math.round(BASE_TEMPO * Math.min(MAX_SPEEDUP, multiplier));
  }

  /** 曲の入/切。切ると止める。入にしても鳴らし始めはしない。 */
  setEnabled(on: boolean): void {
    this.synth.setBusOn('bgm', on);
    if (!on) this.stop();
  }

  /**
   * 頭から鳴らす。`unlock()` の前・切っているとき・鳴っているときは何もしない。
   */
  start(): void {
    if (!this.synth.ready || !this.synth.isBusOn('bgm') || this.#playing) return;
    this.#playing = true;
    this.#step = 0;
    this.#next = this.synth.now + LEAD_IN;
    this.schedule();
    this.#timer = setInterval(() => this.schedule(), WAKE_MS);
  }

  /** 止める。予約済みの音は先読みの分だけ鳴り残る。 */
  stop(): void {
    this.#playing = false;
    if (this.#timer !== null) clearInterval(this.#timer);
    this.#timer = null;
  }

  /**
   * 先読みの範囲に入った刻みを予約する。ふだんはタイマーから呼ばれる。
   */
  schedule(): void {
    if (!this.#playing || !this.synth.ready) return;
    const now = this.synth.now;
    const dt = 60 / this.#tempo / STEPS_PER_BEAT;
    // タブを裏に回すとタイマーが間引かれ、戻ったときに過ぎた刻みが一度に鳴る。
    // 過ぎた分は捨て、刻みの位置だけ進めて拍を保つ。
    if (this.#next < now) {
      const missed = Math.ceil((now - this.#next) / dt);
      this.#step = (this.#step + missed) % BASS.length;
      this.#next += missed * dt;
    }
    while (this.#next < now + LOOKAHEAD) {
      this.#playStep(this.#step, this.#next - now);
      this.#step = (this.#step + 1) % BASS.length;
      this.#next += dt;
    }
  }

  #playStep(step: number, delay: number): void {
    const bass = BASS[step];
    if (typeof bass === 'number') this.#note(ROOT_HZ / 2, bass, delay, 0.14, 0.5);
    const arp = ARP[step];
    if (step % 2 === 0 && arp !== undefined) this.#note(ROOT_HZ, arp, delay, 0.09, 0.16);
    if (step % 4 === 2) {
      // ハイハット。削る境目は動かさない。
      this.synth.noiseBurst({
        dur: 0.05,
        f0: 7000,
        f1: 7000,
        vol: 0.12,
        type: 'highpass',
        delay,
        bus: 'bgm',
      });
    }
  }

  #note(base: number, semitones: number, delay: number, dur: number, vol: number): void {
    // 原型では曲の音を効果音と別の関数で鳴らしていて、違いは立ち上がりの
    // 長さだけだった。同じ部品を使い、立ち上がりだけ原型の曲の値にする。
    this.synth.tone({
      f0: semitone(base, semitones),
      type: 'square',
      dur,
      vol,
      delay,
      attack: 0.008,
      bus: 'bgm',
    });
  }
}
