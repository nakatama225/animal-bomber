import { centerOf, type Cell } from '../core/Coord.js';
import { tick } from '../core/Tick.js';
import type { SimEvent } from '../events/SimEvent.js';
import {
  SUDDEN_DEATH_HP,
  SUDDEN_DEATH_INVULNERABLE,
  SUDDEN_DEATH_LENGTH,
} from '../rules/suddenDeath.js';
import { MAX_BOMBS, MAX_POWER, MAX_SHOES, SPAWN_CELLS } from '../rules/tuning.js';
import { EFFECT_KINDS } from '../state/EffectBag.js';
import { ALIVE, OUT } from '../state/Life.js';
import type { PlayerId, PlayerState } from '../state/PlayerState.js';
import type { WorldState } from '../state/WorldState.js';

/**
 * 延長戦（サドンデス）に入る。
 *
 * 盤面は作り直さず、いまの盤面を片付けて使う。壊せるブロックをすべて消し、
 * 爆弾・爆風・アイテム・飛び道具を取り除く。加わるプレイヤーは、プレイヤー番号の順に開始位置の表
 * （`SPAWN_CELLS`）の隅へ移る（始まった隅とは限らない。原型と同じ）。体力を1個ぶんにして、
 * 爆弾・火力・靴を上限にする。決着を急がせるため。
 * 加わらないプレイヤーは退場する。
 *
 * 柱の並びは種によらず決まっているので、壊せるブロックを消せば、作り直した
 * 盤面と同じになる。作り直す場合と違って乱数を取り出さない。
 *
 * @param players 延長戦に加わるプレイヤー
 * @param reason 延長戦に入ったわけ
 */
export function enterSuddenDeath(
  world: WorldState,
  players: readonly PlayerId[],
  reason: 'allDown' | 'timeUp',
): SimEvent[] {
  world.suddenDeath = true;
  world.endsAt = tick(world.now + SUDDEN_DEATH_LENGTH);

  // 走査しながら書き換えないよう、先に集めてから消す。
  const softCells: Cell[] = [];
  for (const { cell, tile } of world.board.cells()) if (tile === 'soft') softCells.push(cell);
  for (const cell of softCells) world.board.set(cell, 'empty');

  world.bombs = [];
  world.blasts = [];
  world.items = [];
  world.actors = [];

  const joining = new Set(players);
  // 開始位置は、加わるプレイヤーにプレイヤー番号の順で1つずつ割り当てる。
  let slot = 0;
  for (const player of world.players) {
    clearRoundState(player);
    if (!joining.has(player.id)) {
      player.life = OUT;
      continue;
    }
    const spawn = SPAWN_CELLS[slot % SPAWN_CELLS.length]!;
    slot += 1;
    player.life = ALIVE;
    player.position = centerOf(spawn);
    player.hp = SUDDEN_DEATH_HP;
    player.maxBombs = MAX_BOMBS;
    player.power = MAX_POWER;
    player.shoes = MAX_SHOES;
    player.invulnerableUntil = tick(world.now + SUDDEN_DEATH_INVULNERABLE);
  }

  // 加わるプレイヤーは、渡された順ではなくプレイヤー番号の順で知らせる。
  const joined = world.players.filter((player) => joining.has(player.id)).map((player) => player.id);
  return [{ type: 'suddenDeath', reason, players: joined }];
}

/**
 * 延長戦へ持ち越さない状態を戻す。
 *
 * ⚠️ 乗っ取り中の振る舞い（`action`）は必ず外す。外さないと、技の続きが
 * 開始位置で走り、動けないまま固まる（原型にも同じ注意書きがある）。
 */
function clearRoundState(player: PlayerState): void {
  player.activeBombs = 0;
  for (const kind of EFFECT_KINDS) player.effects.clear(kind);
  player.action = null;
  // とくぎは印も回数も戻す（原型の enterSuddenDeath L4448。外周で残った回数もここで消える）。
  player.hasSpecial = false;
  player.specialCharges = 0;
  // 技のボタンの長押しは数え直す（原型の enterSuddenDeath）。押したまま延長戦に入ると、
  // そこからしきい値ぶん押し続ければ、とくぎがもう一度出る（チキンを拾っていれば）。
  // 前の tick の入力（`previousInput`）には触らないので、押した瞬間にはならない。
  player.actionHeld = tick(0);
  player.actionFired = false;
  player.abilityCooldown = tick(0);
  // 最後に傷を付けた相手（`lastHitBy`）は戻さない。原型の enterSuddenDeath（L4446-4461）も触らない。
  // 試合の中で読む所は無く、変わるのは状態の要約だけ。
}
