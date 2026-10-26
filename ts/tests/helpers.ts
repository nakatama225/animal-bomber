import { IDLE_INPUT, type PlayerInput } from '../src/domain/input/PlayerInput.js';
import type { PlayerId, PlayerState } from '../src/domain/state/PlayerState.js';
import { createWorld, type WorldState } from '../src/domain/state/WorldState.js';
import { startingBonusOf } from '../src/app/GameSession.js';
import { Simulation } from '../src/domain/systems/Simulation.js';

/**
 * テスト用の世界を作る。種を変えなければ何度でも同じ盤面になる。
 *
 * 前の tick の入力だけを、ラウンドの途中の状態（誰も何も押していない）にする。ラウンドの始まりは、
 * 爆弾と技のボタンを押していた扱いになっていて、最初の tick に押しても「押した瞬間」にならない。
 * そのままだと、押した瞬間を見るテストがどれも1 tick 待つ形になる。ボタンのラウンドの
 * 始まりの扱いは `tests/systems/round.test.ts` で `createWorld` から確認する。
 *
 * ⚠️ 技のボタンの「とくぎを出し終えた扱い」（`actionFired` の true）は、ラウンドの始まりのまま残る。
 * 長押しのとくぎを見るテストは、まず1 tick 離してから押す（`tests/abilities/charge.test.ts` の
 * `triggerCharge`）。そのものは `charge.test.ts` の「ラウンド開始時から押していると、離すまで出ない」で確認する。
 */
export function makeWorld(seed = 1234, animals: string[] = ['rabbit', 'elephant']): WorldState {
  const world = createWorld({ seed, animals, bonusOf: startingBonusOf });
  for (const player of world.players) player.previousInput = IDLE_INPUT;
  return world;
}

/**
 * チキンを拾ってとくぎを `charges` 回ぶん持った状態にする。0 なら持たない状態にする。
 *
 * ⚠️ とくぎを持っているか（`hasSpecial`）と回数（`specialCharges`）は別に持つ（原型の chicken と chickenCharges）。
 * 回数だけを書いても、とくぎは出ない。
 */
export function grantSpecial(player: PlayerState, charges: number): void {
  player.hasSpecial = charges > 0;
  player.specialCharges = charges;
}

/** 指定した向きだけを押している入力。 */
export function press(partial: Partial<PlayerInput>): PlayerInput {
  return { ...IDLE_INPUT, ...partial };
}

/** 全員に同じ入力を配る。 */
export function sameForAll(
  world: WorldState,
  playerInput: PlayerInput,
): ReadonlyMap<PlayerId, PlayerInput> {
  const map = new Map<PlayerId, PlayerInput>();
  for (const player of world.players) map.set(player.id, playerInput);
  return map;
}

/** 1人だけに入力を与え、残りは何も押していない入力にする。 */
export function onlyFor(
  world: WorldState,
  playerId: PlayerId,
  playerInput: PlayerInput,
): ReadonlyMap<PlayerId, PlayerInput> {
  const map = new Map<PlayerId, PlayerInput>();
  for (const player of world.players) {
    map.set(player.id, player.id === playerId ? playerInput : IDLE_INPUT);
  }
  return map;
}

/** 同じ入力で `ticks` 回進める。 */
export function advance(
  world: WorldState,
  playerInputs: ReadonlyMap<PlayerId, PlayerInput>,
  ticks: number,
  sim = new Simulation(),
): void {
  for (let i = 0; i < ticks; i += 1) sim.step(world, playerInputs);
}

/**
 * 盤面の壊せるブロックを全部消す。
 *
 * 爆風の伸び方や経路を確認するとき、種ごとに違うブロックの配置に
 * 結果が左右されないようにするため。
 */
export function clearBoard(world: WorldState): void {
  for (const { cell, tile } of world.board.cells()) {
    if (tile === 'soft') world.board.set(cell, 'empty');
  }
}
