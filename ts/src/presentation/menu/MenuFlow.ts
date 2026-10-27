import { CPU_LEVEL_KEYS, type CpuLevelKey } from '../../ai/CpuLevel.js';
import { ANIMAL_LOOKS } from '../../content/animals.js';
import { assertChoice, HIT_CHOICES, TIME_CHOICES, WIN_CHOICES } from './choices.js';
import { DEFAULT_SETUP, MODE_SIZES, type LocalSetup, type PlayMode } from './localSetup.js';

/**
 * 試合の前の画面。
 *
 * | 画面 | 中身 | もどる先 |
 * |---|---|---|
 * | `title` | 遊び方を選ぶ | — |
 * | `pick` | 人間ごとに動物を選ぶ | `title` |
 * | `rules` | 体力・CPU の強さ・勝ち数・制限時間・延長戦 | `pick` |
 * | `manual` | 音の設定・マニュアル・更新履歴 | `title` |
 */
export type MenuScreen = 'title' | 'pick' | 'rules' | 'manual';

/** 1つ前の画面。 */
const BACK: Readonly<Record<Exclude<MenuScreen, 'title'>, MenuScreen>> = {
  pick: 'title',
  rules: 'pick',
  manual: 'title',
};

/** 音の設定。 */
export type SoundSetting = 'both' | 'sfx' | 'off';

/**
 * 試合の前の画面の流れと、そこで選んだもの。
 *
 * **画面に何も書かない。** どの画面にいて何を選んだかだけを持つ。画面を組み立てるのは
 * `platform/ui/MenuView.ts` で、そちらはこのクラスの値を写して、押されたらここを呼ぶ。
 * 分けてあるので、画面の流れはブラウザ無しで確認できる。
 *
 * 選べない値（表に無い勝ち数など）を渡されたら例外にする（`assertChoice`）。
 * 黙って既定値に戻すと気づけない。
 */
export class MenuFlow {
  #screen: MenuScreen = 'title';
  #setup: LocalSetup;
  #sound: SoundSetting;

  /** @param sound 前に選んだ音の設定。起動の入口が、ブラウザに残した値を読んで渡す */
  constructor(setup: LocalSetup = DEFAULT_SETUP, sound: SoundSetting = 'both') {
    this.#setup = setup;
    this.#sound = sound;
  }

  get screen(): MenuScreen {
    return this.#screen;
  }

  get setup(): LocalSetup {
    return this.#setup;
  }

  get sound(): SoundSetting {
    return this.#sound;
  }

  /** いまの遊び方の人数。 */
  get sizes(): { readonly humans: number; readonly cpus: number } {
    return MODE_SIZES[this.#setup.mode];
  }

  /** 遊び方を選んで、動物を選ぶ画面へ進む。 */
  chooseMode(mode: PlayMode): void {
    this.#setup = { ...this.#setup, mode };
    this.#screen = 'pick';
  }

  openManual(): void {
    this.#screen = 'manual';
  }

  /** 1つ前の画面へもどる。タイトルでは何もしない。 */
  back(): void {
    if (this.#screen !== 'title') this.#screen = BACK[this.#screen];
  }

  /** 動物を選ぶ画面から、ルールを決める画面へ進む。 */
  next(): void {
    if (this.#screen === 'pick') this.#screen = 'rules';
  }

  /** 人間の動物を選ぶ。 */
  pick(human: 0 | 1, animal: string): void {
    if (!ANIMAL_LOOKS.some((look) => look.key === animal)) throw new Error(`知らない動物: ${animal}`);
    if (human >= this.sizes.humans) throw new Error(`この遊び方に ${human + 1}P はいない`);
    const picks: [string, string] = [...this.#setup.picks];
    picks[human] = animal;
    this.#setup = { ...this.#setup, picks };
  }

  /** 爆風何回で倒れるか。 */
  setHits(who: 'p1' | 'p2' | 'cpu', hits: number): void {
    assertChoice(HIT_CHOICES, hits, '爆風の回数');
    this.#setup = { ...this.#setup, hits: { ...this.#setup.hits, [who]: hits } };
  }

  /** CPU の強さ。`index` は CPU の何体目か（0 から）。 */
  setCpuLevel(index: 0 | 1 | 2, level: CpuLevelKey): void {
    assertChoice(CPU_LEVEL_KEYS, level, 'CPU の強さ');
    if (index >= this.sizes.cpus) throw new Error(`この遊び方に CPU${index + 1} はいない`);
    const cpuLevels: [CpuLevelKey, CpuLevelKey, CpuLevelKey] = [...this.#setup.cpuLevels];
    cpuLevels[index] = level;
    this.#setup = { ...this.#setup, cpuLevels };
  }

  setWinsToTake(wins: number): void {
    assertChoice(WIN_CHOICES, wins, '勝ち数');
    this.#setup = { ...this.#setup, winsToTake: wins };
  }

  setRoundSeconds(seconds: number): void {
    assertChoice(TIME_CHOICES, seconds, '制限時間');
    this.#setup = { ...this.#setup, roundSeconds: seconds };
  }

  setSuddenDeath(on: boolean): void {
    this.#setup = { ...this.#setup, suddenDeath: on };
  }

  setSound(sound: SoundSetting): void {
    this.#sound = sound;
  }

  /** 試合から戻ってきたとき。選んだものは残し、タイトルから始める。 */
  returnToTitle(): void {
    this.#screen = 'title';
  }
}
