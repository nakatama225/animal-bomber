import { describe, expect, it } from 'vitest';

import { ANIMAL_LOOKS } from '../../src/content/animals.js';
import { abilityOf } from '../../src/domain/abilities/registry.js';
import { ChargeAction } from '../../src/domain/abilities/elephant/ChargeAction.js';
import { TongueAction } from '../../src/domain/abilities/frog/TongueAction.js';
import { PitAction } from '../../src/domain/abilities/mole/PitAction.js';
import { cellOf, centerOf, DIRECTIONS } from '../../src/domain/core/Coord.js';
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
import { clearBoard, grantSpecial, makeWorld } from '../helpers.js';
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
      grantSpecial(p, 1);
      p.actionHeld = tick(Math.floor(abilityOf(p.animal).holdTicks / 2));
      p.actionFired = false;
    },
    icons: true,
    gauge: true,
  },
  { name: '無敵で点滅中', setup: () => undefined, invulnerable: true },
  {
    name: '舌を伸ばしている',
    setup: (w, p) => {
      const action = new TongueAction(cellOf(p.position), p.facing);
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
  {
    name: '周りを埋めている',
    setup: (_w, p) => p.effects.add('scattering', tick(60), tick(120)),
    icons: true,
  },
  { name: 'キツネ跳び', setup: (_w, p) => p.effects.add('leap', tick(30), tick(60)), icons: true },
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
  it('この押し方のとくぎを出し終えたら（actionFired）、押し続けていても次のとくぎが残っていてもゲージを出さない', () => {
    // 原型も出し終えたら消す（actFired）。描くと、次のとくぎがもう出せるように見える。
    const held = (fired: boolean): Case => ({
      name: fired ? '出し終えた' : '溜めている途中',
      setup: (_w, p) => {
        grantSpecial(p, 2);
        p.actionHeld = abilityOf(p.animal).holdTicks;
        p.actionFired = fired;
      },
    });
    const rects = (c: Case): number => drawOnce('elephant', 'down', false, c).calls.get('fillRect') ?? 0;
    expect(rects(held(false))).toBeGreaterThan(rects(held(true)));
  });

  it('振る舞いの最中でも、押していて出し終えていなければゲージを出す（最中もとくぎのボタンは効く。原型と同じ）', () => {
    const during = (withAction: boolean): Case => ({
      name: withAction ? '突進の最中' : '突進していない',
      setup: (_w, p) => {
        grantSpecial(p, 1);
        p.actionHeld = tick(10);
        p.actionFired = false;
        if (withAction) p.action = new ChargeAction(p.facing);
      },
    });
    const gauge = (c: Case): number => drawOnce('elephant', 'down', false, c).calls.get('fillRect') ?? 0;
    expect(gauge(during(true))).toBe(gauge(during(false)));
    expect(gauge(during(true))).toBeGreaterThan(0);
  });

  it('回数が残っていても、持っている印が外れていればゲージを出さない（原型 L4823 は p.chicken で見る）', () => {
    // 外周から戻ると回数だけが残る（原型の toNegibon L2255 は chicken だけを消す）。そのとくぎは出せない。
    const holding = (mark: boolean): Case => ({
      name: mark ? '印あり' : '回数だけ',
      setup: (_w, p) => {
        grantSpecial(p, 2);
        p.hasSpecial = mark;
        p.actionHeld = tick(10);
        p.actionFired = false;
      },
    });
    const rects = (c: Case): number => drawOnce('elephant', 'down', false, c).calls.get('fillRect') ?? 0;
    const none = rects({ name: '押していない', setup: () => undefined });
    expect(rects(holding(true))).toBeGreaterThan(none);
    expect(rects(holding(false))).toBe(none);
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
    grantSpecial(player, 1);
    player.effects.add('slow', tick(60), tick(120));
    expect(statusIcons(player, '👅')).toEqual(['🟢', '👅', '🐌']);
  });

  it('回数が残っていても、持っている印が外れていればとくぎの絵文字を出さない（原型 L4813 は p.chicken で見る）', () => {
    // 外周から戻ると回数だけが残る（原型の toNegibon L2255 は chicken だけを消す）。対照は上の並びの確認。
    const world = makeWorld(7, ['frog']);
    const player = world.players[0]!;
    grantSpecial(player, 2);
    player.hasSpecial = false;
    player.effects.add('slow', tick(60), tick(120));
    expect(statusIcons(player, '👅')).toEqual(['👅', '🐌']);
  });
});

describe('描画のために読む値', () => {
  it('舌の長さは伸びてから縮み、伸びきる手前まで届いて、終わる直前には 0 近くまで戻る', () => {
    // 何も無い所へ伸ばす。10 マス伸びて戻り、151 tick 目に終わる（`TongueAction`）。
    const world = makeWorld(7, ['frog']);
    clearBoard(world);
    const player = world.players[0]!;
    player.position = centerOf({ col: 3, row: 5 });
    player.facing = 'right';
    const action = new TongueAction(cellOf(player.position), player.facing);
    const lengths: number[] = [action.extent];
    let done = false;
    while (!done && lengths.length < 200) {
      done = action.tick(world, player).done;
      if (!done) lengths.push(action.extent);
    }
    expect(lengths[0]).toBe(0);
    const peak = lengths.indexOf(Math.max(...lengths));
    expect(Math.max(...lengths)).toBeGreaterThan(9.9);
    expect(Math.max(...lengths)).toBeLessThanOrEqual(10);
    // 頂点までは伸び続け、そのあとは縮み続ける。
    for (let i = 1; i <= peak; i += 1) expect(lengths[i]!).toBeGreaterThanOrEqual(lengths[i - 1]!);
    for (let i = peak + 1; i < lengths.length; i += 1) expect(lengths[i]!).toBeLessThanOrEqual(lengths[i - 1]!);
    expect(lengths.at(-1)!).toBeLessThan(0.2);
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
