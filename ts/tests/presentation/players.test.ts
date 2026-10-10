import { describe, expect, it } from 'vitest';

import { ANIMAL_LOOKS } from '../../src/content/animals.js';
import { abilityOf } from '../../src/domain/abilities/registry.js';
import { ChargeAction } from '../../src/domain/abilities/elephant/ChargeAction.js';
import { TongueAction } from '../../src/domain/abilities/frog/TongueAction.js';
import { PitAction } from '../../src/domain/abilities/mole/PitAction.js';
import { ScatterAction } from '../../src/domain/abilities/rabbit/ScatterAction.js';
import { cellOf, DIRECTIONS } from '../../src/domain/core/Coord.js';
import { tick } from '../../src/domain/core/Tick.js';
import { EFFECT_KINDS } from '../../src/domain/state/EffectBag.js';
import type { PlayerState } from '../../src/domain/state/PlayerState.js';
import { hashWorld, type WorldState } from '../../src/domain/state/WorldState.js';
import { CosmeticRng } from '../../src/presentation/CosmeticRng.js';
import { headPainterOf, plainHead } from '../../src/presentation/render/animals/registry.js';
import { EFFECT_ICONS, statusIcons } from '../../src/presentation/render/effectIcons.js';
import type { Frame } from '../../src/presentation/render/Frame.js';
import { layoutFor } from '../../src/presentation/render/Layout.js';
import { drawPlayer } from '../../src/presentation/render/players.js';
import { makeWorld } from '../helpers.js';
import { fakeCanvas, type FakeCanvas } from './fakeCanvas.js';

/**
 * プレイヤーの描画の検査。
 *
 * 試合を通す検査（renderer.test.ts）では、どの動物がどの向きでどの状態になるかは
 * 試合の流れ次第で、通らない組み合わせが残る。ここでは動物・向き・歩いているか・
 * 状態のすべての組み合わせを、狙って1回ずつ描く。
 */

interface Case {
  readonly name: string;
  /** その状態にする。世界ごと渡すのは、振る舞いを進めるのに世界が要るため。 */
  readonly setup: (world: WorldState, player: PlayerState) => void;
  readonly invulnerable?: boolean;
  /** 足元に絵文字が出るはずか。 */
  readonly icons?: boolean;
  /** とくぎの溜めのゲージが出るはずか。 */
  readonly gauge?: boolean;
}

const CASES: readonly Case[] = [
  { name: '何もない', setup: () => undefined },
  { name: '泣いて動けない', setup: (_w, p) => p.effects.add('stun', tick(60), tick(120)), icons: true },
  { name: '滑っている', setup: (_w, p) => p.effects.add('slide', tick(60), tick(120)), icons: true },
  { name: '操作が反転', setup: (_w, p) => p.effects.add('reverse', tick(60), tick(120)), icons: true },
  {
    name: 'とくぎを溜めている途中',
    setup: (_w, p) => {
      p.specialCharges = 1;
      p.actionHeld = tick(Math.floor(abilityOf(p.animal).holdTicks / 2));
    },
    icons: true,
    gauge: true,
  },
  { name: '無敵で点滅中', setup: () => undefined, invulnerable: true },
  {
    name: '舌を伸ばしている',
    setup: (w, p) => {
      const action = new TongueAction(p.facing);
      for (let i = 0; i < 8; i += 1) action.tick(w, p);
      p.action = action;
    },
    icons: true,
  },
  {
    name: '穴を掘っている',
    setup: (w, p) => {
      const action = new PitAction(cellOf(p.position));
      for (let i = 0; i < 45; i += 1) action.tick(w, p);
      p.action = action;
    },
    icons: true,
  },
  { name: '周りを埋めている', setup: (_w, p) => (p.action = new ScatterAction(cellOf(p.position))), icons: true },
];

function frameOn(canvas: FakeCanvas, time = 0): Frame {
  return { g: canvas.context, layout: layoutFor(920, 680), time, cosmetic: new CosmeticRng() };
}

/** 1人だけの世界を作り、状態を整えて1回描く。 */
function drawOnce(animal: string, facing: PlayerState['facing'], moving: boolean, c: Case, time = 0): FakeCanvas {
  const world = makeWorld(7, [animal]);
  const player = world.players[0]!;
  player.facing = facing;
  player.walked = 1.3;
  c.setup(world, player);
  const canvas = fakeCanvas();
  const before = hashWorld(world);
  drawPlayer(frameOn(canvas, time), {
    player,
    x: player.position.x,
    y: player.position.y,
    moving,
    invulnerable: c.invulnerable ?? false,
  });
  // 描いても状態は変わらない。
  expect(hashWorld(world)).toBe(before);
  return canvas;
}

describe('プレイヤーの描画', () => {
  // 時刻を2つ試すのは、点滅・震え・土くれのように時刻で切り替わる描き分けを両側とも通すため。
  // 0 秒ちょうどでは sin が 0 になり、姿勢を崩す分岐や土くれを飛ばす分岐を通らない。
  it.each(CASES)('$name: 5匹・4方向・歩行の有無のすべてで最後まで描ける', (c) => {
    for (const { key } of ANIMAL_LOOKS) {
      for (const facing of DIRECTIONS) {
        for (const moving of [false, true]) {
          for (const time of [0, 0.1]) {
            const canvas = drawOnce(key, facing, moving, c, time);
            const label = `${key} ${facing} ${moving ? '歩行' : '停止'} ${time}s`;
            expect(canvas.calls.get('fill') ?? 0, label).toBeGreaterThan(0);
            expect(canvas.calls.get('stroke') ?? 0, label).toBeGreaterThan(0);
            if (c.icons === true) expect(canvas.calls.get('fillText') ?? 0, label).toBeGreaterThan(0);
            if (c.gauge === true) expect(canvas.calls.get('fillRect') ?? 0, label).toBeGreaterThan(0);
          }
        }
      }
    }
  });

  it('点滅で薄くしている間は、体の中の半透明の部分を描いた後も薄いまま', () => {
    // 体の中で透明度を 1 に戻すと、点滅中でも腕と頭だけが濃く描かれる。
    for (const { key } of ANIMAL_LOOKS) {
      const canvas = drawOnce(key, 'down', false, { name: '無敵', setup: () => undefined, invulnerable: true });
      expect(canvas.context.globalAlpha, key).toBeCloseTo(0.35);
    }
  });
});

describe('とくぎの溜めのゲージ', () => {
  it('とくぎの最中は、次のとくぎが残っていてもゲージを出さない', () => {
    // 技の最中はゲームの側がボタンを見ないので、押した長さが満タンのまま残る。
    // 描くと、次のとくぎがもう出せるように見える。
    const full = (withAction: boolean): Case => ({
      name: withAction ? '突進の最中' : '溜め切った直後',
      setup: (_w, p) => {
        p.specialCharges = 2;
        p.actionHeld = abilityOf(p.animal).holdTicks;
        if (withAction) p.action = new ChargeAction(p.facing);
      },
    });
    const rects = (c: Case): number => drawOnce('elephant', 'down', false, c).calls.get('fillRect') ?? 0;
    expect(rects(full(false))).toBeGreaterThan(rects(full(true)));
  });
});

describe('頭の登録表', () => {
  it('見た目のある動物にはすべて専用の頭がある', () => {
    for (const { key } of ANIMAL_LOOKS) expect(headPainterOf(key), key).not.toBe(plainHead);
  });

  it('登録の無い動物は丸い頭で描く', () => {
    expect(headPainterOf('unregistered-animal')).toBe(plainHead);
    const canvas = fakeCanvas();
    plainHead(canvas.context, 0, 0, 10, 'front', { color: '#fff', shade: '#000', fur: '#eee' });
    expect(canvas.calls.get('arc') ?? 0).toBeGreaterThan(0);
  });
});

describe('足元の絵文字', () => {
  it('すべての状態に絵文字がある', () => {
    for (const kind of EFFECT_KINDS) expect(EFFECT_ICONS[kind], kind).toBeTruthy();
  });

  it('溜めてあるとくぎ → 技 → 状態の順に並ぶ', () => {
    const world = makeWorld(7, ['frog']);
    const player = world.players[0]!;
    player.specialCharges = 1;
    player.effects.add('slow', tick(60), tick(120));
    expect(statusIcons(player, '👅')).toEqual(['🟢', '👅', '🐌']);
  });
});

describe('描画のために読む値', () => {
  it('舌の長さは伸びてから縮み、最後は 0 に戻る', () => {
    const world = makeWorld(7, ['frog']);
    const player = world.players[0]!;
    const action = new TongueAction(player.facing);
    const lengths: number[] = [action.extent];
    for (let i = 0; i < 48; i += 1) {
      action.tick(world, player);
      lengths.push(action.extent);
    }
    expect(lengths[0]).toBe(0);
    expect(Math.max(...lengths)).toBe(6);
    expect(lengths[24]).toBe(6);
    expect(lengths[36]).toBe(3);
    expect(lengths[48]).toBe(0);
  });

  it('穴掘りの進みは 0 から 1 まで進む', () => {
    const world = makeWorld(7, ['mole']);
    const player = world.players[0]!;
    const action = new PitAction(cellOf(player.position));
    expect(action.progress).toBe(0);
    for (let i = 0; i < 45; i += 1) action.tick(world, player);
    expect(action.progress).toBeCloseTo(0.5);
    for (let i = 0; i < 45; i += 1) action.tick(world, player);
    expect(action.progress).toBe(1);
  });
});
