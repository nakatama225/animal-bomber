import { describe, expect, it } from 'vitest';

import { FoxfireActor } from '../../src/domain/abilities/fox/FoxfireActor.js';
import { SlimeBombActor } from '../../src/domain/abilities/frog/SlimeBombActor.js';
import { PitActor } from '../../src/domain/abilities/mole/PitAction.js';
import { ScatteredActor } from '../../src/domain/abilities/rabbit/ScatterAction.js';
import type { WorldActor } from '../../src/domain/abilities/WorldActor.js';
import { centerOf } from '../../src/domain/core/Coord.js';
import { tick } from '../../src/domain/core/Tick.js';
import type { SimEvent } from '../../src/domain/events/SimEvent.js';
import { IDLE_INPUT } from '../../src/domain/input/PlayerInput.js';
import { placeBombAt } from '../../src/domain/mutations/bombs.js';
import { detonate } from '../../src/domain/mutations/explode.js';
import { enterSuddenDeath } from '../../src/domain/mutations/suddenDeath.js';
import { LeekActor } from '../../src/domain/negibon/LeekActor.js';
import { ITEM_DEFINITIONS } from '../../src/domain/rules/items.js';
import { BLAST_DURATION, BOMB_FUSE } from '../../src/domain/rules/tuning.js';
import type { Blast, Bomb } from '../../src/domain/state/Bomb.js';
import type { Tile } from '../../src/domain/state/Board.js';
import type { WorldState } from '../../src/domain/state/WorldState.js';
import { Simulation } from '../../src/domain/systems/Simulation.js';
import { CosmeticRng } from '../../src/presentation/CosmeticRng.js';
import { drawAirActor, drawGroundActor } from '../../src/presentation/render/actors.js';
import { drawTile } from '../../src/presentation/render/board.js';
import { drawBlast, drawBomb } from '../../src/presentation/render/bombs.js';
import { ParticleField } from '../../src/presentation/render/ParticleField.js';
import type { Frame } from '../../src/presentation/render/Frame.js';
import { drawItem } from '../../src/presentation/render/items.js';
import { layoutFor, screenX } from '../../src/presentation/render/Layout.js';
import { clearBoard, makeWorld } from '../helpers.js';
import { fakeCanvas, type FakeCanvas } from './fakeCanvas.js';

/**
 * 盤面に置かれるものの描画と、粒子・画面の揺れ。
 *
 * 通し検査（renderer.test.ts）は試合で実際に現れたものしか通らない。ここでは
 * 種類ごと・段階ごとに1つずつ描き、どれも例外を出さずに描けることと、
 * 見せてはいけないもの（落とし穴）を描かないことを確かめる。
 */

function frameOn(canvas: FakeCanvas, time = 0.5): Frame {
  return { g: canvas.context, layout: layoutFor(920, 680), time, cosmetic: new CosmeticRng() };
}

function count(canvas: FakeCanvas, name: string): number {
  return canvas.calls.get(name) ?? 0;
}

function bombWithFuse(fuse: number): Bomb {
  return { id: 1 as Bomb['id'], cell: { col: 3, row: 3 }, owner: 0, power: 2, fuse: tick(fuse), passThrough: new Set(), chained: false };
}

function blastWithRemaining(remaining: number): Blast {
  return { id: 2 as Blast['id'], cell: { col: 3, row: 3 }, owner: 0, isCenter: true, remaining: tick(remaining) };
}

/** 粒子を描いたときに呼ばれた、塗る命令の数。0 なら何も出ていない。 */
function paintedParticles(field: ParticleField): number {
  const canvas = fakeCanvas();
  field.draw(frameOn(canvas));
  return count(canvas, 'fillRect') + count(canvas, 'fillText');
}

/** 盤面を結びつけたうえで、自律物を足して1 tick ぶん観察させる。 */
function observeNew(field: ParticleField, world: WorldState, actor: WorldActor): void {
  field.onEvents([], world);
  world.actors.push(actor);
  field.onEvents([], world);
}

describe('盤面のマス', () => {
  it.each<Tile>(['empty', 'hard', 'soft'])('%s を市松のどちらのマスでも描ける', (tile) => {
    for (const cell of [{ col: 2, row: 2 }, { col: 3, row: 2 }]) {
      const canvas = fakeCanvas();
      drawTile(frameOn(canvas), tile, cell);
      expect(count(canvas, 'fillRect')).toBeGreaterThan(0);
    }
  });
});

describe('アイテム', () => {
  it.each(ITEM_DEFINITIONS.map((definition) => definition.kind))('%s を描ける', (kind) => {
    const canvas = fakeCanvas();
    drawItem(frameOn(canvas), { id: 1 as never, cell: { col: 4, row: 5 }, kind });
    expect(count(canvas, 'fillText')).toBe(1);
    expect(count(canvas, 'stroke')).toBeGreaterThan(0);
  });
});

describe('爆弾と爆風', () => {
  it('脈打ちの大きさは導火線の残りで決まり、ラウンドの経過時間に左右されない', () => {
    // ラウンドの経過時間から位相を作ると、経過時間が長いほど1 tick ごとの位相の飛びが
    // 大きくなり、10 秒を過ぎたあたりから脈打ちがばらばらに跳ねる（原型の不具合）。
    const scaleAt = (time: number): readonly unknown[] => {
      const canvas = fakeCanvas();
      drawBomb(frameOn(canvas, time), bombWithFuse(BOMB_FUSE * 0.4));
      return canvas.log.find((call) => call.name === 'scale')?.args ?? [];
    };
    expect(scaleAt(1)).toEqual(scaleAt(97.3));
  });

  it.each([BOMB_FUSE, BOMB_FUSE * 0.5, BOMB_FUSE * 0.2, 1, 0])('導火線の残り %d tick の爆弾を描ける', (fuse) => {
    const canvas = fakeCanvas();
    drawBomb(frameOn(canvas), bombWithFuse(fuse));
    expect(count(canvas, 'arc')).toBeGreaterThanOrEqual(3);
  });

  it('爆発の直前は、置いた直後より多く重ね塗りする（赤い光と熱）', () => {
    const fresh = fakeCanvas();
    drawBomb(frameOn(fresh), bombWithFuse(BOMB_FUSE));
    const late = fakeCanvas();
    drawBomb(frameOn(late), bombWithFuse(1));
    expect(count(late, 'arc')).toBeGreaterThan(count(fresh, 'arc'));
  });

  it.each([BLAST_DURATION, Math.floor(BLAST_DURATION / 2), 1, 0])('残り %d tick の爆風を描ける', (remaining) => {
    const canvas = fakeCanvas();
    drawBlast(frameOn(canvas), blastWithRemaining(remaining));
    expect(count(canvas, 'fillRect')).toBe(3);
  });
});

describe('自律物', () => {
  const world = makeWorld();
  const owner = world.players[0];
  if (owner === undefined) throw new Error('プレイヤーがいない');

  const cases: { name: string; actor: WorldActor; ground: boolean; air: boolean }[] = [
    { name: '撒かれた障害物', actor: new ScatteredActor({ col: 5, row: 5 }, 0), ground: true, air: false },
    { name: '落とし穴', actor: new PitActor({ col: 5, row: 5 }, 0), ground: false, air: false },
    { name: '追いかける炎', actor: new FoxfireActor({ x: 5.5, y: 5.5 }, 0), ground: false, air: true },
    { name: '跳ね回る爆弾', actor: new SlimeBombActor({ col: 5, row: 5 }, owner, 6), ground: false, air: true },
    { name: '飛んでいる葱', actor: new LeekActor({ x: 5.5, y: 5.5 }, 'down', 0), ground: false, air: true },
  ];

  it.each(cases)('$name は描くべき層にだけ描かれ、状態は変わらない', ({ actor, ground, air }) => {
    const before = actor.encode();
    const below = fakeCanvas();
    drawGroundActor(frameOn(below), actor);
    const above = fakeCanvas();
    drawAirActor(frameOn(above), actor);
    expect(below.calls.size > 0).toBe(ground);
    expect(above.calls.size > 0).toBe(air);
    expect(actor.encode()).toBe(before);
  });

  it('跳ね回る爆弾は、着地からの時間が進んでも描け、爆発が近いと輪を足す', () => {
    const calm = new SlimeBombActor({ col: 5, row: 5 }, owner, 6);
    const warned = new SlimeBombActor({ col: 5, row: 5 }, owner, 1);
    for (let i = 0; i < 12; i += 1) {
      calm.tick(world);
      warned.tick(world);
    }
    const a = fakeCanvas();
    drawAirActor(frameOn(a), calm);
    const b = fakeCanvas();
    drawAirActor(frameOn(b), warned);
    expect(count(b, 'ellipse')).toBe(count(a, 'ellipse') + 1);
  });

  it('撒かれた障害物は、消える間際でも描ける', () => {
    const actor = new ScatteredActor({ col: 5, row: 5 }, 0);
    const empty = makeWorld();
    for (let i = 0; i < 3590; i += 1) actor.tick(empty);
    const canvas = fakeCanvas();
    drawGroundActor(frameOn(canvas, 1.23), actor);
    expect(count(canvas, 'fillText')).toBe(1);
  });
});

describe('粒子と画面の揺れ', () => {
  /** 壊せるブロックの隣で爆弾を1つ爆発させ、ルールの層が返すイベントを得る。 */
  function realExplosion(world: WorldState): SimEvent[] {
    const player = world.players[0];
    if (player === undefined) throw new Error('プレイヤーがいない');
    world.board.set({ col: 1, row: 4 }, 'soft');
    const bomb = placeBombAt(world, player, { col: 1, row: 3 });
    if (bomb === undefined) throw new Error('爆弾を置けない');
    const result = detonate(world, bomb);
    return [{ type: 'exploded', cell: bomb.cell, owner: bomb.owner, chained: result.chained }, ...result.events];
  }

  it('爆発で粒子が出て、時間が経てばすべて消える', () => {
    const world = makeWorld();
    const field = new ParticleField(new CosmeticRng());
    const events = realExplosion(world);
    expect(events.some((event) => event.type === 'blockDestroyed')).toBe(true);

    field.onEvents(events, world);
    field.step();
    expect(paintedParticles(field)).toBeGreaterThan(0);

    for (let i = 0; i < 120; i += 1) field.step();
    expect(paintedParticles(field)).toBe(0);
  });

  it('画面の揺れは爆発で上がり、その後は増えずに 0 まで収まる', () => {
    const world = makeWorld();
    const field = new ParticleField(new CosmeticRng());
    expect(field.shake).toBe(0);

    field.onEvents(realExplosion(world), world);
    let last = field.shake;
    expect(last).toBeGreaterThan(0);
    for (let i = 0; i < 60; i += 1) {
      field.step();
      expect(field.shake).toBeLessThanOrEqual(last);
      last = field.shake;
    }
    expect(field.shake).toBe(0);
  });

  it('倒れたときは、回りながら浮かぶ顔を出す', () => {
    const world = makeWorld();
    const field = new ParticleField(new CosmeticRng());
    field.onEvents([{ type: 'playerDown', target: 1, by: 0, at: { x: 5.5, y: 5.5 } }], world);
    const canvas = fakeCanvas();
    field.draw(frameOn(canvas));
    expect(count(canvas, 'rotate')).toBe(1);
  });

  it('倒れた顔は、プレイヤーのいまの位置ではなく倒れた位置に出す', () => {
    // 同じ tick に延長戦へ入ると、受け取る頃には開始位置へ移っている。
    const world = makeWorld();
    const layout = layoutFor(920, 680);
    world.players[1]!.position = { x: 20.5, y: 14.5 };
    const field = new ParticleField(new CosmeticRng());
    field.onEvents([{ type: 'playerDown', target: 1, by: 0, at: { x: 1.5, y: 1.5 } }], world);
    const canvas = fakeCanvas();
    field.draw({ g: canvas.context, layout, time: 0.5, cosmetic: new CosmeticRng() });
    const face = canvas.log.find((call) => call.name === 'translate');
    const faceX = face?.args[0] as number;
    // 顔は浮かびながら少し横へ流れるので、盤面の左端寄りにあるかだけを見る。
    expect(Math.abs(faceX - screenX(layout, 1.5))).toBeLessThan(layout.tile * 2);
  });

  it('延長戦で自律物が片付けられても、消えたときの煙を出さない', () => {
    // 片付けは踏まれたのでも寿命でもない。
    const world = makeWorld();
    const field = new ParticleField(new CosmeticRng());
    observeNew(field, world, new ScatteredActor({ col: 5, row: 5 }, 0));
    field.onEvents([], world);
    const before = paintedParticles(field);
    const events = enterSuddenDeath(world, [0, 1], 'timeUp');
    field.onEvents(events, world);
    expect(paintedParticles(field)).toBeLessThanOrEqual(before);
    expect(field.shake).toBe(0);
  });

  it('落とし穴は、仕掛けられても粒子を出さない', () => {
    const world = makeWorld();
    const field = new ParticleField(new CosmeticRng());
    observeNew(field, world, new PitActor({ col: 5, row: 5 }, 0));
    expect(paintedParticles(field)).toBe(0);
  });

  it('落とし穴は、誰かが落ちて消えたときだけ揺らす（落ちない相手が乗ったまま時間切れになっても揺らさない）', () => {
    // そのマスに誰かいるかで決めると、落ちない相手（ほかのもぐら）が乗ったまま時間切れになったとき、
    // 見えないはずの穴の位置を見せてしまう。
    const untilPitGoes = (animal: string): { shake: number; ticks: number } => {
      const world = makeWorld(1, ['mole', animal]);
      clearBoard(world);
      const field = new ParticleField(new CosmeticRng());
      const sim = new Simulation();
      const idle = new Map(world.players.map((player) => [player.id, IDLE_INPUT]));
      world.players[1]!.position = centerOf({ col: 5, row: 5 });
      observeNew(field, world, new PitActor({ col: 5, row: 5 }, 0));
      let ticks = 0;
      while (world.actors.some((actor) => actor instanceof PitActor)) {
        field.onEvents(sim.step(world, idle), world);
        ticks += 1;
      }
      return { shake: field.shake, ticks };
    };
    const onMole = untilPitGoes('mole');
    // 片付け（延長戦）で消えたのではなく、時間切れまで乗り続けたことを確かめる。
    expect(onMole.ticks).toBe(3600);
    expect(onMole.shake).toBe(0);
    expect(untilPitGoes('rabbit').shake).toBeGreaterThan(0);
  });

  it('落とし穴の寿命の最後の tick に落ちても、落ちたものとして揺らす', () => {
    // 落ちた tick には残りを減らさない（`PitActor.tick`）。減らしてから落とすと、最後の tick に
    // 落ちた穴は残りが 0 になり、時間切れと見分けられない。
    const world = makeWorld(1, ['mole', 'rabbit']);
    clearBoard(world);
    const field = new ParticleField(new CosmeticRng());
    const sim = new Simulation();
    const idle = new Map(world.players.map((player) => [player.id, IDLE_INPUT]));
    const rabbit = world.players[1]!;
    rabbit.position = centerOf({ col: 9, row: 9 });
    const pit = new PitActor({ col: 5, row: 5 }, 0);
    observeNew(field, world, pit);
    while (pit.remaining > 1) field.onEvents(sim.step(world, idle), world);
    rabbit.position = centerOf({ col: 5, row: 5 });
    field.onEvents(sim.step(world, idle), world);
    expect(rabbit.effects.has('pitfall')).toBe(true);
    expect(world.actors).not.toContain(pit);
    expect(field.shake).toBeGreaterThan(0);
  });

  it('撒かれた障害物が置かれると、煙を出す', () => {
    const world = makeWorld();
    const field = new ParticleField(new CosmeticRng());
    observeNew(field, world, new ScatteredActor({ col: 5, row: 5 }, 0));
    expect(paintedParticles(field)).toBeGreaterThan(0);
  });

  /** 光の玉の数。1つにつき放射状の塗りを1回使う。 */
  function glows(field: ParticleField): number {
    const canvas = fakeCanvas();
    field.draw(frameOn(canvas));
    return count(canvas, 'createRadialGradient');
  }

  it('追いかける炎は、通った跡に光の玉を残す', () => {
    const world = makeWorld();
    const field = new ParticleField(new CosmeticRng());
    observeNew(field, world, new FoxfireActor({ x: 5.5, y: 5.5 }, 0));
    for (let t = 1; t <= 8; t += 1) {
      world.now = tick(t);
      field.onEvents([], world);
    }
    expect(glows(field)).toBeGreaterThan(0);
  });

  it('盤面が止まっている間は、光の玉を足さない', () => {
    // 決着のあとの待ちや試合の終わりでは時刻が進まない。そこで毎 tick 足すと、
    // 同じ場所に光が重なって白く塗りつぶされる。
    const world = makeWorld();
    const field = new ParticleField(new CosmeticRng());
    observeNew(field, world, new FoxfireActor({ x: 5.5, y: 5.5 }, 0));
    world.now = tick(8);
    field.onEvents([], world);
    const once = glows(field);
    for (let i = 0; i < 30; i += 1) field.onEvents([], world);
    expect(glows(field)).toBeLessThanOrEqual(once);
  });

  it('盤面が作り直されたら、前のラウンドの粒子と揺れを持ち越さない', () => {
    const field = new ParticleField(new CosmeticRng());
    const first = makeWorld();
    field.onEvents(realExplosion(first), first);
    expect(field.shake).toBeGreaterThan(0);

    const next = makeWorld();
    field.onEvents([], next);
    expect(field.shake).toBe(0);
    expect(paintedParticles(field)).toBe(0);
  });
});
