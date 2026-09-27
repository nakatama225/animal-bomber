import { IDLE_INTENT, type PlayerIntent } from '../src/domain/intent/PlayerIntent.js';
import type { PlayerId } from '../src/domain/state/PlayerState.js';
import { createWorld, type WorldState } from '../src/domain/state/WorldState.js';
import { startingBonusOf } from '../src/app/GameSession.js';
import { Simulation } from '../src/domain/systems/Simulation.js';

/**
 * テスト用の世界を作る。種を変えなければ何度でも同じ盤面になる。
 *
 * 前の tick の入力だけを、ラウンドの途中の状態（誰も何も押していない）にする。ラウンドの始まりは、
 * 爆弾のボタンを押していた扱いになっていて、最初の tick に押しても「押した瞬間」にならない。
 * そのままだと、押した瞬間を見るテストがどれも1 tick 待つ形になる。爆弾のボタンのラウンドの
 * 始まりの扱いは `tests/systems/round.test.ts` で `createWorld` から確かめる。
 *
 * ⚠️ 技のボタンのロック（`actionHeld` の -1）は、ラウンドの始まりのまま残る。技を見るテストは、
 * まず1 tick 離してから押す（`tests/abilities/charge.test.ts` の `triggerCharge`）。技のロック
 * そのものは `charge.test.ts` の「ラウンド開始時から押していると、離すまで出ない」で確かめる。
 */
export function makeWorld(seed = 1234, animals: string[] = ['rabbit', 'elephant']): WorldState {
  const world = createWorld({ seed, animals, bonusOf: startingBonusOf });
  for (const player of world.players) player.previousIntent = IDLE_INTENT;
  return world;
}

/** 指定した向きだけを押している意思。 */
export function press(partial: Partial<PlayerIntent>): PlayerIntent {
  return { ...IDLE_INTENT, ...partial };
}

/** 全員に同じ意思を配る。 */
export function sameForAll(
  world: WorldState,
  intent: PlayerIntent,
): ReadonlyMap<PlayerId, PlayerIntent> {
  const map = new Map<PlayerId, PlayerIntent>();
  for (const player of world.players) map.set(player.id, intent);
  return map;
}

/** 1人だけに意思を与え、残りは何もしない。 */
export function onlyFor(
  world: WorldState,
  playerId: PlayerId,
  intent: PlayerIntent,
): ReadonlyMap<PlayerId, PlayerIntent> {
  const map = new Map<PlayerId, PlayerIntent>();
  for (const player of world.players) {
    map.set(player.id, player.id === playerId ? intent : IDLE_INTENT);
  }
  return map;
}

/** 同じ意思で `ticks` 回進める。 */
export function advance(
  world: WorldState,
  intents: ReadonlyMap<PlayerId, PlayerIntent>,
  ticks: number,
  sim = new Simulation(),
): void {
  for (let i = 0; i < ticks; i += 1) sim.step(world, intents);
}

/**
 * 盤面の壊せるブロックを全部消す。
 *
 * 爆風の伸び方や経路を確かめるとき、種ごとに違うブロックの配置に
 * 結果が左右されないようにするため。
 */
export function clearBoard(world: WorldState): void {
  for (const { cell, tile } of world.board.cells()) {
    if (tile === 'soft') world.board.set(cell, 'empty');
  }
}
