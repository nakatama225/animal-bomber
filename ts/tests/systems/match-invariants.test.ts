import { describe, expect, it } from 'vitest';

import { CpuInputSource, cpuSeed } from '../../src/ai/CpuInputSource.js';
import { CPU_LEVELS } from '../../src/ai/CpuLevel.js';
import { GameSession } from '../../src/app/GameSession.js';
import { defaultMatchConfig } from '../../src/domain/rules/MatchConfig.js';
import { BLAST_DURATION } from '../../src/domain/rules/tuning.js';

/**
 * 試合を通して崩れない約束。
 *
 * 1つの場面を組み立てて確かめるテストは、組み立てた場面しか見ない。ここでは CPU どうしの
 * 試合を決着まで回し、毎 tick 同じ約束を確かめる。場面を思いつかなかった崩れ方も、
 * 試合の中で起きれば捕まる。
 */
describe('試合を通して崩れない約束', () => {
  it('ブロックは1回だけ壊れ、同じマスにアイテムが2つ並ばない', () => {
    // 1. 1つの tick の中で、同じブロックは1回しか壊れない。壊れたブロックは空くので、
    //    あとから届いた爆風はそこを抜ける。1つの連鎖で2つの爆風が届いても1回だけ。
    // 2. 同じマスにアイテムが2つ並ばない。アイテムを置く処理は、どれも「そのマスにもう
    //    アイテムがあれば置かない」か、いま壊したブロックのマス（アイテムが乗っていたはずが
    //    ない）に置くかのどちらか。
    // 段階 3 から 2026-10-04 まで、2つの爆弾の爆風が同じブロックに届くと 1 を破り、抽選を
    // 2回引いた。2回とも当たると 2 も破れた（種 0〜9 の試合すべてで起き、種 7 では
    // 1,849 tick 目）。1 は乱数によらず破れるので、2 より確かに捕まえる。
    // 並べてよい仕組みを足すときは、この約束から決め直す。
    // 2つの爆風が同じブロックに届く場面を通るまで、種を順に替えて試合を回す（上限 10 試合）。
    // 種を1つに決め打ちすると、技や CPU を直して試合の流れが変わるたびに、場面を通らなくなる。
    const animals = ['rabbit', 'elephant', 'fox', 'frog'];
    let dropped = 0;
    let reachedTwice = 0;
    let matches = 0;
    for (let seed = 7; seed < 17 && reachedTwice === 0; seed += 1) {
      const game = new GameSession({ ...defaultMatchConfig(seed, animals), winsToTake: 2 });
      game.world.players.forEach((player) =>
        game.attach(new CpuInputSource(player.id, CPU_LEVELS.oni, cpuSeed(seed, player.id))),
      );
      for (let i = 0; i < 60000 && !game.match.finished; i += 1) {
        const events = game.tick();
        dropped += events.filter((event) => event.type === 'itemDropped').length;
        const broken = events.flatMap((event) =>
          event.type === 'blockDestroyed' ? [`${event.cell.col},${event.cell.row}`] : [],
        );
        expect(new Set(broken).size, `種 ${seed} の ${i + 1} tick 目`).toBe(broken.length);
        const cells = game.world.items.map((item) => `${item.cell.col},${item.cell.row}`);
        expect(new Set(cells).size, `種 ${seed} の ${i + 1} tick 目`).toBe(cells.length);
        // この tick に置かれた爆風（残りが BLAST_DURATION - 1）が、壊れたブロックのマスに
        // 2つ以上ある回数。2つの爆風が同じブロックに届いた場面を通ったかを見る。
        for (const key of broken) {
          const fresh = game.world.blasts.filter(
            (blast) =>
              `${blast.cell.col},${blast.cell.row}` === key && blast.remaining === BLAST_DURATION - 1,
          );
          if (fresh.length >= 2) reachedTwice += 1;
        }
      }
      expect(game.match.finished, `種 ${seed}`).toBe(true);
      matches += 1;
    }
    // 前提：アイテムが何度も出て、2つの爆風が同じブロックに届いた。
    // そうでなければ、この確かめは何も見ていない。
    expect(matches).toBeGreaterThan(0);
    expect(dropped).toBeGreaterThan(20);
    expect(reachedTwice).toBeGreaterThan(0);
  }, 120_000);
});
