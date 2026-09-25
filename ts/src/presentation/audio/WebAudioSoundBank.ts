import type { SoundBank, SoundName } from './SoundBank.js';
import { SOUND_RECIPES, type Recipe } from './soundRecipes.js';
import type { Synth } from './Synth.js';

/**
 * 同じ作り方の音を、これより短い間隔では重ねない（秒）。
 *
 * ルールの層はブロック1つ・アイテム1つごとにイベントを返すので、
 * 1回の爆発で同じ音が何本も同時に届く。そのまま重ねると音量が本数倍になり、
 * 割れる。原型は爆発1回につき1回だけ鳴らしていた。
 * 1回の描画で何 tick か進めたときも、音はどれも同じ瞬間に鳴るのでまとめてよい。
 */
const SAME_SOUND_GAP = 0.03;

/**
 * Web Audio で鳴らす SoundBank。
 *
 * 音を鳴らす仕組みは `Synth` が持つ。`Synth.unlock()` を呼ぶ前に `play()` が
 * 呼ばれても、何もせずに戻る。
 */
export class WebAudioSoundBank implements SoundBank {
  // 同じ関数を指す名前（1個置き・一列置き）も、まとめて1つと数える。
  readonly #lastPlayed = new Map<Recipe, number>();

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
    const recipe = SOUND_RECIPES[name];
    const now = this.synth.now;
    const last = this.#lastPlayed.get(recipe);
    if (last !== undefined && now - last < SAME_SOUND_GAP) return;
    this.#lastPlayed.set(recipe, now);
    recipe(this.synth, intensity);
  }
}
