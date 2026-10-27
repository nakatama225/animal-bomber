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
 * | `lan` | 「たてる」「さんかする」（通信対戦の中継につなぐ） | `title`（つないでいる最中は、切るかの確認を出す） |
 *
 * 通信対戦のロビーと試合の画面は、ここには含めない。どちらも中継との接続（`app/LanMatch.ts`）が持ち、
 * `app/Shell.ts` が接続の段階を見て出し分ける。
 */
export type MenuScreen = 'title' | 'pick' | 'rules' | 'manual' | 'lan';

/** 1つ前の画面（原型の `MENU_BACK`。L3181）。 */
const BACK: Readonly<Record<Exclude<MenuScreen, 'title'>, MenuScreen>> = {
  pick: 'title',
  rules: 'pick',
  manual: 'title',
  lan: 'title',
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
  #connecting = false;
  #failure = '';

  /**
   * @param sound 起動したときの音の設定。原型と同じく起動の間だけ持ち、ブラウザには残さない（通信対戦へ移るときも
   *   抜けるときもページを開き直さないので、残さなくても選んだものは消えない）
   */
  constructor(setup: LocalSetup = DEFAULT_SETUP, sound: SoundSetting = 'both') {
    this.#setup = setup;
    this.#sound = sound;
  }

  get screen(): MenuScreen {
    return this.#screen;
  }

  /**
   * 中継との接続を持っているか（LAN の画面で「たてる」か「さんかする」を押してから、タイトルへ戻るか、つなげなかったと
   * 分かるまで）。LAN の画面は、この間「たてる」「さんかする」を出さずに「接続しています…」を出す。
   */
  get connecting(): boolean {
    return this.#connecting;
  }

  /** LAN の画面の「接続しています…」の行に出す、つなげなかった理由。無ければ空。 */
  get failure(): string {
    return this.#failure;
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
    this.#show('pick');
  }

  openManual(): void {
    this.#show('manual');
  }

  /** LAN の画面へ移る（タイトルの「LAN対戦」。原型 L5721）。 */
  openLan(): void {
    this.#show('lan');
  }

  /**
   * 中継につなぎ始めた（LAN の画面の「たてる」「さんかする」と、URL の `?relay` で開いたとき）。LAN の画面へ移る。
   *
   * @returns つなぎ始めてよいか。もう接続を持っていれば false（接続は1本しか持たない。原型は押すたびにもう1本つないだ）
   */
  startConnecting(): boolean {
    if (this.#connecting) return false;
    this.#show('lan');
    this.#connecting = true;
    return true;
  }

  /**
   * 中継につなげなかった（ロビーへ移る前に止まった）。LAN の画面に留まり、「接続しています…」の行に理由を出す。
   * また押せる（「たてる」「さんかする」を出す）。
   */
  connectionFailed(reason: string): void {
    this.#connecting = false;
    this.#failure = reason;
  }

  /**
   * 1つ前の画面へもどる。タイトルでは何もしない。
   *
   * つないでいる最中の LAN の画面では呼ばない（戻ると接続が切れるので、呼ぶ側が先に確認の画面を出す）。
   */
  back(): void {
    if (this.#screen !== 'title') this.#show(BACK[this.#screen]);
  }

  /** 動物を選ぶ画面から、ルールを決める画面へ進む。 */
  next(): void {
    if (this.#screen === 'pick') this.#show('rules');
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

  /**
   * 試合や通信対戦から戻ってきたとき（原型の `backToSetup`）。選んだものは残し、タイトルから始める。
   *
   * 中継との接続は手放したものとして、「接続しています…」も消す（原型は消さずに残し、次に LAN の画面を開いても
   * 出ていた。表示の不具合なので写さない。Python 版と同じ）。
   */
  returnToTitle(): void {
    this.#connecting = false;
    this.#show('title');
  }

  /** 画面を替える。つなげなかった理由は、画面を替えたら消す（LAN の画面を出たら残さない）。 */
  #show(screen: MenuScreen): void {
    this.#screen = screen;
    this.#failure = '';
  }
}
