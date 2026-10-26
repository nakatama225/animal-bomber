import { describe, expect, it } from 'vitest';

import { centerOf } from '../../src/domain/core/Coord.js';
import { blastReach } from '../../src/domain/query/BlastReach.js';
import { bombAt, blastAt, isSolidFor } from '../../src/domain/query/BoardQuery.js';
import { BOMB_FUSE, BLAST_DURATION } from '../../src/domain/rules/tuning.js';
import { detonate } from '../../src/domain/mutations/explode.js';
import { placeBomb } from '../../src/domain/mutations/bombs.js';
import { Simulation } from '../../src/domain/systems/Simulation.js';
import { advance, clearBoard, makeWorld, onlyFor, press } from '../helpers.js';


describe('爆弾を置く', () => {
  it('押し下げた瞬間に1つ置かれる', () => {
    const world = makeWorld();
    advance(world, onlyFor(world, 0, press({ bomb: true })), 1);
    expect(world.bombs).toHaveLength(1);
    expect(world.players[0]!.activeBombs).toBe(1);
  });

  it('押しっぱなしでは2つ目が置かれない', () => {
    // 原型では、押している間じゅう置き続けてしまう不具合が出たことがある。
    const world = makeWorld();
    world.players[0]!.maxBombs = 5;
    advance(world, onlyFor(world, 0, press({ bomb: true })), 60);
    expect(world.bombs).toHaveLength(1);
  });

  it('離して押し直せば2つ目が置かれる', () => {
    const world = makeWorld();
    const player = world.players[0]!;
    player.maxBombs = 5;
    const sim = new Simulation();
    sim.step(world, onlyFor(world, 0, press({ bomb: true })));
    sim.step(world, onlyFor(world, 0, press({})));
    // 同じマスには置けないので、1マス動いてから置く。
    advance(world, onlyFor(world, 0, press({ right: true })), 20, sim);
    sim.step(world, onlyFor(world, 0, press({ bomb: true })));
    expect(world.bombs).toHaveLength(2);
  });

  it('手持ちの上限を超えて置けない', () => {
    const world = makeWorld();
    const player = world.players[0]!;
    player.maxBombs = 1;
    placeBomb(world, player);
    player.position = centerOf({ col: 3, row: 1 });
    placeBomb(world, player);
    expect(world.bombs).toHaveLength(1);
  });

  it('同じマスには2つ置けない', () => {
    const world = makeWorld();
    const player = world.players[0]!;
    player.maxBombs = 5;
    placeBomb(world, player);
    placeBomb(world, player);
    expect(world.bombs).toHaveLength(1);
  });

  it('壊せるブロックの上には置けない', () => {
    const world = makeWorld();
    const player = world.players[0]!;
    world.board.set({ col: 1, row: 1 }, 'soft');
    expect(placeBomb(world, player)).toBeUndefined();
  });
});

describe('置いた爆弾の通り抜け', () => {
  it('置いたプレイヤー自身は、降りるまで通り抜けられる', () => {
    const world = makeWorld();
    const player = world.players[0]!;
    placeBomb(world, player);
    expect(isSolidFor(world, { col: 1, row: 1 }, player)).toBe(false);
  });

  it('足元に置かれたほかのプレイヤーも通り抜けられる', () => {
    // 置いたプレイヤー自身だけを通す形にすると、足元へ置かれた側が
    // その場から動けなくなって詰む。
    const world = makeWorld();
    const owner = world.players[0]!;
    const victim = world.players[1]!;
    victim.position = { ...owner.position };
    placeBomb(world, owner);
    expect(isSolidFor(world, { col: 1, row: 1 }, victim)).toBe(false);
  });

  it('関わりのないプレイヤーには固い', () => {
    const world = makeWorld();
    const owner = world.players[0]!;
    const other = world.players[1]!;
    placeBomb(world, owner);
    expect(isSolidFor(world, { col: 1, row: 1 }, other)).toBe(true);
  });

  it('降りたら固くなり、戻れない', () => {
    const world = makeWorld();
    const player = world.players[0]!;
    player.maxBombs = 2;
    placeBomb(world, player);
    // 右へ1マス以上動いて、爆弾のマスから出る。
    advance(world, onlyFor(world, 0, press({ right: true })), 40);
    expect(isSolidFor(world, { col: 1, row: 1 }, player)).toBe(true);
  });
});

describe('爆発', () => {
  it('導火線が尽きると爆発する', () => {
    const world = makeWorld();
    placeBomb(world, world.players[0]!);
    advance(world, onlyFor(world, 0, press({})), BOMB_FUSE + 1);
    expect(world.bombs).toHaveLength(0);
    expect(blastAt(world, { col: 1, row: 1 })).toBeDefined();
  });

  it('爆風は原型と同じく右・左・下・上の順に伸ばす', () => {
    // この順が爆風の識別子の順と、誘爆した爆弾を積む順を決め、爆風が重なったマスで
    // 当てたプレイヤーを決める（DamageSystem）。4つの向きの位置を全部留める。
    const world = makeWorld();
    clearBoard(world);
    const reach = blastReach(world, { col: 5, row: 5 }, 1);
    expect(reach.arms.map((arm) => arm.cell)).toEqual([
      { col: 6, row: 5 },
      { col: 4, row: 5 },
      { col: 5, row: 6 },
      { col: 5, row: 4 },
    ]);
  });

  it('爆発を知らせるときに、その連鎖で壊したブロックの数も知らせる（ブロックの音を連鎖1回に1回鳴らすため）', () => {
    const world = makeWorld();
    clearBoard(world);
    const player = world.players[0]!;
    player.position = centerOf({ col: 5, row: 5 });
    world.board.set({ col: 6, row: 5 }, 'soft');
    world.board.set({ col: 5, row: 6 }, 'soft');
    placeBomb(world, player);
    const sim = new Simulation();
    const exploded = [];
    for (let t = 0; t <= BOMB_FUSE; t += 1) {
      exploded.push(...sim.step(world, onlyFor(world, 0, press({}))).filter((e) => e.type === 'exploded'));
    }
    expect(exploded).toEqual([{ type: 'exploded', cell: { col: 5, row: 5 }, owner: 0, chained: 1, blocks: 2 }]);
  });

  it('爆発すると手持ちが戻る', () => {
    const world = makeWorld();
    const player = world.players[0]!;
    placeBomb(world, player);
    expect(player.activeBombs).toBe(1);
    advance(world, onlyFor(world, 0, press({})), BOMB_FUSE + 1);
    expect(player.activeBombs).toBe(0);
  });

  it('爆風は火力のぶんだけ伸びる', () => {
    const world = makeWorld();
    clearBoard(world);
    const player = world.players[0]!;
    player.power = 3;
    player.position = centerOf({ col: 5, row: 5 });
    const bomb = placeBomb(world, player)!;
    detonate(world, bomb);
    expect(blastAt(world, { col: 8, row: 5 })).toBeDefined();
    expect(blastAt(world, { col: 9, row: 5 })).toBeUndefined();
  });

  it('壊せない壁で止まり、その先へは届かない', () => {
    const world = makeWorld();
    clearBoard(world);
    const player = world.players[0]!;
    player.power = 5;
    // 柱が立つのは列も行も偶数のマス。(4,5) の真上 (4,4) が柱になる。
    player.position = centerOf({ col: 4, row: 5 });
    const bomb = placeBomb(world, player)!;
    detonate(world, bomb);
    expect(world.board.at({ col: 4, row: 4 })).toBe('hard');
    expect(blastAt(world, { col: 4, row: 4 })).toBeUndefined();
    expect(blastAt(world, { col: 4, row: 3 })).toBeUndefined();
    // 柱の無い横方向へは伸びている。
    expect(blastAt(world, { col: 5, row: 5 })).toBeDefined();
  });

  it('壊せるブロックを壊し、そのマスで止まる', () => {
    const world = makeWorld();
    clearBoard(world);
    const player = world.players[0]!;
    player.power = 5;
    player.position = centerOf({ col: 5, row: 5 });
    world.board.set({ col: 5, row: 7 }, 'soft');
    const bomb = placeBomb(world, player)!;
    const result = detonate(world, bomb);
    expect(world.board.at({ col: 5, row: 7 })).toBe('empty');
    expect(result.destroyed).toHaveLength(1);
    // ブロックのマスまでは爆風が届くが、その先へは伸びない。
    expect(blastAt(world, { col: 5, row: 7 })).toBeDefined();
    expect(blastAt(world, { col: 5, row: 8 })).toBeUndefined();
  });

  it('ブロックを壊すのは連鎖をすべて処理したあと', () => {
    // 途中で壊すと、その先へ爆風が伸びるかどうかが処理の順序で変わる。
    const world = makeWorld();
    clearBoard(world);
    const player = world.players[0]!;
    player.power = 2;
    player.maxBombs = 2;
    player.position = centerOf({ col: 5, row: 5 });
    world.board.set({ col: 5, row: 7 }, 'soft');
    const first = placeBomb(world, player)!;
    player.position = centerOf({ col: 5, row: 9 });
    placeBomb(world, player);

    detonate(world, first);
    // (5,7) のブロックは壊れるが、その向こうの爆弾は
    // 爆風が届いていないので連鎖していない。
    expect(world.board.at({ col: 5, row: 7 })).toBe('empty');
    expect(blastAt(world, { col: 5, row: 8 })).toBeUndefined();
  });

  it('2つの爆弾の爆風が同じブロックに届いても、壊すのは1回', () => {
    // 壊すたびにアイテムを抽選するので、2回壊すと同じマスにアイテムが
    // 2つ出うる（段階 3 から 2026-10-04 まで、この版はそうなっていた）。
    // 原型は、ブロックを壊す関数の入口で「もう壊れていれば帰る」ので1回だけ。
    const world = makeWorld();
    clearBoard(world);
    const player = world.players[0]!;
    player.power = 3;
    player.maxBombs = 2;
    player.position = centerOf({ col: 5, row: 5 });
    const first = placeBomb(world, player)!;
    player.position = centerOf({ col: 5, row: 6 });
    placeBomb(world, player);
    const block = { col: 5, row: 8 };
    world.board.set(block, 'soft');

    // 先の爆弾の爆風は、あとの爆弾を巻き込んで (5,8) で止まる。
    // あとの爆弾の爆風も (5,8) で止まる。
    const before = world.rng.calls;
    const result = detonate(world, first);
    expect(result.chained).toBe(2);
    expect(result.destroyed).toEqual([block]);
    expect(result.events.filter((event) => event.type === 'blockDestroyed')).toHaveLength(1);
    // 抽選1回で乱数を取り出すのは、出るかで1回、出るなら種類で1回まで（2回抽選すると、この場面では3回）。
    expect(world.rng.calls - before).toBeLessThanOrEqual(2);
    const itemsOnBlock = world.items.filter(
      (item) => item.cell.col === block.col && item.cell.row === block.row,
    );
    expect(itemsOnBlock.length).toBeLessThanOrEqual(1);
  });
});

describe('誘爆', () => {
  it('爆風に触れた爆弾も爆発する', () => {
    const world = makeWorld();
    clearBoard(world);
    const player = world.players[0]!;
    player.power = 3;
    player.maxBombs = 2;
    player.position = centerOf({ col: 5, row: 5 });
    const first = placeBomb(world, player)!;
    player.position = centerOf({ col: 7, row: 5 });
    placeBomb(world, player);

    const result = detonate(world, first);
    expect(result.chained).toBe(2);
    expect(world.bombs).toHaveLength(0);
  });

  it('連鎖は同じ爆弾を二度数えない', () => {
    // 同じ爆弾へ複数の経路から爆風が届くことがある。
    const world = makeWorld();
    clearBoard(world);
    const player = world.players[0]!;
    player.power = 4;
    player.maxBombs = 4;
    for (const cell of [
      { col: 5, row: 5 },
      { col: 7, row: 5 },
      { col: 7, row: 7 },
      { col: 5, row: 7 },
    ]) {
      player.position = centerOf(cell);
      placeBomb(world, player);
    }
    const result = detonate(world, world.bombs[0]!);
    expect(result.chained).toBe(4);
    expect(player.activeBombs).toBe(0);
  });

  it('連鎖のあとも手持ちが増えすぎない', () => {
    const world = makeWorld();
    clearBoard(world);
    const player = world.players[0]!;
    player.power = 3;
    player.maxBombs = 3;
    for (const cell of [
      { col: 5, row: 5 },
      { col: 7, row: 5 },
    ]) {
      player.position = centerOf(cell);
      placeBomb(world, player);
    }
    detonate(world, world.bombs[0]!);
    expect(player.activeBombs).toBe(0);
  });
});

describe('爆風の寿命', () => {
  it('時間が経つと消える', () => {
    const world = makeWorld();
    placeBomb(world, world.players[0]!);
    advance(world, onlyFor(world, 0, press({})), BOMB_FUSE + 1);
    expect(world.blasts.length).toBeGreaterThan(0);
    advance(world, onlyFor(world, 0, press({})), BLAST_DURATION + 1);
    expect(world.blasts).toHaveLength(0);
  });
});

describe('置いた爆弾の問い合わせ', () => {
  it('置いたマスから取得できる', () => {
    const world = makeWorld();
    placeBomb(world, world.players[0]!);
    expect(bombAt(world, { col: 1, row: 1 })).toBeDefined();
    expect(bombAt(world, { col: 2, row: 1 })).toBeUndefined();
  });
});
