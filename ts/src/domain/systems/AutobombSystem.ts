import { tick } from '../core/Tick.js';
import type { SimEvent } from '../events/SimEvent.js';
import { placeBomb } from '../mutations/bombs.js';
import { AUTOBOMB_INTERVAL } from '../rules/tuning.js';
import type { PlayerState } from '../state/PlayerState.js';
import { isAlive } from '../state/PlayerState.js';
import type { WorldState } from '../state/WorldState.js';

/**
 * 「勝手に設置」がかかっているプレイヤーに、拍ごとに爆弾を置かせる。
 *
 * ボタンで置く爆弾（`BombSystem`）と分けてあるのは、置く時期が違うから。原型は効果の
 * 時間を進める処理の中で全員ぶんの勝手に設置を済ませ、そのあとで各プレイヤーを入力で
 * 動かす（`legacy/animal-bomber.html` の update）。ボタンの爆弾は動いたあとに見る
 * （humanUpdate）。`Simulation` はこの処理を移動（`MovementSystem`）の前に、`BombSystem` を
 * 移動のあとに並べる。拍の tick にマスの境目をまたいでも、置くのは今までいたマスになる。
 * 全員ぶんをボタンの爆弾より先に置くので、同じ tick に置く順と識別子も原型と同じになる
 * （番号の小さいプレイヤーがボタンで置いた tick に、別のプレイヤーの拍が来たときも）。
 *
 * ⚠️ 技（`ActionSystem`）との順は原型と違う。原型はプレイヤーごとに「そのプレイヤーの
 * 技を進める → そのプレイヤーの勝手に設置」と回し、技を始めるのはそのあと（入力の処理）。ここでは全員の技を進めて
 * 始めてから、勝手に設置を置く。そのため、技を始める tick と拍が重なったとき（原型は
 * 置いてから技を始める。ここでは技が先に始まり、置けない技なら拍だけ進む）と、番号の
 * 大きいプレイヤーが技で進んで拍のプレイヤーを押しのけるとき（原型は置いてから技が
 * 進み、その爆弾を同じ tick に起爆する）は、原型と答えが違う。
 */
export class AutobombSystem {
  step(world: WorldState): SimEvent[] {
    const events: SimEvent[] = [];
    for (const player of world.players) {
      if (!isAlive(player)) continue;
      // 拍は、このあと置けずに飛ばす場合も進める。原型も、置けなかった拍の次は1拍あと。
      if (!this.#beat(player)) continue;
      // 乗っ取り中に置けるかは、その振る舞いが決める。
      if (player.action !== null && !player.action.canPlaceBomb) continue;
      // 「爆弾おけない」は見ない。勝手に設置がかかっていると、爆弾おけないを上書きする
      // （`BombSystem` の説明）。
      const bomb = placeBomb(world, player);
      if (bomb !== undefined) {
        events.push({ type: 'bombPlaced', cell: bomb.cell, owner: bomb.owner });
      }
    }
    return events;
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
