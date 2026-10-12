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
 * 倒れた人がまだ外周へ回れるか。残り時間が短くなると、外周は閉じる。
 *
 * ⚠️ 残り時間は設定の制限時間ではなく `world.endsAt` から数える。延長戦に入ると
 * 残りは延長戦の長さちょうどになり、外周は開かない。
 */
export function lanesOpen(world: Readonly<WorldState>): boolean {
  return world.endsAt - world.now > NEGIBON_CUTOFF;
}

/**
 * 倒れた人を外周へ送る。倒れた位置にいちばん近い外周の位置から始める。
 *
 * かかっている状態ととくぎの回数は持ち越さない。火力・爆弾の数・靴は持ち越す。
 * 戻るたびに初期値へ戻すと、終盤に誰も強くならず決着がつかない。
 *
 * ⚠️ 盤面に置いたままの爆弾の数（`activeBombs`）は戻さない。爆発したときに
 * 数え直すので、ここで 0 にすると、まだ盤面にある爆弾のぶんだけ多く置けてしまう。
 */
export function sendToLane(world: WorldState, player: PlayerState): void {
  player.life = {
    kind: 'negibon',
    along: nearestAlong(player.position),
    readyAt: tick(world.now + LEEK_FIRST_COOLDOWN),
  };
  for (const kind of EFFECT_KINDS) player.effects.clear(kind);
  player.specialCharges = 0;
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
  shooter.lastHitBy = null;
  // 技のボタンの押した長さには触らない（原型の negiHit も触らない）。外周にいる間は数えないので、
  // 倒れたときの長さが残る。押したまま戻ると、そこから数え続ける。とくぎの回数は外周へ回るときに
  // 0 にしてあるので、拾わない限りとくぎは出ない。

  return [{ type: 'revived', player: shooter.id, replaced: victim.id, at: { ...at } }];
}
