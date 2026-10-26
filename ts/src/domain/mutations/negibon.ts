import { tick } from '../core/Tick.js';
import type { SimEvent } from '../events/SimEvent.js';
import { nearestAlong } from '../negibon/lane.js';
import {
  LEEK_FIRST_COOLDOWN,
  NEGIBON_CUTOFF,
  REVIVE_HP,
  REVIVE_INVULNERABLE,
} from '../rules/negibon.js';
import { EFFECT_KINDS } from '../state/EffectBag.js';
import { ALIVE } from '../state/Life.js';
import type { PlayerState } from '../state/PlayerState.js';
import type { WorldState } from '../state/WorldState.js';

/**
 * 倒れたプレイヤーがまだ外周へ回れるか。残り時間が短くなると、外周は閉じる。1 tick を進める処理（`step`）の中で呼ぶ。
 *
 * 残りは、この tick のぶんを引いたあとの値（`endsAt − (now + 1)`）で見る。原型の L4288 と同じ形にするため。
 * 原型は update の頭（L4288）で残り時間 G.time から1フレームぶんを先に引き、倒れたプレイヤーの行き先（kill の L1700 →
 * negibonAvailable の L2364）も、外周を閉じるか（update の最後の checkEnd の L4411 → negibonCutoff の L2359）も、
 * 引いたあとの値で比べる。`now` を進めるのは step の最後なので、step の中の `now` で数えると残りを1 tick 多く
 * 数えてしまい、3:00 なら残り60秒ちょうどの tick（now=7199）に倒れたプレイヤーが外周へ回ってしまう（原型はその場で退場）。
 *
 * ⚠️ 7:00 の設定だけは、原型が外周を閉じるのが1 tick 遅い（21601 回目の update）。1/60 を小数で引き続けた
 * 誤差で、実数で数えれば 21600 回目になる。この版は実数の数え方のまま。
 *
 * ⚠️ 残り時間は設定の制限時間ではなく `world.endsAt` から数える。延長戦に入ると
 * 残りは延長戦の長さちょうどになり、外周は開かない。
 */
export function lanesOpen(world: Readonly<WorldState>): boolean {
  return world.endsAt - (world.now + 1) > NEGIBON_CUTOFF;
}

/**
 * 倒れたプレイヤーを外周へ送る。倒れた位置にいちばん近い外周の位置から始める。
 *
 * かかっている状態と、とくぎを持っている印（`hasSpecial`）は持ち越さない。火力・爆弾の数・靴は持ち越す。
 * 戻るたびに初期値へ戻すと、終盤に誰も強くならず決着がつかない。
 *
 * とくぎの回数（`specialCharges`）は残す。原型の toNegibon（L2255）と同じ形にするため。原型は持っている印
 * （chicken）だけを消し、回数（chickenCharges）には触らない。残った回数は見えず使えないが、同じラウンドのうちに
 * 盤面へ戻ってチキンを拾うと、その回数に足される（L1616-1617）。
 *
 * 盤面に置いている爆弾の数（`activeBombs`）は 0 に戻す。原型の toNegibon（L2256）と同じ。盤面に残った自分の爆弾が
 * あとで爆発しても、減らすのは 0 で止める（`removeBomb`。原型の L1494）ので負にはならない。
 * 0 に戻しても、盤面へ戻ったときに多く置けることは起きない。外周へ回ってから最初に撃てるまで 3.5 秒かかり、
 * 導火線（2.4 秒）より長いので、戻る時点では、倒れる前に置いた爆弾はもう爆発して盤面に残っていない。
 */
export function sendToLane(world: WorldState, player: PlayerState): void {
  player.life = {
    kind: 'negibon',
    along: nearestAlong(player.position),
    readyAt: tick(world.now + LEEK_FIRST_COOLDOWN),
  };
  for (const kind of EFFECT_KINDS) player.effects.clear(kind);
  player.hasSpecial = false;
  player.activeBombs = 0;
}

/**
 * 葱が当たった。撃った側が当たった側の位置で盤面へ戻り、当たった側が外周へ回る。
 *
 * @param shooter 葱を撃った葱ボン
 * @param victim 葱が当たった、盤面にいるプレイヤー
 */
export function swapPlaces(
  world: WorldState,
  shooter: PlayerState,
  victim: PlayerState,
): SimEvent[] {
  const at = { ...victim.position };
  sendToLane(world, victim);

  shooter.life = ALIVE;
  shooter.position = at;
  shooter.hp = REVIVE_HP;
  shooter.invulnerableUntil = tick(world.now + REVIVE_INVULNERABLE);
  // 最後に傷を付けた相手（`lastHitBy`）は戻さない。原型の negiHit（L2337-2356）も触らない。
  // 試合の中で読む所は無く、変わるのは状態の要約だけ。
  // 置いている爆弾の数も 0 に戻す（原型の negiHit L2347）。外周にいる間は爆弾を置けないので、ふつうはもう 0。
  shooter.activeBombs = 0;
  // かかっている状態と、盤面を離れても止めて残していた振る舞い（`ActiveAction.staysOffBoard`）を消す
  // （原型の negiHit L2347-2348 は effects={}・tongue=null・digging=null）。外周にいる間に振る舞いが爆風に触れて
  // 付いた泣く状態も、ここで消える。後始末（finish）は呼ばない。原型も消すだけで、掴んでいた物も一緒に消える
  // （延長戦の片付けと同じ）。
  for (const kind of EFFECT_KINDS) shooter.effects.clear(kind);
  shooter.action = null;
  // 技のボタンの押した長さには触らない（原型の negiHit も触らない）。外周にいる間は数えないので、
  // 倒れたときの長さが残る。押したまま戻ると、そこから数え続ける。とくぎを持っている印は外周へ回るときに
  // 外してあるので、拾わない限りとくぎは出ない。印と回数には触らない（原型の negiHit L2337-2356 も触らない）。

  return [{ type: 'revived', player: shooter.id, replaced: victim.id, at: { ...at } }];
}
