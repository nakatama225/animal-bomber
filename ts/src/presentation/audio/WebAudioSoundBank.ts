import type { SoundBank, SoundName } from './SoundBank.js';
import { SOUND_RECIPES } from './soundRecipes.js';
import type { Synth } from './Synth.js';

/**
 * Web Audio で鳴らす SoundBank。
 *
 * 音を鳴らす仕組みは `Synth` が持つ。`Synth.unlock()` を呼ぶ前に `play()` が
 * 呼ばれても、何もせずに戻る。
 *
 * 同じ音を一定時間まとめて1回にする仕組みは持たない（原型の `SE` も、呼ぶたびに予約してまとめない）。
 * 原型が1回しか鳴らさない場面（1回の爆発で壊したブロック・一列に並べた爆弾など）は、鳴らす側の
 * `Presenter` が場面を見分けて1回にする。
 */
export class WebAudioSoundBank implements SoundBank {
  constructor(private readonly synth: Synth) {}

  /** 効果音が入になっているか。 */
  get enabled(): boolean {
    return this.synth.isBusOn('sfx');
  }

  /** 効果音の入/切。`unlock()` の前に変えても、呼んだときに反映される。 */
  setEnabled(on: boolean): void {
    this.synth.setBusOn('sfx', on);
  }

  /**
   * @param intensity 爆発の連鎖数。ほかの音では使わない
   */
  play(name: SoundName, intensity = 1): void {
    // 切っているあいだは部品も作らない。音量 0 で鳴らしても聞こえないだけで、
    // 部品は作られ続ける。
    if (!this.synth.ready || !this.enabled) return;
    SOUND_RECIPES[name](this.synth, intensity);
  }
}
