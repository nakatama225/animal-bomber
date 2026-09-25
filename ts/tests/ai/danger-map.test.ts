import { describe, expect, it } from 'vitest';

import { cellKey, centerOf, type Cell } from '../../src/domain/core/Coord.js';
import { tick } from '../../src/domain/core/Tick.js';
import { detonate } from '../../src/domain/mutations/explode.js';
import { placeBombAt } from '../../src/domain/mutations/bombs.js';
import { addBlast } from '../../src/domain/mutations/explode.js';
import { DangerMap, NEVER } from '../../src/domain/query/DangerMap.js';
import { cellsTouchedBy } from '../../src/domain/query/Hitbox.js';
import { hashWorld } from '../../src/domain/state/WorldState.js';
import { clearBoard, makeWorld } from '../helpers.js';


/** 危険の地図で、いずれ爆風が届くとされたマス。 */
function markedCells(map: DangerMap, world: ReturnType<typeof makeWorld>): Set<string> {
  const marked = new Set<string>();
  for (const { cell } of world.board.cells()) {
    if (map.at(cell) !== NEVER) marked.add(cellKey(cell));
  }
  return marked;
}

describe('危険の地図', () => {
  it('爆風が届くとしたマスが、実際に爆発させたときの爆風と一致する', () => {
    // 見積もりと実際の爆発が食い違うと、CPU は「安全だ」と思って立った所で倒れる。
    // 壊せるブロックが残った盤面で、置く場所と火力を変えて突き合わせる。
    const cases: { cell: Cell; power: number }[] = [
      { cell: { col: 1, row: 1 }, power: 1 },
      { cell: { col: 3, row: 1 }, power: 4 },
      { cell: { col: 1, row: 3 }, power: 13 },
      { cell: { col: 21, row: 15 }, power: 3 },
    ];
    for (const seed of [1, 2, 3]) {
      for (const { cell, power } of cases) {
        const world = makeWorld(seed);
        world.board.set(cell, 'empty');
        const player = world.players[0]!;
        player.power = power;
        const bomb = placeBombAt(world, player, cell)!;

        const expected = markedCells(DangerMap.of(world), world);
        detonate(world, bomb);
        const actual = new Set(world.blasts.map((blast) => cellKey(blast.cell)));
        expect([...actual].sort()).toEqual([...expected].sort());
      }
    }
  });

  it('誘爆を織り込む：遅い爆弾も、早い爆弾の爆風が届けばそのとき爆発する', () => {
    const world = makeWorld();
    clearBoard(world);
    const player = world.players[0]!;
    player.maxBombs = 5;
    player.power = 2;
    const early = placeBombAt(world, player, { col: 1, row: 1 })!;
    const late = placeBombAt(world, player, { col: 3, row: 1 })!;
    early.fuse = tick(10);
    late.fuse = tick(100);

    const map = DangerMap.of(world);
    // 遅い爆弾の爆風だけが届くマスも、早い爆弾の時刻で燃える。
    expect(map.at({ col: 5, row: 1 })).toBe(10);
    expect(map.at({ col: 3, row: 1 })).toBe(10);
  });

  it('逆に、届かない爆弾は巻き込まない', () => {
    // 前の確認が「全部を最小の時刻にしているだけ」で通らないための対照。
    const world = makeWorld();
    clearBoard(world);
    const player = world.players[0]!;
    player.maxBombs = 5;
    player.power = 1;
    const early = placeBombAt(world, player, { col: 1, row: 1 })!;
    const far = placeBombAt(world, player, { col: 5, row: 1 })!;
    early.fuse = tick(10);
    far.fuse = tick(100);
    expect(DangerMap.of(world).at({ col: 6, row: 1 })).toBe(100);
  });

  it('いま出ている爆風のマスは 0、爆弾の無い盤面はすべて安全', () => {
    const world = makeWorld();
    expect(DangerMap.of(world).isSafe({ col: 1, row: 1 })).toBe(true);
    addBlast(world, { col: 1, row: 1 }, 0, true);
    expect(DangerMap.of(world).at({ col: 1, row: 1 })).toBe(0);
  });

  it('まだ置いていない爆弾を足して試算しても、盤面は変わらない', () => {
    const world = makeWorld();
    const before = hashWorld(world);
    const map = DangerMap.of(world, [{ cell: { col: 1, row: 1 }, power: 2, fuse: tick(144) }]);
    expect(map.isSafe({ col: 1, row: 1 })).toBe(false);
    expect(world.bombs).toHaveLength(0);
    expect(hashWorld(world)).toBe(before);
  });
});

describe('体が触れているマス', () => {
  it('マスの中央に立てば1マスだけ', () => {
    expect(cellsTouchedBy(centerOf({ col: 3, row: 1 }))).toEqual([{ col: 3, row: 1 }]);
  });

  it('境目の近くでは隣のマスにもはみ出す', () => {
    // 安全なマスに入った直後に立ち止まると、ここで隣の爆風に当たる。
    const cells = cellsTouchedBy({ x: 3.05, y: 1.5 });
    expect(cells).toEqual([
      { col: 2, row: 1 },
      { col: 3, row: 1 },
    ]);
  });
});
