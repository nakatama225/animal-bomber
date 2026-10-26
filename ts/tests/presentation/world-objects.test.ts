import { describe, expect, it } from 'vitest';

import { FoxfireActor } from '../../src/domain/abilities/fox/FoxfireActor.js';
import { SlimeBombActor } from '../../src/domain/abilities/frog/SlimeBombActor.js';
import { BurntTongueActor } from '../../src/domain/abilities/frog/TongueAction.js';
import { PitActor } from '../../src/domain/abilities/mole/PitAction.js';
import { ScatterActor } from '../../src/domain/abilities/rabbit/ScatterActor.js';
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
import { drawAirActor } from '../../src/presentation/render/actors.js';
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
 * 見せてはいけないもの（落とし穴）を描かないことを確認する。
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
    drawItem(frameOn(canvas), { id: 1 as never, cell: { col: 4, row: 5 }, kind }, tick(0));
    expect(count(canvas, 'fillText')).toBe(1);
    expect(count(canvas, 'stroke')).toBeGreaterThan(0);
  });

  it('撒かれたものは桃色で描き、消える前の 3.5 秒は点滅する（消える時刻の無いアイテムは点滅しない）', () => {
    // 偽の canvas は代入の最後の値を残す。札の不透明度は最初に1回だけ入れ、下地の色味は最後の塗りに残る。
    // frameOn の時刻 0.5 秒では、点滅の sin が 1 から遠いので薄くなる。
    const drawn = (item: Parameters<typeof drawItem>[1], now: number): { alpha: unknown; tint: unknown } => {
      const canvas = fakeCanvas();
      drawItem(frameOn(canvas), item, tick(now));
      return { alpha: canvas.context.globalAlpha, tint: canvas.context.fillStyle };
    };
    const plain = { id: 1 as never, cell: { col: 4, row: 5 }, kind: 'poop' as const };
    const scattered = { ...plain, scatteredBy: 0 as const, expiresAt: tick(3600) };
    expect(drawn(scattered, 0)).toEqual({ alpha: 1, tint: 'rgba(255,150,200,.34)' });
    expect(drawn(scattered, 3500).alpha).toBeLessThan(1);
    expect(drawn(plain, 3500)).toEqual({ alpha: 1, tint: 'rgba(255,105,80,.34)' });
    // ふつうのうんこ（消える時刻だけ持つ）も、損をする色のまま、消える前は点滅する（原型と同じ）。
    const expiring = { ...plain, expiresAt: tick(900) };
    expect(drawn(expiring, 0)).toEqual({ alpha: 1, tint: 'rgba(255,105,80,.34)' });
    expect(drawn(expiring, 800)).toEqual({ alpha: expect.any(Number), tint: 'rgba(255,105,80,.34)' });
    expect(drawn(expiring, 800).alpha).toBeLessThan(1);
  });

  it('鼻水で溶けているうんこは、溶けきるまでの残りに合わせて薄れていく', () => {
    const alphaAt = (now: number): unknown => {
      const canvas = fakeCanvas();
      drawItem(frameOn(canvas), { id: 1 as never, cell: { col: 4, row: 5 }, kind: 'poop', meltingUntil: tick(27) }, tick(now));
      return canvas.context.globalAlpha;
    };
    expect(alphaAt(0)).toBe(1);
    expect(alphaAt(13)).toBeCloseTo(14 / 27);
    expect(alphaAt(26)).toBeCloseTo(1 / 27);
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

  const cases: { name: string; actor: WorldActor; air: boolean }[] = [
    { name: '落とし穴', actor: new PitActor({ col: 5, row: 5 }, 0), air: false },
    { name: '追いかける炎', actor: new FoxfireActor({ x: 5.5, y: 5.5 }, 0), air: true },
    { name: '跳ね回る爆弾', actor: new SlimeBombActor({ col: 5, row: 5 }, owner, 6), air: true },
    { name: '飛んでいる葱', actor: new LeekActor({ x: 5.5, y: 5.5 }, 'down', 0), air: true },
    // 撒くとくぎと焼けた舌は盤面に描くものが無い（撒かれたものはアイテムとして描く）。
    { name: '撒くとくぎ', actor: new ScatterActor({ col: 5, row: 5 }, 0), air: false },
    { name: '焼けた舌', actor: new BurntTongueActor(0, 3), air: false },
  ];

  it.each(cases)('$name は描くものだけを描き、状態は変わらない', ({ actor, air }) => {
    const before = actor.encode();
    const above = fakeCanvas();
    drawAirActor(frameOn(above), actor);
    expect(above.calls.size > 0).toBe(air);
    expect(actor.encode()).toBe(before);
  });

  it('跳ね回る爆弾は、着地からの時間が進んでも描け、残りの区切りが2以下だと輪を足す（飛んでいる間は足さない）', () => {
    // 原型も、跳ねている間で残りが2以下のときだけ赤い輪で知らせる。
    const calm = new SlimeBombActor({ col: 5, row: 5 }, owner, 6);
    const warned = new SlimeBombActor({ col: 5, row: 5 }, owner, 2);
    const flying = new SlimeBombActor({ col: 5, row: 5 }, owner, 2, { x: 2.5, y: 5.5 });
    // 30 tick なら、21 tick 目に着地して、まだ最初の区切り（19〜24 tick）の途中。
    for (let i = 0; i < 30; i += 1) {
      calm.tick(world);
      warned.tick(world);
    }
    for (let i = 0; i < 5; i += 1) flying.tick(world);
    expect([calm.flight, warned.flight]).toEqual([null, null]);
    expect(flying.flight).not.toBeNull();
    const a = fakeCanvas();
    drawAirActor(frameOn(a), calm);
    const b = fakeCanvas();
    drawAirActor(frameOn(b), warned);
    const c = fakeCanvas();
    drawAirActor(frameOn(c), flying);
    expect(count(b, 'ellipse')).toBe(count(a, 'ellipse') + 1);
    expect(count(c, 'ellipse')).toBe(count(a, 'ellipse'));
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
    return [
      { type: 'exploded', cell: bomb.cell, owner: bomb.owner, chained: result.chained, blocks: result.destroyed.length },
      ...result.events,
    ];
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
    // 片付けは踏まれたのでも寿命でもない。追いかける炎は、消えると煙を出す自律物。
    const world = makeWorld();
    const field = new ParticleField(new CosmeticRng());
    observeNew(field, world, new FoxfireActor({ x: 5.5, y: 5.5 }, 0));
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

  it('落とし穴は、誰かが落ちて消えたときに揺らす（落ちないもぐらが乗り続けても消えず、揺らさない）', () => {
    // 穴に寿命は無いので、消えるのは誰かが落ちたときだけ（ラウンドの作り直しと延長戦の片付けは、
    // 消えたものとして数えない）。
    const standOnPit = (animal: string, ticks: number): { shake: number; pitLeft: boolean } => {
      const world = makeWorld(1, ['mole', animal]);
      clearBoard(world);
      const field = new ParticleField(new CosmeticRng());
      const sim = new Simulation();
      const idle = new Map(world.players.map((player) => [player.id, IDLE_INPUT]));
      world.players[1]!.position = centerOf({ col: 5, row: 5 });
      observeNew(field, world, new PitActor({ col: 5, row: 5 }, 0));
      for (let i = 0; i < ticks; i += 1) field.onEvents(sim.step(world, idle), world);
      return { shake: field.shake, pitLeft: world.actors.some((actor) => actor instanceof PitActor) };
    };
    expect(standOnPit('mole', 4000)).toEqual({ shake: 0, pitLeft: true });
    const onRabbit = standOnPit('rabbit', 1);
    expect(onRabbit.pitLeft).toBe(false);
    expect(onRabbit.shake).toBeGreaterThan(0);
  });

  it('撒かれたうんこが置かれると煙を出し、残る長さを過ぎて消えても煙を出す', () => {
    const world = makeWorld();
    clearBoard(world);
    world.items = [];
    const placed = new ParticleField(new CosmeticRng());
    const scatter = new ScatterActor({ col: 5, row: 5 }, 0);
    placed.onEvents(scatter.tick(world).events, world);
    expect(world.items.map((item) => item.scatteredBy)).toEqual([0]);
    expect(paintedParticles(placed)).toBeGreaterThan(0);

    const expired = new ParticleField(new CosmeticRng());
    expired.onEvents([{ type: 'itemExpired', cell: { col: 5, row: 5 }, kind: 'poop', scattered: true }], world);
    expect(paintedParticles(expired)).toBeGreaterThan(0);
  });

  it('ふつうのうんこが消えたときと、爆風で吹き飛んだときにも煙を出す', () => {
    const world = makeWorld();
    for (const event of [
      { type: 'itemExpired', cell: { col: 5, row: 5 }, kind: 'poop', scattered: false },
      { type: 'itemBlown', from: { col: 5, row: 5 }, to: { col: 6, row: 5 }, kind: 'poop' },
    ] as const) {
      const field = new ParticleField(new CosmeticRng());
      field.onEvents([event], world);
      expect(paintedParticles(field), event.type).toBeGreaterThan(0);
    }
  });

  it('舌が焼き切れたときに、焼けたマスで煙を出す（原型の tongueBurnCheck の puff）', () => {
    const world = makeWorld();
    const field = new ParticleField(new CosmeticRng());
    field.onEvents([{ type: 'burntOff', player: 0, cell: { col: 5, row: 5 } }], world);
    expect(paintedParticles(field)).toBeGreaterThan(0);
  });

  it('鼻水で爆弾の火が消えたときと、うんこが溶けきったときに、しずくを出す', () => {
    const world = makeWorld();
    for (const event of [
      { type: 'bombDoused', cell: { col: 5, row: 5 }, owner: 1 },
      { type: 'itemWashed', cell: { col: 5, row: 5 }, kind: 'poop' },
    ] as const) {
      const field = new ParticleField(new CosmeticRng());
      field.onEvents([event], world);
      expect(paintedParticles(field), event.type).toBeGreaterThan(0);
    }
  });

  it('鼻水を吹くと、届いたマスごとに水しぶきを4つ出し、足元に土ぼこりは立てない（原型の elephantSnot）', () => {
    /** 通常技をポン押しで出し、出た粒の色を数える。 */
    const tapColors = (animal: string): Map<string, number> => {
      const world = makeWorld(1, [animal, 'mole']);
      clearBoard(world);
      const player = world.players[0]!;
      player.position = centerOf({ col: 3, row: 7 });
      player.facing = 'right';
      const field = new ParticleField(new CosmeticRng());
      const sim = new Simulation();
      const idle = new Map(world.players.map((p) => [p.id, IDLE_INPUT]));
      const pressing = new Map(world.players.map((p) => [p.id, p.id === 0 ? { ...IDLE_INPUT, action: true } : IDLE_INPUT]));
      field.onEvents([], world);
      for (const inputs of [idle, pressing, idle]) field.onEvents(sim.step(world, inputs), world);
      const canvas = fakeCanvas();
      const colors = new Map<string, number>();
      const fillRect = canvas.context.fillRect.bind(canvas.context);
      canvas.context.fillRect = (...args: Parameters<CanvasRenderingContext2D['fillRect']>) => {
        const color = String(canvas.context.fillStyle);
        colors.set(color, (colors.get(color) ?? 0) + 1);
        fillRect(...args);
      };
      field.draw(frameOn(canvas));
      return colors;
    };
    const snot = tapColors('elephant');
    // 正面の2マス（4,7）（5,7）に4つずつ。
    expect(snot.get('#9fd8ff')).toBe(8);
    expect(snot.has('#a6e06a')).toBe(false);
    // 対照：うさぎの跳びは足元に土ぼこりを立てる。
    expect(tapColors('rabbit').get('#a6e06a')).toBe(6);
  });

  it('引き寄せて手元で適用されたアイテム（拾ったマスが無い）は煙を出さない（対照：拾ったマスがあれば出す）', () => {
    const world = makeWorld();
    const reeled = new ParticleField(new CosmeticRng());
    reeled.onEvents([{ type: 'itemTaken', cell: null, kind: 'fire', taker: 0, swept: false }], world);
    expect(paintedParticles(reeled)).toBe(0);
    const picked = new ParticleField(new CosmeticRng());
    picked.onEvents([{ type: 'itemTaken', cell: { col: 5, row: 5 }, kind: 'fire', taker: 0, swept: false }], world);
    expect(paintedParticles(picked)).toBeGreaterThan(0);
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
