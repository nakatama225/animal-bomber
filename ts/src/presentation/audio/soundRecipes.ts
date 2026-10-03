import type { SoundName } from './SoundBank.js';
import { semitone, type Voice } from './Synth.js';

/**
 * 音1つの作り方。
 *
 * @param intensity 大きさの手がかり。いまは爆発の連鎖数にだけ使う
 */
export type Recipe = (voice: Voice, intensity: number) => void;


/** 音の列を、`gap` 秒ずつずらして鳴らす。 */
function arpeggio(
  voice: Voice,
  base: number,
  steps: readonly number[],
  gap: number,
  tone: { readonly type: 'square' | 'triangle'; readonly dur: number; readonly vol: number },
): void {
  steps.forEach((s, i) => voice.tone({ ...tone, f0: semitone(base, s), delay: i * gap }));
}

const place: Recipe = (v) => {
  v.tone({ f0: 300, f1: 110, type: 'square', dur: 0.09, vol: 0.16 });
  v.tone({ f0: 900, f1: 600, type: 'triangle', dur: 0.05, vol: 0.1 });
};

/**
 * SoundName ごとの作り方。原型の効果音の表から、数値をそのまま写している。
 *
 * `Record` にしてあるので、SoundName を足して作り方を書き忘れると型検査が失敗する。
 */
export const SOUND_RECIPES: Readonly<Record<SoundName, Recipe>> = {
  place,

  explode(v, chained) {
    v.noiseBurst({ dur: 0.5, f0: 2200, f1: 90, vol: 0.75 });
    v.tone({ f0: 110, f1: 32, type: 'sine', dur: 0.42, vol: 0.5 });
    // 連鎖したときだけ、少し遅れてもう1つ重ねる。
    if (chained > 1) v.noiseBurst({ dur: 0.35, f0: 1200, f1: 120, vol: 0.4, delay: 0.05 });
  },

  breakBlock(v) {
    v.noiseBurst({ dur: 0.16, f0: 2600, f1: 700, vol: 0.3, type: 'bandpass', q: 1.2 });
  },

  item(v) {
    // 短三度ずつ上がる3音。
    arpeggio(v, 520, [0, 3, 6], 0.055, { type: 'square', dur: 0.08, vol: 0.16 });
  },

  chicken(v) {
    arpeggio(v, 440, [0, 5, 9, 12], 0.07, { type: 'triangle', dur: 0.16, vol: 0.2 });
  },

  burn(v) {
    // 原型には無い音。アイテムが焼けるのは爆発と同じ瞬間なので、
    // 爆発の音の陰でかすかに聞こえる程度の、短く高いジュッという音にする。
    v.noiseBurst({ dur: 0.1, f0: 4200, f1: 1800, vol: 0.07, type: 'bandpass', q: 0.9 });
  },

  hurt(v) {
    v.tone({ f0: 520, f1: 90, type: 'sawtooth', dur: 0.3, vol: 0.3 });
    v.noiseBurst({ dur: 0.2, f0: 900, f1: 200, vol: 0.25 });
  },

  down(v) {
    // 長三度ずつ下がる4音と、長めの崩れる音。
    arpeggio(v, 440, [0, -4, -8, -12], 0.1, { type: 'square', dur: 0.16, vol: 0.22 });
    v.noiseBurst({ dur: 0.6, f0: 700, f1: 60, vol: 0.35, delay: 0.1 });
  },

  slip(v) {
    v.tone({ f0: 1100, f1: 220, type: 'sine', dur: 0.42, vol: 0.22 });
    v.noiseBurst({ dur: 0.3, f0: 3000, f1: 800, vol: 0.14, type: 'bandpass', q: 2 });
  },

  cry(v) {
    for (let i = 0; i < 3; i += 1) {
      v.tone({
        f0: 660 - i * 90,
        f1: 520 - i * 90,
        type: 'sawtooth',
        dur: 0.22,
        vol: 0.16,
        delay: i * 0.16,
      });
    }
  },

  poop(v) {
    v.tone({ f0: 220, f1: 55, type: 'sawtooth', dur: 0.45, vol: 0.24 });
    v.noiseBurst({ dur: 0.35, f0: 500, f1: 90, vol: 0.22, type: 'lowpass' });
  },

  roundEnd(v) {
    arpeggio(v, 523.25, [0, 4, 7, 12, 16, 19], 0.11, { type: 'triangle', dur: 0.3, vol: 0.2 });
  },

  draw(v) {
    arpeggio(v, 392, [0, -2, -4], 0.16, { type: 'square', dur: 0.35, vol: 0.18 });
  },

  leek(v) {
    // 葱を撃った音。高い音が落ちていくのに、風を切るノイズを重ねる。
    v.tone({ f0: 1500, f1: 640, type: 'triangle', dur: 0.15, vol: 0.2 });
    v.noiseBurst({ dur: 0.1, f0: 4000, f1: 1200, vol: 0.1, type: 'highpass' });
  },

  leekBlock(v) {
    // 葱が爆弾に弾かれた音。
    v.tone({ f0: 180, f1: 90, type: 'square', dur: 0.1, vol: 0.22 });
    v.noiseBurst({ dur: 0.09, f0: 1600, f1: 500, vol: 0.16, type: 'bandpass', q: 3 });
  },

  leekHit(v) {
    // 葱が当たって入れ替わった音。駆け上がる音に、弾けるノイズを重ねる。
    arpeggio(v, 523, [0, 4, 7, 12, 16], 0.06, { type: 'square', dur: 0.16, vol: 0.2 });
    v.noiseBurst({ dur: 0.25, f0: 2200, f1: 400, vol: 0.2 });
  },

  lanesClosed(v) {
    arpeggio(v, 392, [0, -3, -7], 0.12, { type: 'square', dur: 0.2, vol: 0.16 });
  },

  sudden(v) {
    // 高低2音の警報を4回。下に長い地鳴りを重ねる。
    for (let i = 0; i < 4; i += 1) {
      v.tone({ f0: i % 2 === 1 ? 880 : 660, type: 'square', dur: 0.14, vol: 0.24, delay: i * 0.17 });
    }
    v.tone({ f0: 80, f1: 40, type: 'sine', dur: 0.9, vol: 0.35, delay: 0.1 });
  },

  tick(v) {
    // 残り10秒からの秒読み。短く高い音にして、ほかの音に埋もれないようにする。
    v.tone({ f0: 1200, type: 'square', dur: 0.05, vol: 0.14 });
  },

  fanfare(v) {
    // 優勝ファンファーレ。[半音, 鳴らす時刻] の組を、1オクターブ下と重ねて鳴らす。
    const notes: readonly (readonly [number, number])[] = [
      [0, 0], [0, 0.12], [0, 0.24], [4, 0.36], [7, 0.48],
      [12, 0.6], [7, 0.86], [12, 0.98], [16, 1.1], [19, 1.24],
    ];
    for (const [s, delay] of notes) {
      v.tone({ f0: semitone(523.25, s), type: 'square', dur: 0.26, vol: 0.2, delay });
      v.tone({ f0: semitone(261.6, s), type: 'triangle', dur: 0.26, vol: 0.14, delay });
    }
    // 最後の音に合わせて、シャーンと高い音を足す。
    v.noiseBurst({ dur: 0.5, f0: 6000, f1: 1200, vol: 0.14, type: 'highpass', delay: 1.24 });
  },

  hop(v) {
    v.tone({ f0: 400, f1: 820, type: 'triangle', dur: 0.13, vol: 0.2 });
  },

  // 原型でも、一列に置いたときは1個置くときと同じ音を1回だけ鳴らしていた。
  // 置いた数だけ届く bombPlaced と重ならないよう、同じ関数を指しておく
  // （WebAudioSoundBank は同じ作り方の音を同時に重ねない）。
  lineBombs: place,

  tongue(v) {
    v.tone({ f0: 700, f1: 1300, type: 'sine', dur: 0.13, vol: 0.16 });
  },

  special(v) {
    arpeggio(v, 392, [0, 3, 7, 10, 12], 0.05, { type: 'square', dur: 0.11, vol: 0.17 });
  },

  scatter(v) {
    // 原型の「うんこが爆風で吹き飛んだ」音。撒く技には専用の音が無く、
    // 悪い状態にかかったときの音（poop）とは分けておきたいので、これを当てる。
    v.noiseBurst({ dur: 0.22, f0: 700, f1: 160, vol: 0.2 });
    v.tone({ f0: 300, f1: 520, type: 'sine', dur: 0.18, vol: 0.14 });
  },

  charge(v) {
    v.noiseBurst({ dur: 0.45, f0: 700, f1: 180, vol: 0.26, type: 'lowpass' });
    v.tone({ f0: 130, f1: 220, type: 'sawtooth', dur: 0.4, vol: 0.22 });
    v.tone({ f0: 900, f1: 400, type: 'square', dur: 0.1, vol: 0.1 });
  },

  dig(v) {
    // 掘っているあいだ、ザクザクと5回鳴らす。間隔は、掘り終わるまでの
    // 長さ（原型で 1.5 秒）の少し手前で鳴りやむように決めてある。
    for (let i = 0; i < 5; i += 1) {
      const delay = i * 0.28;
      v.noiseBurst({ dur: 0.16, f0: 1500, f1: 300, vol: 0.15, type: 'bandpass', q: 1.5, delay });
      v.tone({ f0: 170, f1: 90, type: 'triangle', dur: 0.12, vol: 0.1, delay });
    }
  },

  foxfire(v) {
    // 妖しく揺れる炎。ずらして重ねた3つの音が、それぞれ4度上へすべり上がる。
    [0, 7, 12].forEach((s, i) =>
      v.tone({
        f0: semitone(330, s),
        f1: semitone(330, s + 5),
        type: 'sine',
        dur: 0.5,
        vol: 0.15,
        delay: i * 0.06,
      }),
    );
    v.noiseBurst({ dur: 0.6, f0: 2600, f1: 700, vol: 0.12, type: 'bandpass', q: 2 });
  },

  slime(v) {
    v.tone({ f0: 200, f1: 520, type: 'sine', dur: 0.22, vol: 0.2 });
    v.noiseBurst({ dur: 0.14, f0: 900, f1: 2200, vol: 0.1, type: 'bandpass', q: 1.4 });
  },
};
