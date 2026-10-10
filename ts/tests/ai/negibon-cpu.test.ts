import { describe, expect, it } from 'vitest';

import type { CpuBehavior } from '../../src/ai/CpuBehavior.js';
import { CpuInputSource } from '../../src/ai/CpuInputSource.js';
import { CPU_LEVELS } from '../../src/ai/CpuLevel.js';
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

describe('外周にいる CPU', () => {
  it('射線の上に相手がいれば、動かずに狙いを定めてから撃つ', () => {
    const { world, cpu, foe } = arena();
    onLane(cpu, topAlongFor(5));
    foe.position = centerOf({ col: 5, row: 3 });
    const events = run(world, [cpuOf(), new IdleInputSource(1)], 120);

    const thrownAt = events.findIndex((tickEvents) => tickEvents.some((e) => e.type === 'leekThrown'));
    // 捉えた瞬間には撃たない。人のように反応を遅らせる。
    expect(thrownAt).toBeGreaterThan(secondsToTicks(0.5));
    expect(thrownAt).toBeLessThan(secondsToTicks(1));
    expect(events.flat().some((e) => e.type === 'revived')).toBe(true);
  });

  it('間に柱があれば撃たない', () => {
    // 6 列目は2行目に柱がある。
    const { world, cpu, foe } = arena();
    onLane(cpu, topAlongFor(6));
    foe.position = centerOf({ col: 6, row: 3 });
    const events = run(world, [cpuOf(), new IdleInputSource(1)], 240);
    expect(events.flat().some((e) => e.type === 'leekThrown')).toBe(false);
  });

  it('間に爆弾があれば撃たない', () => {
    // 爆弾は葱を弾くので、撃っても無駄になる。
    const { world, cpu, foe } = arena();
    onLane(cpu, topAlongFor(5));
    foe.position = centerOf({ col: 5, row: 3 });
    placeBombAt(world, foe, { col: 5, row: 2 })!.fuse = tick(1000);
    const events = run(world, [cpuOf(), new IdleInputSource(1)], 240);
    expect(events.flat().some((e) => e.type === 'leekThrown')).toBe(false);
  });

  it('射線に相手がいなければ、いちばん近い相手を撃てる位置へ外周を回って寄り、撃つ', () => {
    const { world, cpu, foe } = arena();
    onLane(cpu, topAlongFor(3));
    foe.position = centerOf({ col: 9, row: 3 });
    const events = run(world, [cpuOf(), new IdleInputSource(1)], 600);
    const revived = events.flat().find((e) => e.type === 'revived');
    expect(revived).toMatchObject({ player: 0, replaced: 1 });
  });

  it.each([
    { from: 3, dx: 0.14 },
    { from: 3, dx: 0.3 },
    { from: 15, dx: -0.14 },
    { from: 15, dx: -0.3 },
    { from: 3, dx: -0.3 },
  ])('マスの中央からずれて立つ相手にも、寄って1発で当てる（$from 列から、ずれ $dx）', ({ from, dx }) => {
    // マスの中央へ寄ると、中央の手前で止まり、反対側へずれて立つ相手が射線に入らない。
    const { world, cpu, foe } = arena();
    onLane(cpu, topAlongFor(from));
    foe.position = { x: 9.5 + dx, y: 3.5 };
    const events = run(world, [cpuOf(), new IdleInputSource(1)], 900).flat();
    expect(events.find((e) => e.type === 'revived')).toMatchObject({ player: 0, replaced: 1 });
    // 当たらない位置から撃たない。
    expect(events.filter((e) => e.type === 'leekThrown')).toHaveLength(1);
  });

  it('止まっている相手には、どこから寄っても当たる位置からしか撃たない', () => {
    // 射線の幅が当たり判定より広いと、当たらない位置で止まって撃ち続ける。
    // 寄る位置の見積もりが撃つ判定と食い違うと、着いたのに撃たずに止まる。
    // 相手の立ち位置（マスの中央からのずれ）と、寄り始める位置を組み合わせて確かめる。
    for (const dx of [-0.3, -0.2, -0.14, 0, 0.14, 0.2, 0.3]) {
      for (const from of [1, 5, 9, 13, 17, 21]) {
        const { world, cpu, foe } = arena();
        onLane(cpu, topAlongFor(from));
        foe.position = { x: 9.5 + dx, y: 3.5 };
        const events = run(world, [cpuOf(), new IdleInputSource(1)], 900).flat();
        const label = `ずれ ${dx}・${from} 列から`;
        expect(events.some((e) => e.type === 'revived'), label).toBe(true);
        expect(events.filter((e) => e.type === 'leekThrown'), label).toHaveLength(1);
      }
    }
  });

  it.each([
    { name: '左上の隅で外壁に寄る', at: { x: 1.36, y: 1.5 }, from: [topAlongFor(3), 60] },
    { name: '右上の隅で外壁に寄る', at: { x: 21.64, y: 1.5 }, from: [topAlongFor(4), 30] },
    { name: '右下の隅で外壁に寄る', at: { x: 21.64, y: 15.5 }, from: [30, 45] },
    { name: '左下の隅で外壁に寄る', at: { x: 1.36, y: 15.5 }, from: [45, 60] },
    { name: '柱の列の端に立つ', at: { x: 10.05, y: 3.5 }, from: [topAlongFor(14), topAlongFor(2)] },
    { name: '柱の列の反対の端に立つ', at: { x: 9.95, y: 3.5 }, from: [topAlongFor(14), topAlongFor(2)] },
  ])('相手が「$name」ときも、撃てる位置を見つけて当てる', ({ at, from }) => {
    // 外壁に寄ると撃てる位置は辺の始まりにしか無く、柱の列の端では隣の列からしか撃てない。
    for (const start of from) {
      const { world, cpu, foe } = arena();
      onLane(cpu, start);
      foe.position = { ...at };
      const events = run(world, [cpuOf(), new IdleInputSource(1)], 1500).flat();
      expect(events.some((e) => e.type === 'revived'), `${start} から`).toBe(true);
    }
  });

  it('近くても1 tick で飛び越えてしまう狭い位置には寄らず、少し遠くても撃てる位置へ回る', () => {
    // 相手は柱のある 4 列目の左の端に立つ。上辺からは 3 列目の端の、ごく狭い位置からしか
    // 撃てない。そこへ寄ると飛び越えて、柱の列で止まったまま撃てなくなる。左辺からは撃てる。
    const { world, cpu, foe } = arena();
    onLane(cpu, topAlongFor(6));
    foe.position = { x: 4.2, y: 3.5 };
    const events = run(world, [cpuOf(), new IdleInputSource(1)], 900).flat();
    expect(events.some((e) => e.type === 'revived')).toBe(true);
  });

  it('外周の1周をまたぐほうが近ければ、またいで寄る', () => {
    // 左辺の上の端から、上辺の左寄りの相手へ。またがずに回ると 65 マスかかる。
    const { world, cpu, foe } = arena();
    onLane(cpu, 71.5);
    foe.position = centerOf({ col: 7, row: 1 });
    const events = run(world, [cpuOf(), new IdleInputSource(1)], 200).flat();
    expect(events.some((e) => e.type === 'revived')).toBe(true);
  });

  it('射程の外の相手には、射線に入っても撃たない', () => {
    // 5 列目の 11 行目は、どの辺からも射程の外。
    const { world, cpu, foe } = arena();
    onLane(cpu, topAlongFor(5));
    foe.position = centerOf({ col: 5, row: 11 });
    const events = run(world, [cpuOf(), new IdleInputSource(1)], 300).flat();
    expect(events.some((e) => e.type === 'leekThrown')).toBe(false);
  });

  it('葱が触れられない技の最中の相手は狙わない', () => {
    const { world, cpu, foe } = arena();
    onLane(cpu, topAlongFor(5));
    foe.position = centerOf({ col: 5, row: 3 });
    foe.action = {
      kind: 'probe',
      drivesMovement: true,
      damageCap: null,
      untouchable: true,
      canPlaceBomb: false,
      sweepsItems: false,
      tick: () => ({ events: [], done: false }),
    };
    const events = run(world, [cpuOf(), new IdleInputSource(1)], 300).flat();
    expect(events.some((e) => e.type === 'leekThrown')).toBe(false);
  });

  it('柱の陰になる位置には寄らず、撃てる辺へ回る', () => {
    // 4 列目は2行目に柱がある。上辺からは撃てないので、3 行目を撃てる左辺へ回る。
    const { world, cpu, foe } = arena();
    onLane(cpu, topAlongFor(6));
    foe.position = centerOf({ col: 4, row: 3 });
    const events = run(world, [cpuOf(), new IdleInputSource(1)], 1200).flat();
    expect(events.find((e) => e.type === 'revived')).toMatchObject({ player: 0, replaced: 1 });
  });

  it('無敵中の相手は狙わない。葱は通り抜けるので、撃つ間隔を無駄にする', () => {
    const { world, cpu, foe } = arena();
    onLane(cpu, topAlongFor(5));
    foe.position = centerOf({ col: 5, row: 3 });
    foe.invulnerableUntil = tick(1000);
    const events = run(world, [cpuOf(), new IdleInputSource(1)], 300).flat();
    expect(events.some((e) => e.type === 'leekThrown')).toBe(false);
  });

  it('外周を進む向きは、人の操作と同じ変換で押す（下辺でも逆に進まない）', () => {
    // 下辺は、外周の位置が左へ増える。表を別に持つと、人と CPU で食い違う。
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

describe('外周から戻った CPU', () => {
  it('倒れる前の記憶を捨てる', () => {
    // 戻ると当てた相手の位置へ移るので、倒れる前に立てた道筋は使えない。
    const world = makeWorld(3, ['rabbit', 'elephant']);
    const source = cpuOf();
    const sim = new Simulation();
    const [cpu, foe] = world.players as [PlayerState, PlayerState];
    for (let i = 0; i < 600 && source.memory.lastBomb === null; i += 1) {
      sim.step(world, new Map([[0, source.next(world)]]));
    }
    expect(source.memory.lastBomb).not.toBeNull();

    onLane(cpu, 0);
    source.next(world);
    swapPlaces(world, cpu, foe);
    source.next(world);
    expect(source.memory.lastBomb).toBeNull();
  });
});
