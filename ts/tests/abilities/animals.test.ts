import { describe, expect, it } from 'vitest';

import { abilityOf } from '../../src/domain/abilities/registry.js';
import { cellOf, centerOf, sameCell } from '../../src/domain/core/Coord.js';
import { tick } from '../../src/domain/core/Tick.js';
import { placeBomb, placeBombAt } from '../../src/domain/mutations/bombs.js';
import { applyItem } from '../../src/domain/mutations/items.js';
import { isSolidFor } from '../../src/domain/query/BoardQuery.js';
import { isBlastProof, isInvulnerable, isUntouchable } from '../../src/domain/state/PlayerState.js';
import { Simulation } from '../../src/domain/systems/Simulation.js';
import { advance, clearBoard, makeWorld, onlyFor, press } from '../helpers.js';
import { SlimeBombActor } from '../../src/domain/abilities/frog/SlimeBombActor.js';

/** プレイヤー0をその動物にした世界。 */
function worldWith(animal: string): ReturnType<typeof makeWorld> {
  return makeWorld(2468, [animal, 'rabbit']);
}

/** 技のボタンを押して離す（通常技）。 */
function tap(world: ReturnType<typeof makeWorld>, sim = new Simulation()): void {
  sim.step(world, onlyFor(world, 0, press({})));
  sim.step(world, onlyFor(world, 0, press({ action: true })));
  sim.step(world, onlyFor(world, 0, press({})));
}

/** 技のボタンを長押ししてとくぎを出す。 */
function hold(world: ReturnType<typeof makeWorld>, animal: string): void {
  const sim = new Simulation();
  world.players[0]!.specialCharges = 1;
  sim.step(world, onlyFor(world, 0, press({})));
  for (let i = 0; i < abilityOf(animal).holdTicks; i += 1) {
    sim.step(world, onlyFor(world, 0, press({ action: true })));
  }
}

describe('うさぎ', () => {
  it('1マス越えて跳ぶ', () => {
    const world = worldWith('rabbit');
    const player = world.players[0]!;
    player.position = centerOf({ col: 1, row: 1 });
    player.facing = 'right';
    world.board.set({ col: 2, row: 1 }, 'soft'); // 越える対象
    world.board.set({ col: 3, row: 1 }, 'empty'); // 着地点
    tap(world);
    expect(player.position.x).toBeCloseTo(3.5);
  });

  it('2マス先が塞がっていれば1マス先へ跳び、どちらも塞がっていれば跳ばない（原型の hop）', () => {
    // 原型：(3,7) から右へ。2マス先が壊せるブロックか爆弾なら (4,7)、1マス先も塞がっていれば動かない。
    const hopFrom = (setup: (world: ReturnType<typeof makeWorld>) => void): number => {
      const world = worldWith('rabbit');
      clearBoard(world);
      const player = world.players[0]!;
      player.position = centerOf({ col: 3, row: 7 });
      player.facing = 'right';
      setup(world);
      tap(world);
      return player.position.x;
    };
    expect(hopFrom(() => {})).toBe(5.5);
    expect(hopFrom((world) => world.board.set({ col: 5, row: 7 }, 'soft'))).toBe(4.5);
    expect(
      hopFrom((world) => {
        placeBombAt(world, world.players[1]!, { col: 5, row: 7 })!.fuse = tick(999);
      }),
    ).toBe(4.5);
    expect(
      hopFrom((world) => {
        world.board.set({ col: 5, row: 7 }, 'soft');
        world.board.set({ col: 4, row: 7 }, 'soft');
      }),
    ).toBe(3.5);
  });

  it('続けて跳べない', () => {
    // 連打で壁抜けになってしまうため、間隔を置く。
    const world = worldWith('rabbit');
    const player = world.players[0]!;
    player.facing = 'right';
    for (const col of [2, 3, 4, 5]) world.board.set({ col, row: 1 }, 'empty');
    tap(world);
    const afterFirst = player.position.x;
    tap(world);
    expect(player.position.x).toBe(afterFirst);
  });

  it('とくぎで周囲が埋まる', () => {
    const world = worldWith('rabbit');
    hold(world, 'rabbit');
    advance(world, onlyFor(world, 0, press({})), 130);
    expect(world.items.filter((item) => item.scatteredBy === 0).length).toBeGreaterThan(0);
  });

  it('撒いたプレイヤー自身は踏んでも効かず、撒いたものも残る', () => {
    // 自分の周りに壁を作って立てこもる使い方が成り立たなくなる。
    const world = worldWith('rabbit');
    const player = world.players[0]!;
    hold(world, 'rabbit');
    advance(world, onlyFor(world, 0, press({})), 130);
    const harmful = ['reverse', 'nobomb', 'runaway', 'weak', 'autobomb', 'slow'] as const;
    expect(harmful.filter((kind) => player.effects.has(kind))).toEqual([]);
    expect(world.items.some((item) => sameCell(item.cell, cellOf(player.position)))).toBe(true);
  });
});

describe('もぐら', () => {
  it('壊せるブロックを通り抜けられる', () => {
    const world = worldWith('mole');
    const player = world.players[0]!;
    world.board.set({ col: 3, row: 3 }, 'soft');
    expect(isSolidFor(world, { col: 3, row: 3 }, player, abilityOf('mole').passesThrough)).toBe(
      false,
    );
  });

  it('壊せない壁は通れない', () => {
    const world = worldWith('mole');
    const player = world.players[0]!;
    expect(isSolidFor(world, { col: 0, row: 0 }, player, abilityOf('mole').passesThrough)).toBe(
      true,
    );
  });

  it('ほかのプレイヤーの爆弾の隣のブロックは通れない', () => {
    // これが無いと、爆弾で追い込んでも毎回壁抜けで逃げられ、
    // 追い詰めるという行為が成立しなくなる。
    const world = worldWith('mole');
    const mole = world.players[0]!;
    const other = world.players[1]!;
    world.board.set({ col: 5, row: 3 }, 'soft');
    other.position = centerOf({ col: 5, row: 4 });
    world.board.set({ col: 5, row: 4 }, 'empty');
    placeBomb(world, other);
    expect(isSolidFor(world, { col: 5, row: 3 }, mole, abilityOf('mole').passesThrough)).toBe(
      true,
    );
  });

  it('とくぎで落とし穴ができ、踏んだ相手が止まる', () => {
    const world = worldWith('mole');
    const mole = world.players[0]!;
    const other = world.players[1]!;
    hold(world, 'mole');
    advance(world, onlyFor(world, 0, press({})), 100);
    expect(world.actors.some((a) => a.kind === 'pit')).toBe(true);
    // 相手が同じマスへ来ると止まる。
    other.position = { ...mole.position };
    advance(world, onlyFor(world, 0, press({})), 2);
    expect(other.effects.has('pitfall')).toBe(true);
  });

  it('ポン押しでも、チキンがあれば穴を掘り始める（通常技の無い動物。原型の doAction）', () => {
    // 原型：もぐらでチキンを持って技のボタンを押すと、その場で掘り始める。
    const world = worldWith('mole');
    clearBoard(world);
    const mole = world.players[0]!;
    mole.specialCharges = 1;
    const sim = new Simulation();
    sim.step(world, onlyFor(world, 0, press({})));
    sim.step(world, onlyFor(world, 0, press({ action: true })));
    const events = sim.step(world, onlyFor(world, 0, press({})));
    expect(mole.action?.kind).toBe('dig');
    expect(mole.specialCharges).toBe(0);
    expect(events).toContainEqual({ type: 'techniqueUsed', player: 0, special: true });
  });

  it('対照：チキンが無ければ、ポン押しでは何も起きない。泣いている間のポン押しでは掘らず、チキンも減らない', () => {
    const tapWith = (charges: number, stunned: boolean): { action: string | null; charges: number } => {
      const world = worldWith('mole');
      clearBoard(world);
      const mole = world.players[0]!;
      mole.specialCharges = charges;
      if (stunned) mole.effects.add('stun', tick(120), tick(120));
      tap(world);
      return { action: mole.action?.kind ?? null, charges: mole.specialCharges };
    };
    expect(tapWith(0, false)).toEqual({ action: null, charges: 0 });
    expect(tapWith(1, true)).toEqual({ action: null, charges: 1 });
  });

  it('掘ったプレイヤーは自分の穴で止まらない', () => {
    const world = worldWith('mole');
    const mole = world.players[0]!;
    hold(world, 'mole');
    advance(world, onlyFor(world, 0, press({})), 120);
    expect(mole.effects.has('pitfall')).toBe(false);
  });
});

describe('きつね', () => {
  it('爆弾を1個多く持って始まる', () => {
    expect(worldWith('fox').players[0]!.maxBombs).toBe(2);
  });

  it('正面へ一列に置く', () => {
    const world = worldWith('fox');
    const player = world.players[0]!;
    player.maxBombs = 3;
    player.facing = 'right';
    for (const col of [2, 3, 4, 5]) world.board.set({ col, row: 1 }, 'empty');
    tap(world);
    expect(world.bombs.length).toBe(3);
  });

  it('足元ではなく1マス前から並べる', () => {
    // 足元から置くと自分が列の先頭に埋まって逃げ場を失う。
    const world = worldWith('fox');
    const player = world.players[0]!;
    player.facing = 'right';
    for (const col of [2, 3] ) world.board.set({ col, row: 1 }, 'empty');
    tap(world);
    expect(world.bombs.some((b) => b.cell.col === 1 && b.cell.row === 1)).toBe(false);
    expect(world.bombs.some((b) => b.cell.col === 2 && b.cell.row === 1)).toBe(true);
  });

  it('とくぎで追いかける炎が出る', () => {
    const world = worldWith('fox');
    hold(world, 'fox');
    expect(world.actors.some((a) => a.kind === 'foxfire')).toBe(true);
  });

  it('放つ瞬間に跳び上がり、その間は爆風が当たらない（被弾のあとの無敵とは別で、点滅しない）', () => {
    // 撃ったあと無防備になると、相手が近いほど使えない技になる。
    const world = worldWith('fox');
    hold(world, 'fox');
    const fox = world.players[0]!;
    expect(fox.effects.has('leap')).toBe(true);
    expect(isBlastProof(fox)).toBe(true);
    expect(isUntouchable(fox)).toBe(true);
    expect(isInvulnerable(fox, world.now)).toBe(false);
  });
});

describe('かえる', () => {
  it('アイテムの効果が2倍になる', () => {
    const world = worldWith('frog');
    const player = world.players[0]!;
    const before = player.power;
    applyItem(world, player, 'fire', abilityOf('frog').itemMultiplier);
    expect(player.power).toBe(before + 2);
  });

  it('悪いアイテムの効果も2倍になる', () => {
    // 良いものだけ2倍にすると、短所の無い動物になってしまう。
    const world = worldWith('frog');
    const plain = world.players[1]!;
    const frog = world.players[0]!;
    applyItem(world, plain, 'onion', 1);
    applyItem(world, frog, 'onion', 2);
    expect(frog.effects.remaining('stun')).toBeGreaterThan(plain.effects.remaining('stun'));
  });

  it('舌で離れたアイテムを引き寄せる', () => {
    const world = worldWith('frog');
    const player = world.players[0]!;
    player.facing = 'right';
    for (const col of [2, 3, 4] ) world.board.set({ col, row: 1 }, 'empty');
    world.items.push({ id: world.ids.take(), cell: { col: 4, row: 1 }, kind: 'fire' });
    const before = player.power;
    tap(world);
    // 掴んだアイテムは舌が戻りきってから効く（3 マス先なら伸ばし始めて 46 tick 目）。
    advance(world, onlyFor(world, 0, press({})), 60);
    expect(player.power).toBeGreaterThan(before);
    expect(world.items).toHaveLength(0);
  });

  it('とくぎで跳ね回る爆弾が出る', () => {
    const world = worldWith('frog');
    hold(world, 'frog');
    expect(world.actors.some((a) => a.kind === 'slime')).toBe(true);
  });

  it('跳ね回ったあと爆発する', () => {
    const world = worldWith('frog');
    hold(world, 'frog');
    advance(world, onlyFor(world, 0, press({})), 400);
    expect(world.actors.some((a) => a.kind === 'slime')).toBe(false);
  });
});

describe('飛び道具と撒く技の置き場所', () => {
  it('跳ね回る爆弾は、正面3マス先の空きマスに落ちる', () => {
    const world = worldWith('frog');
    clearBoard(world);
    const frog = world.players[0]!;
    frog.position = centerOf({ col: 1, row: 1 });
    frog.facing = 'right';
    const slime = SlimeBombActor.launch(world, frog);
    expect(slime.cell).toEqual({ col: 4, row: 1 });
  });

  it('盤面の端で外側を向いて投げても、盤面の外には落ちない', () => {
    // 3マス先に決め打ちすると外に落ち、跳ねる先も無いまま不発で終わる。
    const world = worldWith('frog');
    clearBoard(world);
    const frog = world.players[0]!;
    frog.position = centerOf({ col: 1, row: 1 });
    frog.facing = 'up';
    const slime = SlimeBombActor.launch(world, frog);
    expect(world.board.inBounds(slime.cell)).toBe(true);
    expect(world.board.at(slime.cell)).toBe('empty');
  });

  it('撒く技は、アイテムのあるマスを避ける', () => {
    // 重なると、踏むと損をするうんこがアイテムの下に隠れる。
    const world = worldWith('rabbit');
    clearBoard(world);
    const rabbit = world.players[0]!;
    rabbit.position = centerOf({ col: 3, row: 3 });
    world.items.push({ id: world.ids.take(), cell: { col: 4, row: 3 }, kind: 'fire' });
    hold(world, 'rabbit');
    advance(world, onlyFor(world, 0, press({})), 150);
    const onItem = world.items.filter((item) => item.cell.col === 4 && item.cell.row === 3);
    expect(onItem.map((item) => item.kind)).toEqual(['fire']);
    expect(world.items.some((item) => item.scatteredBy !== undefined)).toBe(true);
  });
});

describe('とくぎの長押しの長さ（原型 specialHoldOf）', () => {
  it('ぞうだけ 1.5 秒、ほかは 0.5 秒', () => {
    // 原型は動物の holdTime（ぞうだけ 1.5）か、無ければ SPECIAL_HOLD（0.5 秒）。
    // 画面なしで押し続けると、ぞうは 91 フレーム目、うさぎ・きつねは 31 フレーム目に出る。
    const ticks = Object.fromEntries(
      ['rabbit', 'elephant', 'mole', 'fox', 'frog'].map((animal) => [animal, abilityOf(animal).holdTicks]),
    );
    expect(ticks).toEqual({ rabbit: 30, elephant: 90, mole: 30, fox: 30, frog: 30 });
  });
});
