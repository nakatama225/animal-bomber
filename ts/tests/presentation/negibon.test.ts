import { describe, expect, it } from 'vitest';

import { DIRECTIONS, step } from '../../src/domain/core/Coord.js';
import { tick, type Tick } from '../../src/domain/core/Tick.js';
import { alongsFacing, laneSpot } from '../../src/domain/negibon/lane.js';
import { LeekActor } from '../../src/domain/negibon/LeekActor.js';
import { LEEK_COOLDOWN, LEEK_FIRST_COOLDOWN } from '../../src/domain/rules/negibon.js';
import { COLS, ROWS } from '../../src/domain/rules/tuning.js';
import type { Negibon } from '../../src/domain/state/Life.js';
import { hashWorld } from '../../src/domain/state/WorldState.js';
import { CosmeticRng } from '../../src/presentation/CosmeticRng.js';
import { drawAirActor } from '../../src/presentation/render/actors.js';
import type { Frame } from '../../src/presentation/render/Frame.js';
import { layoutFor, screenX, screenY } from '../../src/presentation/render/Layout.js';
import { drawNegibon } from '../../src/presentation/render/negibon.js';
import { makeWorld } from '../helpers.js';
import { fakeCanvas, type FakeCanvas } from './fakeCanvas.js';

/**
 * 外周の葱ボンと、飛んでいる葱の描画。
 *
 * 試合を通す検査（renderer.test.ts）では、CPU が外周のどの辺にいつ回るかは試合の流れ次第で、
 * 撃てる間と待つ間の両方を4辺すべてで通るとは限らない。ここでは狙って1つずつ描く。
 */

const layout = layoutFor(920, 680);

function frameOn(canvas: FakeCanvas): Frame {
  return { g: canvas.context, layout, time: 0.5, cosmetic: new CosmeticRng() };
}

function count(canvas: FakeCanvas, name: string): number {
  return canvas.calls.get(name) ?? 0;
}

/** 盤面の中ほどのマスへ撃てる、4辺それぞれの帯の上の位置。 */
const SIDES = alongsFacing({ col: 5, row: 5 });

/**
 * いまの tick。0 だと撃てる tick の値がそのまま残りの長さと等しくなり、残りを求めるときに
 * いまの tick を引き忘れても検査が通る。
 */
const NOW = tick(600);

/** 1人目を葱ボンにし、状態が変わらないことを確かめながら1回描く。 */
function drawOnce(along: number, readyAt: Tick): FakeCanvas {
  const world = makeWorld(7, ['rabbit', 'elephant']);
  world.now = NOW;
  const player = world.players[0]!;
  const life: Negibon = { kind: 'negibon', along, readyAt };
  player.life = life;
  const canvas = fakeCanvas();
  const before = hashWorld(world);
  drawNegibon(frameOn(canvas), player.animal, life, world.now);
  expect(hashWorld(world)).toBe(before);
  return canvas;
}

/** 次の葱までの残りを示す棒の幅。棒を描いていなければ 0。 */
function barWidth(canvas: FakeCanvas): number {
  const bar = canvas.log.find((call) => call.name === 'fillRect');
  return bar === undefined ? 0 : (bar.args[2] as number);
}

describe('外周の葱ボン', () => {
  it('4辺それぞれの帯の上の位置は、上辺・右辺・下辺・左辺に1つずつある', () => {
    // 下の検査が4辺すべてを通っていることの前提。
    expect(SIDES.map((along) => laneSpot(along).side)).toEqual(['top', 'right', 'bottom', 'left']);
  });

  it.each([
    { name: '撃てる', wait: 0 },
    { name: '撃ったばかり', wait: LEEK_COOLDOWN },
    { name: '外周へ回ったばかり', wait: LEEK_FIRST_COOLDOWN },
  ])('$name 葱ボンを、4辺のどこでも描け、状態は変わらない', ({ wait }) => {
    for (const along of SIDES) {
      const canvas = drawOnce(along, tick(NOW + wait));
      expect(count(canvas, 'fill'), laneSpot(along).side).toBeGreaterThan(0);
      expect(count(canvas, 'stroke'), laneSpot(along).side).toBeGreaterThan(0);
    }
  });

  it('撃てるまでの間は残りの棒を出し、撃てるようになったら葉の印に替える', () => {
    const waiting = drawOnce(SIDES[0], tick(NOW + 1));
    expect(count(waiting, 'fillRect')).toBe(1);
    expect(waiting.log.some((call) => call.name === 'fillText' && call.args[0] === '🌿')).toBe(false);

    // 撃てるかどうかはルールの層と同じく「いまの tick が撃てる tick に達したか」で決まる。
    const ready = drawOnce(SIDES[0], NOW);
    expect(count(ready, 'fillRect')).toBe(0);
    expect(ready.log.some((call) => call.name === 'fillText' && call.args[0] === '🌿')).toBe(true);
  });

  it('残りの棒は待つほど短くなり、外周へ回った直後の長い待ちでも満タンの幅を越えない', () => {
    // 外周へ回った直後の待ちは撃つ間隔より長い。割合を切らないと、棒が鍋からはみ出す。
    const full = barWidth(drawOnce(SIDES[0], tick(NOW + LEEK_COOLDOWN)));
    const half = barWidth(drawOnce(SIDES[0], tick(NOW + LEEK_COOLDOWN / 2)));
    const first = barWidth(drawOnce(SIDES[0], tick(NOW + LEEK_FIRST_COOLDOWN)));
    expect(half).toBeGreaterThan(0);
    expect(half).toBeLessThan(full);
    expect(first).toBe(full);
  });

  it('撃つ向きの点線は、どの辺からも盤面の内側へ伸びる', () => {
    const inside = (x: number, y: number): boolean =>
      x > screenX(layout, 0) && x < screenX(layout, COLS) && y > screenY(layout, 0) && y < screenY(layout, ROWS);
    for (const along of SIDES) {
      const canvas = drawOnce(along, NOW);
      // 鍋の輪郭も lineTo で作るので、最後に引いた線を点線とみなす。
      const end = canvas.log.filter((call) => call.name === 'lineTo').at(-1);
      expect(end, laneSpot(along).side).toBeDefined();
      const [x, y] = end!.args as [number, number];
      expect(inside(x, y), laneSpot(along).side).toBe(true);
    }
  });
});

describe('飛んでいる葱', () => {
  it.each(DIRECTIONS)('%s へ飛ぶ葱を描け、葉の側を飛ぶ向きへ回す', (facing) => {
    const leek = new LeekActor({ x: 5.5, y: 5.5 }, facing, 0);
    const before = leek.encode();
    const canvas = fakeCanvas();
    drawAirActor(frameOn(canvas), leek);
    expect(count(canvas, 'fill')).toBe(2);
    expect(count(canvas, 'stroke')).toBe(1);
    expect(leek.encode()).toBe(before);

    // 回した後の横向きが、飛ぶ向きと一致する。
    const turn = canvas.log.find((call) => call.name === 'rotate');
    const angle = turn?.args[0] as number;
    const unit = step({ col: 0, row: 0 }, facing);
    expect(Math.cos(angle)).toBeCloseTo(unit.col);
    expect(Math.sin(angle)).toBeCloseTo(unit.row);

    // 葉（2つ目に塗る形）が、回した後の前の側（横の座標が正）に収まっている。
    // 葉が後ろにあると、茎を先にして飛んでいるように見える。
    const fills = canvas.log.flatMap((call, index) => (call.name === 'fill' ? [index] : []));
    const leaf = canvas.log.slice(fills[0]! + 1, fills[1]);
    const xs = leaf.filter((call) => call.name === 'moveTo' || call.name === 'lineTo').map((call) => call.args[0] as number);
    expect(xs.length).toBeGreaterThan(0);
    expect(Math.min(...xs)).toBeGreaterThanOrEqual(0);
  });
});
