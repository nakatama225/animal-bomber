import { describe, expect, it } from 'vitest';

import { CpuInputSource, cpuSeed } from '../../src/ai/CpuInputSource.js';
import { CPU_LEVELS } from '../../src/ai/CpuLevel.js';
import { GameSession } from '../../src/app/GameSession.js';
import { defaultMatchConfig } from '../../src/domain/rules/MatchConfig.js';

/**
 * 試合を通して崩れない約束。
 *
 * 1つの場面を組み立てて確かめるテストは、組み立てた場面しか見ない。ここでは CPU どうしの
 * 試合を決着まで回し、毎 tick 同じ約束を確かめる。場面を思いつかなかった崩れ方も、
 * 試合の中で起きれば捕まる。
 */
describe('試合を通して崩れない約束', () => {
  it('同じマスにアイテムが2つ並ばない', () => {
    // アイテムを置く処理は、どれも「そのマスにもうアイテムがあれば置かない」か、いま壊した
    // ブロックのマス（アイテムが乗っていたはずがない）に置くかのどちらか。だから並ばない。
    // 段階 3 から 2026-10-04 まで、2つの爆弾の爆風が同じブロックに届くと抽選を2回引き、
    // 同じマスに2つ出ていた。種 0〜9 の試合すべてで起きていた（この種では 1,849 tick 目）。
    // 並べてよい仕組みを足すときは、この約束から決め直す。
    const seed = 7;
    const animals = ['rabbit', 'elephant', 'fox', 'frog'];
    const game = new GameSession({ ...defaultMatchConfig(seed, animals), winsToTake: 2 });
    game.world.players.forEach((player) =>
      game.attach(new CpuInputSource(player.id, CPU_LEVELS.oni, cpuSeed(seed, player.id))),
    );

    let dropped = 0;
    for (let i = 0; i < 60000 && !game.match.finished; i += 1) {
      dropped += game.tick().filter((event) => event.type === 'itemDropped').length;
      const cells = game.world.items.map((item) => `${item.cell.col},${item.cell.row}`);
      expect(new Set(cells).size, `${i + 1} tick 目`).toBe(cells.length);
    }
    // 前提：試合が終わり、アイテムが何度も出た。出なければ、この確かめは何も見ていない。
    expect(game.match.finished).toBe(true);
    expect(dropped).toBeGreaterThan(20);
  }, 60_000);
});
