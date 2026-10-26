import type { Tick } from '../../domain/core/Tick.js';
import type { WorldState } from '../../domain/state/WorldState.js';
import { secondsLeft } from '../hud/scoreboard.js';
import type { SoundBank } from './SoundBank.js';

/** 秒読みを始める残り秒数。 */
const COUNT_FROM = 10;

/**
 * 残り時間の秒読み。残り 10 秒から 0 秒まで、秒が変わるたびに短い音を鳴らす。
 *
 * 原型の `update` の「残り秒のチクタク」（`Math.ceil(G.time)` が 10 から 0 のあいだ、前に鳴らした秒と
 * 違えば `SE.tick()`。L4291-4293）を写した。0 秒でも鳴らす（原型と同じ。0 秒の tick には、ラウンドが
 * 決まった音か延長戦の音も同じ tick に鳴る）。
 *
 * 試合の側にこのためのイベントは無い。残り時間は盤面から計算できるので、
 * 秒の境目をこちらで数える。決着のあとの待ちの間は盤面が止まっていて秒が変わらないので、鳴らない。
 *
 * ## 延長戦
 *
 * 延長戦に入ると、時間切れの時刻が延長戦の長さぶん先へ移る。延長戦で 10 秒を切ると、また 10 秒から
 * 鳴らす（原型も同じ）。
 *
 * 延長戦に入る tick は、原型では先に 0 秒の秒読みを鳴らしてから、延長戦の音を鳴らす（update の頭で残り
 * 時間を引いて秒読みを鳴らし、最後の checkEnd で延長戦に入る）。この版は延長戦に入ったあとの盤面を受け取る
 * （`GameSession` が、同じ tick のうちに延長戦へ入れる）ので、延ばしたあとの時刻で数えると残り 60 秒に
 * 見えて、0 秒を鳴らさない。そこで、前の tick に見た時間切れの時刻で、その tick の残りを数える
 * （時刻が延びるのは延長戦に入るときだけで、ルールの層の 1 tick の中では変わらない）。Python 版の
 * `audio/countdown.py` と同じ形。
 */
export class Countdown {
  #world: Readonly<WorldState> | null = null;
  #endsAt: Tick | null = null;
  #last: number | null = null;

  constructor(private readonly sounds: SoundBank) {}

  /**
   * tick を進めるたびに、進めたあとの盤面を渡す。
   *
   * 盤面が替わったら（新しいラウンド）、前に鳴らした秒を忘れる（原型の `startRound` の `lastTickSecond=-1`）。
   * 忘れないと、次の盤面が前の盤面の最後と同じ秒から始まったとき（制限時間が 10 秒以下のとき）に、最初の
   * 1回を鳴らさない。鳴らした秒を覚えるのは、10〜0 秒の間で鳴らしたときだけ（原型の lastTickSecond も同じ）。
   * 延長戦に入っても忘れない（原型の enterSuddenDeath も戻さない）。
   */
  observe(world: Readonly<WorldState>): void {
    if (world !== this.#world) {
      this.#world = world;
      this.#endsAt = world.endsAt;
      this.#last = null;
    }
    // この tick の残りは、前の tick に見た時間切れの時刻で数える（クラスの説明）。
    const left = secondsLeft(world.now, this.#endsAt ?? world.endsAt);
    this.#endsAt = world.endsAt;
    if (left === this.#last || left < 0 || left > COUNT_FROM) return;
    this.#last = left;
    this.sounds.play('tick');
  }
}
