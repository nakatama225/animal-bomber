import { tick } from '../core/Tick.js';
import type { SimEvent } from '../events/SimEvent.js';
import { placeBomb } from '../mutations/bombs.js';
import { AUTOBOMB_INTERVAL } from '../rules/tuning.js';
import type { PlayerState } from '../state/PlayerState.js';
import { canPlaceBomb, isAlive } from '../state/PlayerState.js';
import type { WorldState } from '../state/WorldState.js';

/**
 * 「勝手に設置」がかかっているプレイヤーに、拍ごとに爆弾を置かせる。
 *
 * ボタンで置く爆弾（`BombSystem`）と分けてあるのは、置く時期が違うから。原型は効果の
 * 時間を進める処理の中で、プレイヤーごとに「そのプレイヤーの技を進める → そのプレイヤーの
 * 勝手に設置」と順に処理し、そのあとで各プレイヤーを入力で動かして技を始める（`legacy/animal-bomber.html`
 * の update）。ボタンの爆弾は動いたあとに見る（humanUpdate）。
 *
 * `Simulation` は、プレイヤーごとに技を進めた直後にこれを呼ぶ。新しく技を始めるのと、入力で
 * 動く（`MovementSystem`）のは、全員ぶんの勝手に設置のあと。そのため、
 *
 * - 拍の tick にマスの境目をまたいでも、置くのは今までいたマス
 * - 技を始める tick に拍が来たら、置いてから技を始める
 * - 番号の大きいプレイヤーの技が拍のプレイヤーを押しのけるときは、置いてから押しのける
 *   （同じ tick にその爆弾を起爆することもある）。番号の小さいプレイヤーの技なら、押しのけた
 *   あとのマスに置く
 *
 * が原型と同じになる。全員ぶんをボタンの爆弾より先に置くので、同じ tick に置く順と識別子も
 * 原型と同じ（番号の小さいプレイヤーがボタンで置いた tick に、別のプレイヤーの拍が来たときも）。
 */
export class AutobombSystem {
  /** 1人ぶん。拍が来ていて置ける状態なら、足元に置く。 */
  step(world: WorldState, player: PlayerState): SimEvent[] {
    if (!isAlive(player)) return [];
    // 拍は、このあと置けずに飛ばす場合も進める。原型も、置けなかった拍の次は1拍あと。
    if (!this.#beat(player)) return [];
    // 落とし穴にはまっている間と、置けない振る舞いの最中は置かない（`canPlaceBomb`）。
    // 「爆弾おけない」には止められない。勝手に設置がかかっている間は、そちらが勝つ。
    if (!canPlaceBomb(player)) return [];
    const bomb = placeBomb(world, player);
    if (bomb === undefined) return [];
    return [{ type: 'bombPlaced', cell: bomb.cell, owner: bomb.owner }];
  }

  /**
   * 置こうとする拍か。かかっている間だけ、待ちを1 tick 進める。
   *
   * 前にかかったときの待ちが残っていなければ、かかった次の tick が最初の拍になり、
   * そのあとは `AUTOBOMB_INTERVAL` ごと。待ちを 0 に戻すのはラウンドの始まりだけ。
   */
  #beat(player: PlayerState): boolean {
    if (!player.effects.has('autobomb')) return false;
    const wait = Math.max(0, player.autobombWait - 1);
    if (wait > 0) {
      player.autobombWait = tick(wait);
      return false;
    }
    player.autobombWait = AUTOBOMB_INTERVAL;
    return true;
  }
}
