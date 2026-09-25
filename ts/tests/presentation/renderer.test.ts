import { describe, expect, it } from 'vitest';

import { CpuIntentSource, cpuSeed } from '../../src/ai/CpuIntentSource.js';
import { CPU_LEVELS } from '../../src/ai/CpuLevel.js';
import { GameSession } from '../../src/app/GameSession.js';
import { defaultMatchConfig } from '../../src/domain/rules/MatchConfig.js';
import { hashWorld } from '../../src/domain/state/WorldState.js';
import { Renderer } from '../../src/presentation/render/Renderer.js';
import { fakeCanvas } from './fakeCanvas.js';

/**
 * 描画の通し検査。
 *
 * CPU どうしの試合を、決着まで毎 tick 描く。舌・跳ね回る爆弾・突進・撒く技・
 * 追いかける炎が現れ、ラウンドの切り替わり（決着のあとの待ちと、盤面の作り直し）も
 * 通る。この種と顔ぶれで何が現れるかは、試合の中身が変わると変わるので、
 * 途中で現れたものを数えて確かめている。
 */
describe('描画', () => {
  it('CPU どうしの試合を毎 tick 描いても例外が出ず、状態も変わらない', () => {
    const seed = 31;
    const animals = ['rabbit', 'frog', 'elephant', 'fox'];
    const game = new GameSession({ ...defaultMatchConfig(seed, animals), winsToTake: 2 });
    game.world.players.forEach((player) =>
      game.attach(new CpuIntentSource(player.id, CPU_LEVELS.oni, cpuSeed(seed, player.id))),
    );
    const canvas = fakeCanvas();
    const renderer = new Renderer(canvas.context, 920, 680);

    const seen = new Set<string>();
    let intermissions = 0;
    for (let i = 0; i < 20000 && !game.match.finished; i += 1) {
      const world = game.world;
      renderer.beforeTick(world);
      const events = game.tick();
      renderer.afterTick(events, world);
      if (game.betweenRounds) intermissions += 1;
      for (const actor of game.world.actors) seen.add(actor.kind);
      for (const player of game.world.players) if (player.action !== null) seen.add(player.action.kind);
      const before = hashWorld(game.world);
      renderer.draw(game.world, 0.5);
      expect(hashWorld(game.world)).toBe(before);
    }
    expect(game.match.finished).toBe(true);
    expect(intermissions).toBeGreaterThan(0);
    for (const kind of ['tongue', 'slime', 'charge', 'scatter', 'foxfire']) {
      expect(seen.has(kind), kind).toBe(true);
    }
    // 1万回を超える描画を偽の canvas に通すので、既定の制限時間では足りない。
  }, 120_000);
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
