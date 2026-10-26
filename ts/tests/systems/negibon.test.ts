import { describe, expect, it } from 'vitest';

import type { ActiveAction } from '../../src/domain/abilities/ActiveAction.js';
import { abilityOf } from '../../src/domain/abilities/registry.js';
import { centerOf, cellOf, DIRECTIONS, type Cell, type Direction } from '../../src/domain/core/Coord.js';
import { secondsToTicks, tick } from '../../src/domain/core/Tick.js';
import type { SimEvent } from '../../src/domain/events/SimEvent.js';
import type { PlayerInput } from '../../src/domain/input/PlayerInput.js';
import { placeBombAt } from '../../src/domain/mutations/bombs.js';
import { hurt } from '../../src/domain/mutations/damage.js';
import { swapPlaces } from '../../src/domain/mutations/negibon.js';
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
import { clearBoard, grantSpecial, makeWorld, press } from '../helpers.js';

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
    grantSpecial(player, 2);
    player.effects.add('slow', tick(300), tick(300));
    const events = hurt(world, player, 1, 2);

    expect(events.at(-1)).toMatchObject({ type: 'playerDown', target: 0, at: { x: 7.5, y: 1.5 } });
    const lane = laneOf(player);
    expect(laneSpot(lane.along)).toMatchObject({ side: 'top', position: { x: 7.5 } });
    expect(lane.readyAt).toBe(100 + LEEK_FIRST_COOLDOWN);
    // 状態と、とくぎを持っている印は持ち越さない。とくぎの回数は残る（原型の toNegibon L2255 は chicken だけを
    // 消し、chickenCharges には触らない）。火力は持ち越す。置いている爆弾の数は 0 に戻す（原型 L2256）。
    expect(player.effects.active()).toEqual([]);
    expect([player.hasSpecial, player.specialCharges]).toEqual([false, 2]);
    expect(player.power).toBe(4);
    expect(player.activeBombs).toBe(0);
  });

  it('盤面に残した自分の爆弾が外周にいる間に爆発しても、置いている数は 0 のまま（原型 L2256 で 0 にし、L1494 は 0 で止める）', () => {
    const world = makeWorld(3, ['rabbit', 'elephant']);
    clearBoard(world);
    const player = world.players[0]!;
    player.position = centerOf({ col: 3, row: 3 });
    placeBombAt(world, player, { col: 3, row: 3 });
    expect(player.activeBombs).toBe(1);
    player.hp = 2;
    hurt(world, player, 1, 2);
    expect(player.activeBombs).toBe(0);
    const sim = new Simulation();
    for (let i = 0; i < 300 && world.bombs.length > 0; i += 1) stepWith(world, sim, press({}));
    expect(world.bombs).toEqual([]);
    expect(player.activeBombs).toBe(0);
  });

  it('葱で戻るとき、撃った側の置いている爆弾の数を 0 に戻す（原型の negiHit L2347）', () => {
    const world = makeWorld(3, ['rabbit', 'elephant']);
    const [shooter, victim] = world.players as [PlayerState, PlayerState];
    onLane(shooter, 5);
    shooter.activeBombs = 2;
    swapPlaces(world, shooter, victim);
    expect(isAlive(shooter)).toBe(true);
    expect(shooter.activeBombs).toBe(0);
  });

  it('葱で戻っても、撃った側の最後に傷を付けた相手（lastHitBy）は戻さない（原型の negiHit L2337-2356 は触らない）', () => {
    // 試合の中で読む所は無く、変わるのは状態の要約だけ。原型に合わせる。
    const world = makeWorld(3, ['rabbit', 'elephant']);
    const [shooter, victim] = world.players as [PlayerState, PlayerState];
    shooter.lastHitBy = 1;
    onLane(shooter, 5);
    swapPlaces(world, shooter, victim);
    expect(shooter.lastHitBy).toBe(1);
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
      blocksButtons: false,
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

describe('とくぎを持っている印と回数（原型の chicken と chickenCharges）', () => {
  /** とくぎを2回ぶん持ったまま倒れて外周へ回り、葱を当てて盤面の (5,5) へ戻ったプレイヤー。 */
  function backFromLane(animal: string): { world: WorldState; player: PlayerState; sim: Simulation } {
    const world = makeWorld(3, [animal, 'elephant']);
    clearBoard(world);
    const [player, other] = world.players as [PlayerState, PlayerState];
    grantSpecial(player, 2);
    player.hp = 2;
    hurt(world, player, 1, 2);
    other.position = centerOf({ col: 5, row: 5 });
    swapPlaces(world, player, other);
    const sim = new Simulation();
    // ラウンドの始まりの「とくぎは出し終えた扱い」を外すため、1 tick 離しておく。
    stepWith(world, sim, press({}));
    return { world, player, sim };
  }

  const specialsIn = (events: readonly SimEvent[]): number =>
    events.filter((e) => e.type === 'techniqueUsed' && e.special).length;

  it('葱で戻っても印は外れたまま、回数は残っている（原型の negiHit L2337-2356 はどちらにも触らない）', () => {
    const { player } = backFromLane('rabbit');
    expect(isAlive(player)).toBe(true);
    expect([player.hasSpecial, player.specialCharges]).toEqual([false, 2]);
  });

  it.each([
    { animal: 'rabbit', expected: 3 },
    { animal: 'frog', expected: 4 },
  ])('戻ってチキンを拾うと印が戻り、残っていた回数に足される（原型 L1616-1617。$animal は 2 + 倍率）', ({ animal, expected }) => {
    const { world, player, sim } = backFromLane(animal);
    world.items.push({ id: world.ids.take(), cell: cellOf(player.position), kind: 'chicken' });
    stepWith(world, sim, press({}));
    expect([player.hasSpecial, player.specialCharges]).toEqual([true, expected]);
  });

  it('残った回数だけでは、とくぎを直に出すボタンでも出ない（原型の doSpecial L2455 は chicken を見る）', () => {
    const { world, player, sim } = backFromLane('rabbit');
    expect(specialsIn(stepWith(world, sim, press({ special: true })))).toBe(0);
    expect(player.specialCharges).toBe(2);
  });

  it('残った回数だけでは、長押しでも出ない（原型の doSpecial L2455）', () => {
    const { world, player, sim } = backFromLane('rabbit');
    const events: SimEvent[] = [];
    for (let i = 0; i < abilityOf('rabbit').holdTicks + 5; i += 1) events.push(...stepWith(world, sim, press({ action: true })));
    expect(specialsIn(events)).toBe(0);
    expect(player.specialCharges).toBe(2);
  });

  it('残った回数だけでは、通常技の無い動物のポン押しでも出ない（原型の doAction L2445）', () => {
    const { world, player, sim } = backFromLane('mole');
    expect(specialsIn(stepWith(world, sim, press({ action: true })))).toBe(0);
    expect(player.specialCharges).toBe(2);
  });

  it('使うと回数が1つ減り、0 になると印が外れる（原型の useSpecial L2607-2608）', () => {
    const world = makeWorld(3, ['rabbit', 'elephant']);
    clearBoard(world);
    const player = world.players[0]!;
    grantSpecial(player, 2);
    const sim = new Simulation();
    expect(specialsIn(stepWith(world, sim, press({ special: true })))).toBe(1);
    expect([player.hasSpecial, player.specialCharges]).toEqual([true, 1]);
    stepWith(world, sim, press({}));
    expect(specialsIn(stepWith(world, sim, press({ special: true })))).toBe(1);
    expect([player.hasSpecial, player.specialCharges]).toEqual([false, 0]);
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
    // 技のボタンを 7 tick 押したまま倒れていた。
    shooter.actionHeld = tick(7);
    shooter.actionFired = false;
    const events = throwAndWait(world);

    const revived = events.find((e) => e.type === 'revived');
    expect(revived).toEqual({ type: 'revived', player: 0, replaced: 1, at: { x: 5.5, y: 3.5 } });
    expect(isAlive(shooter)).toBe(true);
    expect(shooter.position).toEqual({ x: 5.5, y: 3.5 });
    expect(shooter.hp).toBe(REVIVE_HP);
    expect(shooter.invulnerableUntil).toBeGreaterThan(world.now);
    expect(shooter.invulnerableUntil).toBeLessThanOrEqual(world.now + REVIVE_INVULNERABLE);
    // 技のボタンの押した長さは倒れたときのまま（原型の negiHit も触らない）。
    expect([shooter.actionHeld, shooter.actionFired]).toEqual([7, false]);
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

  it('同じ tick に撃った2本が同じ相手に同じ tick に届くと、番号の大きいほう（あとに撃った葱）の持ち主が戻る', () => {
    // 原型の updateNegis は葱の配列を後ろから順に処理する（L2292）。葱は入力の輪で番号の順に積む（L4333 → L2288）ので、
    // 同じ tick に撃った2本なら番号の大きいほうが先に進んで当たる（L2327）。先に撃った葱は、相手がもう外周に
    // いる（L2321）のと、戻った撃ち手が無敵な（L2325）のとで通り抜け、そのまま飛び続ける。
    const world = makeWorld(3, ['rabbit', 'elephant', 'mole']);
    clearBoard(world);
    const [early, target, late] = world.players as [PlayerState, PlayerState, PlayerState];
    const aim: Cell = { col: 5, row: 5 };
    // 上辺と左辺から、同じ道のり（帯の真ん中からマスの中央まで 5.81 マス）で届く位置。
    onLane(early, alongsFacing(aim)[0]);
    onLane(late, alongsFacing(aim)[3]);
    target.position = centerOf(aim);
    const sim = new Simulation();
    const fire = new Map<PlayerId, PlayerInput>([
      [early.id, press({ bomb: true })],
      [target.id, press({})],
      [late.id, press({ bomb: true })],
    ]);
    const thrown = sim.step(world, fire).filter((e) => e.type === 'leekThrown');
    expect(thrown.map((e) => e.type === 'leekThrown' && e.player)).toEqual([early.id, late.id]);

    const events: SimEvent[] = [];
    for (let i = 0; i < 100 && !events.some((e) => e.type === 'revived'); i += 1) {
      events.push(...stepWith(world, sim, press({})));
    }
    expect(events.find((e) => e.type === 'revived')).toMatchObject({ player: late.id, replaced: target.id });
    expect(early.life.kind).toBe('negibon');
    // 先に撃った葱は当たらずに飛び続けている。
    expect(world.actors.some((a) => a instanceof LeekActor && a.owner === early.id)).toBe(true);
  });

  it('射程を越えると落ちる。盤面の中央までは届かない', () => {
    const { world } = shootingRange(5);
    const events = throwAndWait(world);
    const stop = events.find((e) => e.type === 'leekStopped');
    expect(stop).toMatchObject({ by: 'range' });
    expect(stop?.type === 'leekStopped' && stop.cell.row).toBeLessThan(Math.floor(ROWS / 2));
  });
});

/**
 * 3:00 の設定。原型は 180 秒から update ごとに 1/60 を引き（L4288）、7200 回目の update で残りが 60 秒を切る
 * （59.99999999996）。この版の step は `now` が n のとき原型の n+1 回目の update に当たるので、境目は now=7199 の step。
 */
const THREE_MINUTES = secondsToTicks(180);
const LAST_OPEN_STEP = tick(7198);
const CLOSING_STEP = tick(7199);

/** その場に長く残る爆風を1マスに置く（倒すため）。 */
function blastOn(world: WorldState, cell: Cell): void {
  world.blasts.push({ id: world.ids.take(), cell, owner: 1, isCenter: true, remaining: tick(1000) });
}

describe('外周が閉じる', () => {
  it('残りが閉じる時刻を切ったら、その tick の最後に外周の全員が退場して、飛んでいる葱も消える（原型 3:00 は 7200 回目の update の最後）', () => {
    // 原型は update の最後の checkEnd の頭（L4405 → L4411 → L2359-2362）で閉じる。
    const world = makeWorld(3, ['rabbit', 'elephant', 'mole']);
    const sim = new Simulation();
    onLane(world.players[0]!, 5);
    onLane(world.players[2]!, 40);
    world.actors.push(new LeekActor({ x: 5.5, y: 0.5 }, 'down', 0));
    world.endsAt = THREE_MINUTES;
    world.now = LAST_OPEN_STEP;

    expect(stepWith(world, sim, press({})).some((e) => e.type === 'lanesClosed')).toBe(false);
    const closed = stepWith(world, sim, press({}));
    expect(closed).toContainEqual({ type: 'lanesClosed', players: [0, 2] });
    expect(world.players[0]!.life).toBe(OUT);
    expect(world.players[2]!.life).toBe(OUT);
    expect(world.actors.some((a) => a instanceof LeekActor)).toBe(false);
    // 2度目は出ない。
    expect(stepWith(world, sim, press({})).some((e) => e.type === 'lanesClosed')).toBe(false);
  });

  it('3:00 の境目の tick（now=7199 の step）に倒れたプレイヤーは外周へ回らず退場し、外周にほかにだれもいなければ lanesClosed が出ない', () => {
    // 原型の 7200 回目の update：倒れたプレイヤーの行き先（kill の L1700 → L2364）は、引いたあとの残り
    // 59.99999999996 で見るので退場。update の最後の negibonCutoff（L2362）は、外周にだれもいなければ何もしない。
    const world = makeWorld(3, ['rabbit', 'elephant']);
    clearBoard(world);
    world.endsAt = THREE_MINUTES;
    world.now = CLOSING_STEP;
    const player = world.players[0]!;
    player.hp = 2;
    blastOn(world, cellOf(player.position));

    const events = stepWith(world, new Simulation(), press({}));
    expect(events).toContainEqual(expect.objectContaining({ type: 'playerDown', target: 0 }));
    expect(player.life).toBe(OUT);
    expect(events.some((e) => e.type === 'lanesClosed')).toBe(false);
  });

  it('その1つ前の tick（now=7198 の step）に倒れたプレイヤーは外周へ回り、次の tick の最後に退場する', () => {
    // 原型の 7199 回目の update は残り 60.0166… なので外周へ回り、7200 回目の update の最後に閉じる。
    const world = makeWorld(3, ['rabbit', 'elephant']);
    clearBoard(world);
    world.endsAt = THREE_MINUTES;
    world.now = LAST_OPEN_STEP;
    const player = world.players[0]!;
    player.hp = 2;
    blastOn(world, cellOf(player.position));
    const sim = new Simulation();

    stepWith(world, sim, press({}));
    expect(player.life.kind).toBe('negibon');
    expect(stepWith(world, sim, press({}))).toContainEqual({ type: 'lanesClosed', players: [0] });
    expect(player.life).toBe(OUT);
  });

  it('閉じる tick の中でも、外周のプレイヤーは動いて撃ち、飛んでいる葱は当たって入れ替わる。当たった相手はその tick の最後に退場する', () => {
    // 原型の入力の輪（L4333-4338。外周のプレイヤーが動いて撃つ）と葱（L4346 → negiHit L2337-2349）は、
    // 外周を閉じる checkEnd（L4405）より前に回る。negiHit は時刻を見ない。
    const world = makeWorld(3, ['rabbit', 'elephant', 'mole']);
    clearBoard(world);
    world.endsAt = THREE_MINUTES;
    world.now = CLOSING_STEP;
    const [shooter, target, thrower] = world.players as [PlayerState, PlayerState, PlayerState];
    onLane(shooter, topAlongFor(9));
    onLane(thrower, topAlongFor(11));
    target.position = centerOf({ col: 5, row: 3 });
    // 次の tick に1歩進むと、相手の当たり枠（0.28）に入る葱。
    world.actors.push(new LeekActor({ x: 5.5, y: 3.2 }, 'down', shooter.id));

    const events = stepWith(world, new Simulation(), press({ bomb: true }), thrower.id);
    expect(events).toContainEqual(expect.objectContaining({ type: 'leekThrown', player: thrower.id }));
    expect(events).toContainEqual(expect.objectContaining({ type: 'revived', player: shooter.id, replaced: target.id }));
    expect(events).toContainEqual({ type: 'lanesClosed', players: [target.id, thrower.id] });
    expect(isAlive(shooter)).toBe(true);
    expect(target.life).toBe(OUT);
    expect(thrower.life).toBe(OUT);
    expect(world.actors.some((a) => a instanceof LeekActor)).toBe(false);
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
