import { describe, expect, it } from 'vitest';

import type { ActiveAction } from '../../src/domain/abilities/ActiveAction.js';
import { centerOf, cellOf, DIRECTIONS, type Cell, type Direction } from '../../src/domain/core/Coord.js';
import { tick } from '../../src/domain/core/Tick.js';
import type { SimEvent } from '../../src/domain/events/SimEvent.js';
import type { PlayerInput } from '../../src/domain/input/PlayerInput.js';
import { placeBombAt } from '../../src/domain/mutations/bombs.js';
import { hurt } from '../../src/domain/mutations/damage.js';
import {
  alongsFacing,
  LANE_LENGTH,
  laneSpot,
  laneStep,
  nearestAlong,
  type LaneSide,
} from '../../src/domain/negibon/lane.js';
import { LeekActor } from '../../src/domain/negibon/LeekActor.js';
import {
  LANE_WIDTH,
  LEEK_COOLDOWN,
  LEEK_FIRST_COOLDOWN,
  NEGIBON_CUTOFF,
  REVIVE_HP,
  REVIVE_INVULNERABLE,
} from '../../src/domain/rules/negibon.js';
import { defaultMatchConfig } from '../../src/domain/rules/MatchConfig.js';
import { COLS, ROWS } from '../../src/domain/rules/tuning.js';
import { OUT, type Negibon } from '../../src/domain/state/Life.js';
import { isAlive, type PlayerId, type PlayerState } from '../../src/domain/state/PlayerState.js';
import type { WorldState } from '../../src/domain/state/WorldState.js';
import { RoundSystem } from '../../src/domain/systems/RoundSystem.js';
import { Simulation } from '../../src/domain/systems/Simulation.js';
import { clearBoard, makeWorld, press } from '../helpers.js';

/** 外周にいる状態にする。すぐ撃てる。 */
function onLane(player: PlayerState, along: number, readyAt = 0): void {
  player.life = { kind: 'negibon', along, readyAt: tick(readyAt) };
}

function laneOf(player: PlayerState): Negibon {
  if (player.life.kind !== 'negibon') throw new Error(`外周にいない: ${player.life.kind}`);
  return player.life;
}

/** そのマスの列（上辺から撃つとき）に向き合う、帯の上の位置。 */
function topAlongFor(col: number): number {
  return alongsFacing({ col, row: 1 })[0];
}

/** プレイヤー0だけに入力を与えて1 tick 進める。 */
function stepWith(world: WorldState, sim: Simulation, playerInput: PlayerInput, id: PlayerId = 0): SimEvent[] {
  const playerInputs = new Map<PlayerId, PlayerInput>();
  for (const player of world.players) playerInputs.set(player.id, player.id === id ? playerInput : press({}));
  return sim.step(world, playerInputs);
}

/** 1回撃って、葱が消えるまで進める。起きたイベントを返す。 */
function throwAndWait(world: WorldState, sim = new Simulation()): SimEvent[] {
  const events = stepWith(world, sim, press({ bomb: true }));
  for (let i = 0; i < 400 && world.actors.some((a) => a instanceof LeekActor); i += 1) {
    events.push(...stepWith(world, sim, press({})));
  }
  return events;
}

/** 葱を撃つ場面。盤面を空にして、プレイヤー0を上辺の `col` 列の上に置く。 */
function shootingRange(col: number): { world: WorldState; shooter: PlayerState; target: PlayerState } {
  const world = makeWorld(3, ['rabbit', 'elephant']);
  clearBoard(world);
  const shooter = world.players[0]!;
  const target = world.players[1]!;
  onLane(shooter, topAlongFor(col));
  target.position = centerOf({ col: 1, row: 13 });
  return { world, shooter, target };
}

describe('外周の帯の位置', () => {
  it('上辺の左端から時計回りに1周する', () => {
    const near = -LANE_WIDTH / 2;
    expect(laneSpot(0)).toEqual({ position: { x: 1.5, y: near }, facing: 'down', side: 'top' });
    expect(laneSpot(COLS - 2)).toEqual({ position: { x: COLS + LANE_WIDTH / 2, y: 1.5 }, facing: 'left', side: 'right' });
    expect(laneSpot(COLS - 2 + ROWS - 2).side).toBe('bottom');
    expect(laneSpot(2 * (COLS - 2) + ROWS - 2).side).toBe('left');
    expect(laneSpot(LANE_LENGTH)).toEqual(laneSpot(0));
    expect(laneSpot(-1)).toEqual(laneSpot(LANE_LENGTH - 1));
  });

  it('帯はいつも盤面の外にあり、撃つ向きは盤面の内側を向く', () => {
    for (let along = 0; along < LANE_LENGTH; along += 0.25) {
      const { position, facing } = laneSpot(along);
      const outside = position.x < 0 || position.y < 0 || position.x > COLS || position.y > ROWS;
      expect(outside, `${along}`).toBe(true);
      const inward: Record<Direction, boolean> = {
        down: position.y < 0,
        up: position.y > ROWS,
        right: position.x < 0,
        left: position.x > COLS,
      };
      expect(inward[facing], `${along}`).toBe(true);
    }
  });

  it('内側のどのマスにも、4辺それぞれからまっすぐ撃てる位置がある', () => {
    for (let row = 1; row < ROWS - 1; row += 1) {
      for (let col = 1; col < COLS - 1; col += 1) {
        const target: Cell = { col, row };
        for (const along of alongsFacing(target)) {
          const { position, facing } = laneSpot(along);
          const vertical = facing === 'up' || facing === 'down';
          const lane = cellOf(position);
          expect(vertical ? lane.col : lane.row, `${col},${row} ← ${along}`).toBe(vertical ? col : row);
        }
      }
    }
  });

  it('倒れた場所から、いちばん近い辺の同じ列（行）へ回る', () => {
    expect(laneSpot(nearestAlong({ x: 7.5, y: 1.5 }))).toMatchObject({ side: 'top', position: { x: 7.5 } });
    expect(laneSpot(nearestAlong({ x: 1.5, y: 9.5 }))).toMatchObject({ side: 'left', position: { y: 9.5 } });
    expect(laneSpot(nearestAlong({ x: 21.5, y: 9.5 }))).toMatchObject({ side: 'right', position: { y: 9.5 } });
    expect(laneSpot(nearestAlong({ x: 7.5, y: 15.5 }))).toMatchObject({ side: 'bottom', position: { x: 7.5 } });
  });

  it('どの辺でも、押した向きへ動く（下辺と左辺で逆にならない）', () => {
    // 帯の上の位置は下辺では左へ、左辺では上へ増える。キーを位置の増減に直結すると逆になる。
    const middles: Record<LaneSide, number> = {
      top: 10,
      right: COLS - 2 + 7,
      bottom: COLS - 2 + ROWS - 2 + 10,
      left: 2 * (COLS - 2) + ROWS - 2 + 7,
    };
    for (const [side, along] of Object.entries(middles) as [LaneSide, number][]) {
      for (const direction of DIRECTIONS) {
        const move = laneStep(side, press({ [direction]: true }));
        const before = laneSpot(along).position;
        const after = laneSpot(along + move * 0.5).position;
        const moved = { up: before.y - after.y, down: after.y - before.y, left: before.x - after.x, right: after.x - before.x };
        const alongSide = side === 'top' || side === 'bottom' ? direction === 'left' || direction === 'right' : direction === 'up' || direction === 'down';
        if (alongSide) expect(moved[direction], `${side} ${direction}`).toBeGreaterThan(0);
        else expect(move, `${side} ${direction}`).toBe(0);
      }
    }
  });
});

describe('倒れたら外周へ回る', () => {
  it('残り時間があれば、倒れた場所に近い外周から、少し待ってから撃てる', () => {
    const world = makeWorld(3, ['rabbit', 'elephant']);
    world.now = tick(100);
    const player = world.players[0]!;
    player.position = centerOf({ col: 7, row: 1 });
    player.hp = 2;
    player.power = 4;
    player.activeBombs = 1;
    player.specialCharges = 2;
    player.effects.add('slow', tick(300), tick(300));
    const events = hurt(world, player, 1, 2);

    expect(events.at(-1)).toMatchObject({ type: 'playerDown', target: 0, at: { x: 7.5, y: 1.5 } });
    const lane = laneOf(player);
    expect(laneSpot(lane.along)).toMatchObject({ side: 'top', position: { x: 7.5 } });
    expect(lane.readyAt).toBe(100 + LEEK_FIRST_COOLDOWN);
    // 状態ととくぎは持ち越さない。火力と、盤面に残った爆弾の数は持ち越す。
    expect(player.effects.active()).toEqual([]);
    expect(player.specialCharges).toBe(0);
    expect(player.power).toBe(4);
    expect(player.activeBombs).toBe(1);
  });

  it('残りが外周の閉じる時刻を切っていれば、外周へ回らず退場する', () => {
    const world = makeWorld(3, ['rabbit', 'elephant']);
    world.endsAt = tick(world.now + NEGIBON_CUTOFF);
    const player = world.players[0]!;
    player.hp = 2;
    hurt(world, player, 1, 2);
    expect(player.life).toBe(OUT);
  });

  it('盤面を離れた人の技は、もう進めずに終える', () => {
    // 進めると、盤面にいない人の技が1 tick ぶん働く（拾った物が外周の葱ボンに渡る、など）。
    const world = makeWorld(3, ['rabbit', 'elephant']);
    const player = world.players[0]!;
    let ticked = 0;
    let finished = 0;
    const probe: ActiveAction = {
      kind: 'probe',
      drivesMovement: true,
      damageCap: null,
      untouchable: false,
      canPlaceBomb: false,
      sweepsItems: false,
      tick: () => {
        ticked += 1;
        return { events: [], done: false };
      },
      finish: () => {
        finished += 1;
        return [];
      },
    };
    player.action = probe;
    onLane(player, 0);
    stepWith(world, new Simulation(), press({}));
    expect(ticked).toBe(0);
    expect(finished).toBe(1);
    expect(player.action).toBeNull();
  });
});

describe('外周を動いて撃つ', () => {
  it('押した向きへ外周を動く', () => {
    const world = makeWorld(3, ['rabbit', 'elephant']);
    const player = world.players[0]!;
    onLane(player, 10);
    const sim = new Simulation();
    for (let i = 0; i < 30; i += 1) stepWith(world, sim, press({ right: true }));
    expect(laneSpot(laneOf(player).along).position.x).toBeGreaterThan(laneSpot(10).position.x);
  });

  it('撃てるまでは撃てず、撃ったあとはしばらく撃てない。押しっぱなしでは続けて撃たない', () => {
    const world = makeWorld(3, ['rabbit', 'elephant']);
    const player = world.players[0]!;
    onLane(player, 10, 5);
    const sim = new Simulation();
    const thrown = (playerInput: PlayerInput): number =>
      stepWith(world, sim, playerInput).filter((e) => e.type === 'leekThrown').length;

    expect(thrown(press({ bomb: true }))).toBe(0); // 撃てるまで待つ
    thrown(press({}));
    for (let i = 0; i < 5; i += 1) thrown(press({}));
    expect(thrown(press({ action: true }))).toBe(1); // 技のボタンでも撃てる
    expect(laneOf(player).readyAt).toBe(world.now - 1 + LEEK_COOLDOWN);
    let total = 0;
    for (let i = 0; i < LEEK_COOLDOWN + 10; i += 1) total += thrown(press({ action: true }));
    expect(total).toBe(0); // 押しっぱなしでは撃たない
  });
});

describe('葱が飛ぶ', () => {
  it('外壁をすり抜けて相手に当たると、撃った側が相手の位置へ戻り、相手が外周へ回る', () => {
    const { world, shooter, target } = shootingRange(5);
    target.position = centerOf({ col: 5, row: 3 });
    const events = throwAndWait(world);

    const revived = events.find((e) => e.type === 'revived');
    expect(revived).toEqual({ type: 'revived', player: 0, replaced: 1, at: { x: 5.5, y: 3.5 } });
    expect(isAlive(shooter)).toBe(true);
    expect(shooter.position).toEqual({ x: 5.5, y: 3.5 });
    expect(shooter.hp).toBe(REVIVE_HP);
    expect(shooter.invulnerableUntil).toBeGreaterThan(world.now);
    expect(shooter.invulnerableUntil).toBeLessThanOrEqual(world.now + REVIVE_INVULNERABLE);
    // 戻った直後は、技のボタンを一度離すまで効かない。
    expect(shooter.actionHeld).toBe(-1);
    expect(target.life.kind).toBe('negibon');
  });

  it('無敵中の相手は通り抜ける', () => {
    // 当たると、戻った直後の相手に撃ち返せてしまい、入れ替わりが止まらない。
    const { world, shooter, target } = shootingRange(5);
    target.position = centerOf({ col: 5, row: 3 });
    target.invulnerableUntil = tick(1000);
    const events = throwAndWait(world);
    expect(events.some((e) => e.type === 'revived')).toBe(false);
    expect(shooter.life.kind).toBe('negibon');
    expect(isAlive(target)).toBe(true);
  });

  it('跳び上がっている相手も通り抜ける（原型の isUntouchable はキツネ跳びを含む）', () => {
    const { world, shooter, target } = shootingRange(5);
    target.position = centerOf({ col: 5, row: 3 });
    // 葱が届くまでの間に切れないよう、長めにかけておく。
    target.effects.add('leap', tick(600), tick(600));
    const events = throwAndWait(world);
    expect(events.some((e) => e.type === 'revived')).toBe(false);
    expect(shooter.life.kind).toBe('negibon');
    expect(isAlive(target)).toBe(true);
  });

  it('柱で砕ける', () => {
    // 6 列目は2行目に柱がある。
    const { world } = shootingRange(6);
    const events = throwAndWait(world);
    expect(events).toContainEqual({ type: 'leekStopped', cell: { col: 6, row: 2 }, by: 'wall' });
  });

  it('爆弾に弾かれる', () => {
    const { world, target } = shootingRange(5);
    placeBombAt(world, target, { col: 5, row: 2 })!.fuse = tick(1000);
    const events = throwAndWait(world);
    expect(events).toContainEqual({ type: 'leekStopped', cell: { col: 5, row: 2 }, by: 'bomb' });
  });

  it('爆風で焼ける', () => {
    const { world } = shootingRange(5);
    world.blasts.push({ id: world.ids.take(), cell: { col: 5, row: 2 }, owner: 1, isCenter: true, remaining: tick(1000) });
    const events = throwAndWait(world);
    expect(events).toContainEqual({ type: 'leekStopped', cell: { col: 5, row: 2 }, by: 'blast' });
  });

  it('射程を越えると落ちる。盤面の中央までは届かない', () => {
    const { world } = shootingRange(5);
    const events = throwAndWait(world);
    const stop = events.find((e) => e.type === 'leekStopped');
    expect(stop).toMatchObject({ by: 'range' });
    expect(stop?.type === 'leekStopped' && stop.cell.row).toBeLessThan(Math.floor(ROWS / 2));
  });
});

describe('外周が閉じる', () => {
  it('残りが閉じる時刻を切ったら、外周の全員が退場して、飛んでいる葱も消える', () => {
    const world = makeWorld(3, ['rabbit', 'elephant', 'mole']);
    const sim = new Simulation();
    onLane(world.players[0]!, 5);
    onLane(world.players[2]!, 40);
    world.actors.push(new LeekActor({ x: 5.5, y: 0.5 }, 'down', 0));
    world.endsAt = tick(world.now + NEGIBON_CUTOFF + 1);

    expect(stepWith(world, sim, press({})).some((e) => e.type === 'lanesClosed')).toBe(false);
    const closed = stepWith(world, sim, press({}));
    expect(closed).toContainEqual({ type: 'lanesClosed', players: [0, 2] });
    expect(world.players[0]!.life).toBe(OUT);
    expect(world.players[2]!.life).toBe(OUT);
    expect(world.actors.some((a) => a instanceof LeekActor)).toBe(false);
    // 2度目は出ない。
    expect(stepWith(world, sim, press({})).some((e) => e.type === 'lanesClosed')).toBe(false);
  });
});

describe('ラウンドの決着と葱ボン', () => {
  it('盤面に1人だけ残れば、外周の葱ボンを待たずに決着', () => {
    const world = makeWorld(3, ['rabbit', 'elephant', 'mole']);
    onLane(world.players[1]!, 5);
    onLane(world.players[2]!, 30);
    const verdict = new RoundSystem().judge(world, defaultMatchConfig(3, ['rabbit', 'elephant', 'mole']), []);
    expect(verdict).toEqual({ type: 'over', outcome: { winner: 0, reason: 'lastStanding' } });
  });
});
