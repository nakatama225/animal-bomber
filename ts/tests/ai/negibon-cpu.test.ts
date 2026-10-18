import { describe, expect, it } from 'vitest';

import type { CpuBehavior } from '../../src/ai/CpuBehavior.js';
import { CpuInputSource } from '../../src/ai/CpuInputSource.js';
import { CPU_LEVELS } from '../../src/ai/CpuLevel.js';
import type { CpuMemory } from '../../src/ai/CpuMemory.js';
import { DODGE_LEEK } from '../../src/ai/behaviors/DodgeLeek.js';
import { FLEE } from '../../src/ai/behaviors/Flee.js';
import { centerOf } from '../../src/domain/core/Coord.js';
import { secondsToTicks, tick } from '../../src/domain/core/Tick.js';
import type { SimEvent } from '../../src/domain/events/SimEvent.js';
import type { InputSource } from '../../src/domain/input/InputSource.js';
import { IdleInputSource, InputGatherer } from '../../src/domain/input/InputSource.js';
import { swapPlaces } from '../../src/domain/mutations/negibon.js';
import { alongsFacing, laneSpot } from '../../src/domain/negibon/lane.js';
import { LeekActor } from '../../src/domain/negibon/LeekActor.js';
import { placeBombAt } from '../../src/domain/mutations/bombs.js';
import { LANE_SPEED } from '../../src/domain/rules/negibon.js';
import { ALIVE } from '../../src/domain/state/Life.js';
import type { PlayerState } from '../../src/domain/state/PlayerState.js';
import type { WorldState } from '../../src/domain/state/WorldState.js';
import { Simulation } from '../../src/domain/systems/Simulation.js';
import { clearBoard, makeWorld } from '../helpers.js';

/** 上辺から `col` 列を撃てる、外周の位置。 */
function topAlongFor(col: number): number {
  return alongsFacing({ col, row: 1 })[0];
}

/** 外周に置く。すぐ撃てる。 */
function onLane(player: PlayerState, along: number): void {
  player.life = { kind: 'negibon', along, readyAt: tick(0) };
}

/** 外周の上の位置。外周にいなければ失敗させる。 */
function alongOf(player: PlayerState): number {
  if (player.life.kind !== 'negibon') throw new Error(`外周にいない: ${player.life.kind}`);
  return player.life.along;
}

/** 盤面を空にした2人の世界。プレイヤー0が CPU、プレイヤー1は動かない的。 */
function arena(): { world: WorldState; cpu: PlayerState; foe: PlayerState } {
  const world = makeWorld(3, ['rabbit', 'elephant']);
  clearBoard(world);
  return { world, cpu: world.players[0]!, foe: world.players[1]! };
}

/** 登録した操作の出どころで `ticks` 回進め、起きたことを tick ごとに返す。 */
function run(world: WorldState, sources: readonly InputSource[], ticks: number): SimEvent[][] {
  const gatherer = new InputGatherer();
  for (const source of sources) gatherer.add(source);
  const sim = new Simulation();
  const out: SimEvent[][] = [];
  for (let i = 0; i < ticks; i += 1) out.push(sim.step(world, gatherer.gather(world)));
  return out;
}

const cpuOf = (chain?: readonly CpuBehavior[]): CpuInputSource =>
  new CpuInputSource(0, CPU_LEVELS.hard, 1, chain);

/** 外周の CPU が進む向きを選び直す間隔（15 tick。原型は 16 フレームごと。1フレームの差は残している）。 */
const REAIM = secondsToTicks(0.25);

/**
 * 登録した操作の出どころで `ticks` 回進め、CPU（プレイヤー0）の外周の上の位置を tick ごとに返す。
 * 起きたことも返す。
 */
function trace(
  world: WorldState,
  sources: readonly InputSource[],
  ticks: number,
): { alongs: number[]; events: SimEvent[] } {
  const gatherer = new InputGatherer();
  for (const source of sources) gatherer.add(source);
  const sim = new Simulation();
  const alongs: number[] = [];
  const events: SimEvent[] = [];
  for (let i = 0; i < ticks; i += 1) {
    events.push(...sim.step(world, gatherer.gather(world)));
    alongs.push(alongOf(world.players[0]!));
  }
  return { alongs, events };
}

/*
 * 外周にいる CPU は、原型の cpuNegiUpdate（L2366-2424）と同じ動きにしてある。
 * 構えて撃つ 37 tick 目・選び直しの 15 tick は、原型（36 フレーム目・16 フレームごと）との1フレームの差を残している。
 */
describe('外周にいる CPU', () => {
  it('射線の上に相手がいれば、動かずに狙いを定めてから撃つ（原型 L2395-2398）', () => {
    const { world, cpu, foe } = arena();
    onLane(cpu, topAlongFor(5));
    foe.position = centerOf({ col: 5, row: 3 });
    const events = run(world, [cpuOf(), new IdleInputSource(1)], 120);

    const thrownAt = events.findIndex((tickEvents) => tickEvents.some((e) => e.type === 'leekThrown'));
    // 捉えた瞬間には撃たない。人間のように反応を遅らせる。
    expect(thrownAt).toBeGreaterThan(secondsToTicks(0.5));
    expect(thrownAt).toBeLessThan(secondsToTicks(1));
    expect(events.flat().some((e) => e.type === 'revived')).toBe(true);
  });

  it('間に柱があれば撃たない（原型 L2388）', () => {
    // 6 列目は2行目に柱がある。
    const { world, cpu, foe } = arena();
    onLane(cpu, topAlongFor(6));
    foe.position = centerOf({ col: 6, row: 3 });
    const events = run(world, [cpuOf(), new IdleInputSource(1)], 240);
    expect(events.flat().some((e) => e.type === 'leekThrown')).toBe(false);
  });

  it('間に爆弾があれば撃たない（原型 L2390）', () => {
    // 爆弾は葱を弾くので、撃っても無駄になる。
    const { world, cpu, foe } = arena();
    onLane(cpu, topAlongFor(5));
    foe.position = centerOf({ col: 5, row: 3 });
    placeBombAt(world, foe, { col: 5, row: 2 })!.fuse = tick(1000);
    const events = run(world, [cpuOf(), new IdleInputSource(1)], 240);
    expect(events.flat().some((e) => e.type === 'leekThrown')).toBe(false);
  });

  it('射程の外の相手には、射線に入っても撃たない（原型 L2380 の ahead<=NEGI_RANGE-1）', () => {
    // 5 列目の 11 行目は、どの辺からも射程の外。
    const { world, cpu, foe } = arena();
    onLane(cpu, topAlongFor(5));
    foe.position = centerOf({ col: 5, row: 11 });
    const events = run(world, [cpuOf(), new IdleInputSource(1)], 300).flat();
    expect(events.some((e) => e.type === 'leekThrown')).toBe(false);
  });

  it('射線に乗っているとみなす幅は 0.3。ずれ 0.29 なら当たらなくても撃ち、0.31 なら撃たない（原型 L2380。葱の当たりは 0.28）', () => {
    const shoot = (dx: number): SimEvent[] => {
      const { world, cpu, foe } = arena();
      onLane(cpu, topAlongFor(5));
      foe.position = { x: 5.5 + dx, y: 3.5 };
      return run(world, [cpuOf(), new IdleInputSource(1)], 120).flat();
    };
    const near = shoot(0.29);
    expect(near.some((e) => e.type === 'leekThrown')).toBe(true);
    expect(near.some((e) => e.type === 'revived')).toBe(false);
    expect(shoot(0.31).some((e) => e.type === 'leekThrown')).toBe(false);
  });

  it.each([
    {
      name: '無敵中',
      setup: (foe: PlayerState) => {
        foe.invulnerableUntil = tick(1000);
      },
    },
    {
      name: '葱が触れられない振る舞いの最中',
      setup: (foe: PlayerState) => {
        foe.action = {
          kind: 'probe',
          drivesMovement: true,
          damageCap: null,
          untouchable: true,
          canPlaceBomb: false,
          blocksButtons: false,
          sweepsItems: false,
          tick: () => ({ events: [], done: false }),
        };
      },
    },
    {
      name: 'とくぎで跳び上がっている最中',
      setup: (foe: PlayerState) => {
        foe.effects.add('leap', tick(1000), tick(1000));
      },
    },
  ])('「$name」の相手も狙って撃つ。葱は通り抜ける（原型 L2369 は盤面にいる全員を狙い、L2325 で葱が通り抜ける）', ({ setup }) => {
    // 撃つ間隔を無駄にするが、原型と同じにする。
    const { world, cpu, foe } = arena();
    onLane(cpu, topAlongFor(5));
    foe.position = centerOf({ col: 5, row: 3 });
    setup(foe);
    const events = run(world, [cpuOf(), new IdleInputSource(1)], 120).flat();
    expect(events.some((e) => e.type === 'leekThrown')).toBe(true);
    expect(events.some((e) => e.type === 'revived')).toBe(false);
  });

  it('射線に相手がいなければ、いちばん近い相手のマスに向き合う4辺のうち、外周を回っていちばん近い位置へ寄り、射線に乗れば撃つ（原型 L2403-2417）', () => {
    // 上辺の 6 列目から 9 列目の相手へ。上辺の位置（右へ 3）が、左辺の位置（左へ 8）より近い。
    const { world, cpu, foe } = arena();
    onLane(cpu, topAlongFor(6));
    foe.position = centerOf({ col: 9, row: 3 });
    const events = run(world, [cpuOf(), new IdleInputSource(1)], 600).flat();
    expect(events.find((e) => e.type === 'revived')).toMatchObject({ player: 0, replaced: 1 });
  });

  it('外周の道のりは1周をまたいで測る（原型 L2414-2420）', () => {
    // 左辺の上の端（71.5）から、1 列目の相手へ。上辺の位置 0 は、またげば 0.5、左辺の位置 69 は 2.5。
    const { world, cpu, foe } = arena();
    onLane(cpu, 71.5);
    foe.position = centerOf({ col: 1, row: 3 });
    const events = run(world, [cpuOf(), new IdleInputSource(1)], 200).flat();
    expect(events.some((e) => e.type === 'revived')).toBe(true);
  });

  it.each([
    {
      name: '射程の外',
      // 上辺の 3 列目から 9 列目の相手へ。左辺の位置 69（左へ 5）が、上辺の位置 8（右へ 6）より近い。
      // 左辺から 9 列目までは射程の外。
      start: topAlongFor(3),
      foeAt: { col: 9, row: 3 },
      target: alongsFacing({ col: 9, row: 3 })[3],
    },
    {
      name: '柱の陰',
      // 上辺の 6 列目から 4 列目の相手へ。上辺の位置 3（左へ 2）がいちばん近いが、4 列目は2行目に柱がある。
      start: topAlongFor(6),
      foeAt: { col: 4, row: 3 },
      target: topAlongFor(4),
    },
  ])('いちばん近い辺が「$name」でも、射程や陰を見ずにそこへ寄り、撃たずに行き来する（原型 L2410-2417）', ({ start, foeAt, target }) => {
    // 原型も、残り60秒で外周が閉じるか、相手が別のマスへ移るまで、その辺で行ったり来たりする。
    const { world, cpu, foe } = arena();
    onLane(cpu, start);
    foe.position = centerOf(foeAt);
    const { alongs, events } = trace(world, [cpuOf(), new IdleInputSource(1)], 1200);
    expect(events.some((e) => e.type === 'leekThrown')).toBe(false);
    const settled = alongs.slice(120);
    const swing = REAIM * LANE_SPEED;
    for (const along of settled) expect(Math.abs(along - target)).toBeLessThan(swing);
    // 止まらずに、選び直し1回ぶんの幅で動き続ける。
    expect(Math.max(...settled) - Math.min(...settled)).toBeCloseTo(swing);
  });

  it('向きは選び直しのときだけ決め、次の選び直しまで同じ向きで進む。寄る先を行き過ぎては戻る（原型 L2418-2423）', () => {
    // 11 列目の 8 行目は、どの辺からも射程の外。上辺の位置 10 が寄る先になる。そこから 1 だけ先の位置から始める。
    const { world, cpu, foe } = arena();
    const target = topAlongFor(11);
    onLane(cpu, target + 1);
    foe.position = centerOf({ col: 11, row: 8 });
    const { alongs } = trace(world, [cpuOf(), new IdleInputSource(1)], 4 * REAIM);
    const swing = REAIM * LANE_SPEED;
    // 選び直しの間（15 tick）は同じ向きに進み続け、寄る先を 0.375 行き過ぎて戻る。
    expect(alongs[REAIM - 1]).toBeCloseTo(target + 1 - swing);
    expect(alongs[2 * REAIM - 1]).toBeCloseTo(target + 1);
    expect(alongs[3 * REAIM - 1]).toBeCloseTo(target + 1 - swing);
  });

  it('選び直した瞬間に寄る先までの残りが 0.25 未満なら止まる（原型 L2421）', () => {
    const { world, cpu, foe } = arena();
    const target = topAlongFor(11);
    onLane(cpu, target + 0.2);
    foe.position = centerOf({ col: 11, row: 8 });
    const { alongs } = trace(world, [cpuOf(), new IdleInputSource(1)], 4 * REAIM);
    // 動かない（外周の位置を 0〜1周に収める計算の端数だけが付く）。
    for (const along of alongs) expect(along).toBeCloseTo(target + 0.2, 9);
  });

  it('外周を進む向きは、人間の操作と同じ変換で押す（下辺でも逆に進まない）', () => {
    // 下辺は、外周の位置が左へ増える。表を別に持つと、人間と CPU で食い違う。
    const { world, cpu, foe } = arena();
    const bottom = alongsFacing({ col: 15, row: 15 })[2];
    onLane(cpu, bottom);
    foe.position = centerOf({ col: 9, row: 13 });
    const startX = laneSpot(bottom).position.x;
    run(world, [cpuOf(), new IdleInputSource(1)], 30);
    const lane = cpu.life.kind === 'negibon' ? cpu.life : null;
    expect(lane).not.toBeNull();
    expect(laneSpot(lane!.along).side).toBe('bottom');
    expect(laneSpot(lane!.along).position.x).toBeLessThan(startX);
  });
});

describe('盤面にいる CPU と葱', () => {
  /** 外周のプレイヤー1が、盤面の CPU（プレイヤー0）の列へ葱を撃った直後の世界。 */
  function leekIncoming(): { world: WorldState; cpu: PlayerState } {
    const world = makeWorld(3, ['rabbit', 'elephant']);
    clearBoard(world);
    const cpu = world.players[0]!;
    const shooter = world.players[1]!;
    cpu.position = centerOf({ col: 5, row: 5 });
    onLane(shooter, topAlongFor(5));
    world.actors.push(new LeekActor(laneSpot(topAlongFor(5)).position, 'down', 1));
    return { world, cpu };
  }

  it('葱をよける規則が無ければ、飛んでくる葱に当たる', () => {
    // 次の確認が「もともと当たらない場面」で通っていないことの対照。
    const { world, cpu } = leekIncoming();
    const events = run(world, [cpuOf([FLEE]), new IdleInputSource(1)], 120);
    expect(events.flat().some((e) => e.type === 'revived')).toBe(true);
    expect(cpu.life.kind).toBe('negibon');
  });

  it('規則を1つ足すと、飛んでくる葱の列から直角に外れる', () => {
    const { world, cpu } = leekIncoming();
    const events = run(world, [cpuOf([FLEE, DODGE_LEEK]), new IdleInputSource(1)], 120);
    expect(events.flat().some((e) => e.type === 'revived')).toBe(false);
    expect(cpu.life.kind).toBe('alive');
    expect(Math.abs(cpu.position.x - 5.5)).toBeGreaterThan(0.5);
  });

  it('射線から離れる側へよける。近づく側へよけて、外れるはずの葱に当たらない', () => {
    // 射線の左に立っているのに右へよけると、自分から射線を横切る。
    const { world, cpu } = leekIncoming();
    const leek = world.actors[0] as LeekActor;
    world.actors = [new LeekActor({ x: 5.9, y: leek.position.y }, 'down', 1)];
    const events = run(world, [cpuOf([FLEE, DODGE_LEEK]), new IdleInputSource(1)], 120).flat();
    expect(events.some((e) => e.type === 'revived')).toBe(false);
    expect(cpu.position.x).toBeLessThan(5.5);
  });

  it('当たらない位置にいるなら、離れる側が塞がっていても射線を横切らない', () => {
    // マスの中央に立ち、葱は 0.4 マス右を飛ぶ。そのままなら外れる。左のマスは塞がっている。
    const { world, cpu } = leekIncoming();
    const leek = world.actors[0] as LeekActor;
    world.actors = [new LeekActor({ x: 5.9, y: leek.position.y }, 'down', 1)];
    world.board.set({ col: 4, row: 5 }, 'soft');
    const events = run(world, [cpuOf([FLEE, DODGE_LEEK]), new IdleInputSource(1)], 120).flat();
    expect(events.some((e) => e.type === 'revived')).toBe(false);
    expect(cpu.position.x).toBeCloseTo(5.5);
  });

  it('爆風の届くマスへはよけない', () => {
    // 右の (6,5) は、(7,5) の火力1の爆弾の爆風が届く。立っている (5,5) には届かない。左へよける。
    const { world, cpu } = leekIncoming();
    world.players[1]!.power = 1;
    placeBombAt(world, world.players[1]!, { col: 7, row: 5 })!.fuse = tick(1000);
    const events = run(world, [cpuOf([FLEE, DODGE_LEEK]), new IdleInputSource(1)], 120).flat();
    expect(events.some((e) => e.type === 'revived')).toBe(false);
    expect(cpu.position.x).toBeLessThan(5.5);
  });

  it('標準の並びにも、葱をよける規則が入っている', () => {
    const { world, cpu } = leekIncoming();
    run(world, [cpuOf(), new IdleInputSource(1)], 120);
    expect(cpu.life.kind).toBe('alive');
  });
});

/** CPU（プレイヤー0）だけを動かし、爆弾を1つ置いた直後まで進める。置き直さない記憶が入った CPU を返す。 */
function afterFirstBomb(world: WorldState): CpuInputSource {
  const source = cpuOf();
  const sim = new Simulation();
  for (let i = 0; i < 600 && source.memory.lastBomb === null; i += 1) {
    sim.step(world, new Map([[0, source.next(world)]]));
  }
  expect(source.memory.lastBomb).not.toBeNull();
  return source;
}

describe('外周から戻った CPU', () => {
  it('倒れる前の記憶を持ち越す。作り直さないので、判断の間隔の揺らぎも引き直さない（原型の negiHit L2337-2356 は p.ai に触らない）', () => {
    // 原型が CPU の記憶を作り直すのは、ラウンドの始まり（L4191-4192）と作るとき（L1210）だけ。
    const world = makeWorld(3, ['rabbit', 'elephant']);
    const [cpu, foe] = world.players as [PlayerState, PlayerState];
    const source = afterFirstBomb(world);
    const before = source.memory;
    const { jitter, lastBomb } = before;

    onLane(cpu, 0);
    source.next(world);
    swapPlaces(world, cpu, foe);
    source.next(world);
    expect(source.memory).toBe(before);
    expect(source.memory.jitter).toBe(jitter);
    expect(source.memory.lastBomb).toEqual(lastBomb);
  });

  it('戻った直後は、考え直すまで倒れる前の経路の先のマスへ1軸ずつ歩く（隣のマスでなくても。原型 L1971-1984）', () => {
    // 戻ると当てた相手の位置へ移る。原型の経路追従は、先頭のマスが隣かどうかを見ずに、そのマスの中央へ寄る。
    const world = makeWorld(3, ['rabbit', 'elephant']);
    clearBoard(world);
    const [cpu, foe] = world.players as [PlayerState, PlayerState];
    const source = cpuOf();
    source.next(world);
    const memory = source.memory as CpuMemory;
    memory.path = [{ col: 9, row: 9 }];
    memory.thinkIn = 99;

    onLane(cpu, 0);
    source.next(world);
    foe.position = centerOf({ col: 3, row: 7 });
    swapPlaces(world, cpu, foe);
    // 横に 6、縦に 2 離れている。両方 0.06 より離れているので、離れているほうの横だけを押す。
    expect(source.next(world)).toMatchObject({ right: true, down: false, up: false, left: false });
    expect(source.memory.path).toEqual([{ col: 9, row: 9 }]);
  });
});

describe('同じラウンドの2度目の外周（原型の toNegibon L2268 は構えの溜め negiLock だけを 0 にする）', () => {
  it('構えの溜めは 0 に戻るので、射線に乗った相手には、外周へ回ってから 37 tick 目に撃つ', () => {
    // 1度目の外周で 20 tick 構えたところで盤面へ戻す。溜めが残っていれば 17 tick 目に撃ってしまう。
    const { world, cpu, foe } = arena();
    const source = cpuOf();
    const gatherer = new InputGatherer();
    gatherer.add(source);
    gatherer.add(new IdleInputSource(1));
    const sim = new Simulation();
    onLane(cpu, topAlongFor(5));
    foe.position = centerOf({ col: 5, row: 3 });
    for (let i = 0; i < 20; i += 1) sim.step(world, gatherer.gather(world));

    cpu.life = ALIVE;
    source.next(world);
    onLane(cpu, topAlongFor(5));
    let thrownAt: number | null = null;
    for (let i = 1; i <= 60 && thrownAt === null; i += 1) {
      if (sim.step(world, gatherer.gather(world)).some((e) => e.type === 'leekThrown')) thrownAt = i;
    }
    expect(thrownAt).toBe(37);
  });

  it('選び直しの残りと向きは持ち越すので、残りがあるうちは前の外周で選んだ向きへ動く（原型の negiAim・negiDir）', () => {
    // 1度目：上辺の 6 列目から、9 列目の相手へ（右へ。上辺の位置 8 が左辺の位置 69 より近い）。5 tick 動いたところで盤面へ戻す。
    // 2度目：上辺の 6 列目から。相手は 3 列目へ移っているので、選び直せば左へ向かう。
    const { world, cpu, foe } = arena();
    const source = cpuOf();
    const gatherer = new InputGatherer();
    gatherer.add(source);
    gatherer.add(new IdleInputSource(1));
    const sim = new Simulation();
    onLane(cpu, topAlongFor(6));
    foe.position = centerOf({ col: 9, row: 3 });
    for (let i = 0; i < 5; i += 1) sim.step(world, gatherer.gather(world));

    cpu.life = ALIVE;
    source.next(world);
    const start = topAlongFor(6);
    onLane(cpu, start);
    foe.position = centerOf({ col: 3, row: 3 });
    for (let i = 0; i < 3; i += 1) sim.step(world, gatherer.gather(world));
    expect(alongOf(cpu)).toBeGreaterThan(start);
  });
});
