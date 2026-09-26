import { describe, expect, it } from 'vitest';

import { CpuIntentSource, cpuSeed } from '../../src/ai/CpuIntentSource.js';
import { CPU_LEVELS } from '../../src/ai/CpuLevel.js';
import { GameSession } from '../../src/app/GameSession.js';
import { centerOf } from '../../src/domain/core/Coord.js';
import { swapPlaces } from '../../src/domain/mutations/negibon.js';
import { enterSuddenDeath } from '../../src/domain/mutations/suddenDeath.js';
import { defaultMatchConfig } from '../../src/domain/rules/MatchConfig.js';
import { SPAWN_CELLS } from '../../src/domain/rules/tuning.js';
import { tick } from '../../src/domain/core/Tick.js';
import type { PlayerState } from '../../src/domain/state/PlayerState.js';
import { hashWorld } from '../../src/domain/state/WorldState.js';
import { layoutFor, screenX } from '../../src/presentation/render/Layout.js';
import { Renderer } from '../../src/presentation/render/Renderer.js';
import { makeWorld } from '../helpers.js';
import { fakeCanvas } from './fakeCanvas.js';

/**
 * 描画の通し検査。
 *
 * CPU どうしの試合を、決着まで毎 tick 描く。舌・跳ね回る爆弾・突進・撒く技・
 * 追いかける炎・外周の葱ボンと葱が現れ、ラウンドの切り替わり（決着のあとの待ちと、
 * 盤面の作り直し）も通る。この種と顔ぶれで何が現れるかは、試合の中身が変わると変わるので、
 * 途中で現れたものを数えて確かめている。
 */
describe('描画', () => {
  it('CPU どうしの試合を毎 tick 描いても例外が出ず、状態も変わらない', () => {
    // 種は、すべての技と外周の葱ボン・葱が現れるものを選んである。CPU の判断を変えると
    // 現れるものが変わるので、下の確認が落ちたら種を選び直す。
    const seed = 18;
    const animals = ['rabbit', 'frog', 'elephant', 'fox'];
    const game = new GameSession({ ...defaultMatchConfig(seed, animals), winsToTake: 2 });
    game.world.players.forEach((player) =>
      game.attach(new CpuIntentSource(player.id, CPU_LEVELS.oni, cpuSeed(seed, player.id))),
    );
    const canvas = fakeCanvas({ keepLog: false });
    const renderer = new Renderer(canvas.context, 920, 680);

    const seen = new Set<string>();
    let intermissions = 0;
    // 試合の長さは種によって大きく変わる（この顔ぶれで 80 通りの種を試すと 7,290〜33,162 tick）。
    // 上限は余裕を見て大きくとる。
    for (let i = 0; i < 60000 && !game.match.finished; i += 1) {
      const world = game.world;
      renderer.beforeTick(world);
      const events = game.tick();
      renderer.afterTick(events, world);
      if (game.betweenRounds) intermissions += 1;
      for (const actor of game.world.actors) seen.add(actor.kind);
      for (const player of game.world.players) {
        if (player.action !== null) seen.add(player.action.kind);
        if (player.life.kind === 'negibon') seen.add('negibon');
      }
      const before = hashWorld(game.world);
      renderer.draw(game.world, 0.5);
      expect(hashWorld(game.world)).toBe(before);
    }
    expect(game.match.finished).toBe(true);
    expect(intermissions).toBeGreaterThan(0);
    for (const kind of ['tongue', 'slime', 'charge', 'scatter', 'foxfire', 'negibon', 'leek']) {
      expect(seen.has(kind), kind).toBe(true);
    }
    // 数万回の描画を偽の canvas に通すので、既定の制限時間では足りない。
  }, 240_000);

  it('延長戦で開始位置へ飛び移ったプレイヤーを、前の位置との途中に描かない', () => {
    // 歩いた距離なら間を埋めると滑らかに見えるが、飛び移ったぶんを埋めると
    // 盤面を横切って滑っていくように見える。
    const world = makeWorld(3, ['rabbit']);
    world.players[0]!.position = { x: 20.5, y: 14.5 };
    const canvas = fakeCanvas();
    const renderer = new Renderer(canvas.context, 920, 680);
    renderer.beforeTick(world);
    renderer.afterTick(enterSuddenDeath(world, [0], 'timeUp'), world);
    renderer.draw(world, 0.5);

    const layout = layoutFor(920, 680);
    const spawn = centerOf(SPAWN_CELLS[0]!);
    const drawnAt = canvas.log.filter((call) => call.name === 'translate').map((call) => call.args[0] as number);
    const near = (x: number): boolean => drawnAt.some((drawn) => Math.abs(drawn - screenX(layout, x)) < 1);
    expect(near(spawn.x)).toBe(true);
    expect(near((20.5 + spawn.x) / 2)).toBe(false);
  });

  it('葱を当てて戻ったプレイヤーを、倒れた場所との途中に描かない', () => {
    // 外周にいる間は描かないので、1つ前の位置は倒れた場所のまま残っている。
    const world = makeWorld(3, ['rabbit', 'elephant']);
    const [shooter, target] = world.players as [PlayerState, PlayerState];
    shooter.position = { x: 20.5, y: 14.5 };
    shooter.life = { kind: 'negibon', along: 0, readyAt: tick(0) };
    target.position = { x: 1.5, y: 3.5 };
    const canvas = fakeCanvas();
    const renderer = new Renderer(canvas.context, 920, 680);
    renderer.beforeTick(world);
    renderer.afterTick(swapPlaces(world, shooter, target), world);
    renderer.draw(world, 0.5);

    const layout = layoutFor(920, 680);
    const drawnAt = canvas.log.filter((call) => call.name === 'translate').map((call) => call.args[0] as number);
    const near = (x: number): boolean => drawnAt.some((drawn) => Math.abs(drawn - screenX(layout, x)) < 1);
    expect(near(1.5)).toBe(true);
    expect(near((20.5 + 1.5) / 2)).toBe(false);
  });
});

describe('描画の検査に使う偽の canvas', () => {
  it('ブラウザが例外を出す呼び方は、偽物でも例外になる', () => {
    // 上の検査が「偽物が何でも受け付けるから通っている」のではないことの対照。
    const { context } = fakeCanvas();
    expect(() => context.arc(0, 0, -1, 0, 1)).toThrow(RangeError);
    expect(() => context.ellipse(0, 0, 1, -1, 0, 0, 1)).toThrow(RangeError);
    expect(() => context.createRadialGradient(0, 0, -1, 0, 0, 1)).toThrow(RangeError);
    expect(() => context.createLinearGradient(0, 0, 1, 1).addColorStop(1.5, '#000')).toThrow(RangeError);
    expect(() => context.arc(0, 0, 1, 0, 1)).not.toThrow();
  });
});
