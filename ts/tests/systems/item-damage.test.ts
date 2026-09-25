import { describe, expect, it } from 'vitest';

import { centerOf } from '../../src/domain/core/Coord.js';
import type { SimEvent } from '../../src/domain/events/SimEvent.js';
import { MAX_BOMBS, MAX_POWER, MAX_SHOES } from '../../src/domain/rules/tuning.js';
import { itemEffectTicks, POOP_STACK_LIMIT } from '../../src/domain/rules/items.js';
import { powerOf, speedOf } from '../../src/domain/state/PlayerState.js';
import { detonate } from '../../src/domain/systems/BlastSystem.js';
import { placeBomb } from '../../src/domain/systems/BombSystem.js';
import { applyItem, spitPowerUp } from '../../src/domain/systems/ItemSystem.js';
import { Simulation } from '../../src/domain/systems/Simulation.js';
import { Presenter } from '../../src/presentation/Presenter.js';
import { advance, makeWorld, onlyFor, press } from '../helpers.js';

describe('アイテムの効果', () => {
  it('爆弾・火力・靴は上限で止まる', () => {
    const world = makeWorld();
    const player = world.players[0]!;
    for (let i = 0; i < 40; i += 1) {
      applyItem(world, player, 'bomb');
      applyItem(world, player, 'fire');
      applyItem(world, player, 'shoe');
    }
    expect(player.maxBombs).toBe(MAX_BOMBS);
    expect(player.power).toBe(MAX_POWER);
    expect(player.shoes).toBe(MAX_SHOES);
  });

  it('たまねぎを踏むと滑りが止まる', () => {
    // 滑りながら泣いていると、どちらの動きになるか読めなくなる。
    const world = makeWorld();
    const player = world.players[0]!;
    applyItem(world, player, 'banana');
    expect(player.effects.has('slide')).toBe(true);
    applyItem(world, player, 'onion');
    expect(player.effects.has('slide')).toBe(false);
    expect(player.effects.has('stun')).toBe(true);
  });

  it('悪い状態は重ねると伸びる', () => {
    // 上書きにすると、何個踏んでも1つぶんの時間で済んでしまい、
    // 踏むコストが頭打ちになる。
    const world = makeWorld();
    const player = world.players[0]!;
    player.effects.add('slow', itemEffectTicks(4), itemEffectTicks(4 * POOP_STACK_LIMIT));
    const first = player.effects.remaining('slow');
    player.effects.add('slow', itemEffectTicks(4), itemEffectTicks(4 * POOP_STACK_LIMIT));
    expect(player.effects.remaining('slow')).toBeGreaterThan(first);
  });

  it('重ねがけには上限がある', () => {
    const world = makeWorld();
    const player = world.players[0]!;
    const base = itemEffectTicks(4);
    const cap = itemEffectTicks(4 * POOP_STACK_LIMIT);
    for (let i = 0; i < 20; i += 1) player.effects.add('slow', base, cap);
    expect(player.effects.remaining('slow')).toBe(cap);
  });

  it('時間が経つと効果が切れる', () => {
    const world = makeWorld();
    const player = world.players[0]!;
    player.effects.add('slow', itemEffectTicks(1), itemEffectTicks(3));
    advance(world, onlyFor(world, 0, press({})), 70);
    expect(player.effects.has('slow')).toBe(false);
  });
});

describe('悪い状態の作用', () => {
  it('超スローで遅くなる', () => {
    const world = makeWorld();
    const player = world.players[0]!;
    const normal = speedOf(player);
    player.effects.add('slow', itemEffectTicks(4), itemEffectTicks(12));
    expect(speedOf(player)).toBeLessThan(normal);
  });

  it('超スローの上にとまれないを重ねても、超スローは効き続ける', () => {
    // 「とまれない」は速度に下限を敷く効果。下限に超スローの倍率を
    // かけないと、後から踏んだ悪い状態が前のものを打ち消して
    // **速くなる**という逆転が起きる。
    const world = makeWorld();
    const runawayOnly = world.players[0]!;
    const both = world.players[1]!;
    runawayOnly.effects.add('runaway', itemEffectTicks(4), itemEffectTicks(12));
    both.effects.add('slow', itemEffectTicks(4), itemEffectTicks(12));
    both.effects.add('runaway', itemEffectTicks(4), itemEffectTicks(12));
    expect(speedOf(both)).toBeLessThan(speedOf(runawayOnly));
  });

  it('とまれないは速度の下限を敷く', () => {
    // 前の確認が「重ねるほど遅い」だけで通ってしまわないための対照。
    const world = makeWorld();
    const plain = world.players[0]!;
    const runaway = world.players[1]!;
    runaway.effects.add('runaway', itemEffectTicks(4), itemEffectTicks(12));
    expect(speedOf(runaway)).toBeGreaterThan(speedOf(plain));
  });

  it('泣いていると動けない', () => {
    const world = makeWorld();
    const player = world.players[0]!;
    player.effects.add('stun', itemEffectTicks(3), itemEffectTicks(9));
    const before = { ...player.position };
    advance(world, onlyFor(world, 0, press({ right: true })), 30);
    expect(player.position).toEqual(before);
  });

  it('そうさ反転で逆へ進む', () => {
    const world = makeWorld();
    const player = world.players[0]!;
    // 左右が開けたマスへ置く。行が奇数なら柱は無い。
    for (const col of [3, 4, 5, 6, 7]) world.board.set({ col, row: 5 }, 'empty');
    player.position = centerOf({ col: 5, row: 5 });
    player.effects.add('reverse', itemEffectTicks(5), itemEffectTicks(15));
    const before = player.position.x;
    advance(world, onlyFor(world, 0, press({ right: true })), 20);
    expect(player.position.x).toBeLessThan(before);
    expect(player.facing).toBe('left');
  });

  it('滑っている間は手を離しても進む', () => {
    const world = makeWorld();
    const player = world.players[0]!;
    player.facing = 'right';
    player.effects.add('slide', itemEffectTicks(3), itemEffectTicks(9));
    const before = player.position.x;
    advance(world, onlyFor(world, 0, press({})), 20);
    expect(player.position.x).toBeGreaterThan(before);
  });

  it('壁にぶつかると滑りが終わる', () => {
    const world = makeWorld();
    const player = world.players[0]!;
    player.facing = 'left'; // 左は外周の壁
    player.effects.add('slide', itemEffectTicks(3), itemEffectTicks(9));
    advance(world, onlyFor(world, 0, press({})), 5);
    expect(player.effects.has('slide')).toBe(false);
  });

  it('爆弾おけない状態では置けない', () => {
    const world = makeWorld();
    const player = world.players[0]!;
    player.effects.add('nobomb', itemEffectTicks(6), itemEffectTicks(18));
    advance(world, onlyFor(world, 0, press({ bomb: true })), 1);
    expect(world.bombs).toHaveLength(0);
  });

  it('勝手に設置は、爆弾おけないより優先される', () => {
    // 2つが重なったときにどちらが勝つかを決めておかないと、
    // 組み合わせで挙動が読めなくなる。
    const world = makeWorld();
    const player = world.players[0]!;
    player.effects.add('nobomb', itemEffectTicks(6), itemEffectTicks(18));
    player.effects.add('autobomb', itemEffectTicks(4), itemEffectTicks(12));
    advance(world, onlyFor(world, 0, press({})), 1);
    expect(world.bombs).toHaveLength(1);
  });

  it('爆風1マスの状態では火力が落ちる', () => {
    const world = makeWorld();
    const player = world.players[0]!;
    player.power = 8;
    player.effects.add('weak', itemEffectTicks(8), itemEffectTicks(24));
    expect(powerOf(player)).toBe(1);
  });
});

describe('アイテムの焼却と抽選の順序', () => {
  it('爆風に触れたアイテムは焼ける', () => {
    const world = makeWorld();
    const player = world.players[0]!;
    world.items.push({ id: world.ids.take(), cell: { col: 3, row: 1 }, kind: 'fire' });
    player.power = 3;
    const bomb = placeBomb(world, player)!;
    const result = detonate(world, bomb);
    expect(result.events.some((e) => e.type === 'itemBurned')).toBe(true);
    expect(world.items.some((item) => item.cell.col === 3 && item.cell.row === 1)).toBe(false);
  });

  it('いま壊した箱から出たアイテムは焼けない', () => {
    // 焼却より先にブロックを壊すと、出たアイテムを同じ爆風で
    // 即座に焼いてしまい、アイテムが一生出てこなくなる。
    const world = makeWorld();
    const player = world.players[0]!;
    player.power = 6;
    // 周囲を壊せるブロックで囲み、確実に何個か壊す。
    for (const cell of [
      { col: 3, row: 1 },
      { col: 1, row: 3 },
    ]) {
      world.board.set(cell, 'soft');
    }
    const bomb = placeBomb(world, player)!;
    const result = detonate(world, bomb);
    const dropped = result.events.filter((e) => e.type === 'itemDropped');
    const burned = result.events.filter((e) => e.type === 'itemBurned');
    // 落ちたものが同じ処理の中で焼かれていない。
    expect(burned).toHaveLength(0);
    for (const event of dropped) {
      if (event.type !== 'itemDropped') continue;
      expect(
        world.items.some(
          (item) => item.cell.col === event.cell.col && item.cell.row === event.cell.row,
        ),
      ).toBe(true);
    }
  });
});

describe('被弾', () => {
  it('爆風に当たると体力が減る', () => {
    const world = makeWorld();
    const player = world.players[0]!;
    const before = player.hp;
    placeBomb(world, player);
    advance(world, onlyFor(world, 0, press({})), 200);
    expect(player.hp).toBeLessThan(before);
  });

  it('無敵の間は続けて当たらない', () => {
    const world = makeWorld();
    const player = world.players[0]!;
    player.hp = 100;
    placeBomb(world, player);
    advance(world, onlyFor(world, 0, press({})), 200);
    // 爆風は数十 tick 残るが、減るのは1回ぶんだけ。
    expect(player.hp).toBe(98);
  });

  it('体力が尽きると倒れる', () => {
    const world = makeWorld();
    const player = world.players[0]!;
    player.hp = 2;
    placeBomb(world, player);
    advance(world, onlyFor(world, 0, press({})), 200);
    expect(player.life).toBe('dead');
  });

  it('当たった瞬間に相手を控える', () => {
    // 倒れてから爆風の持ち主を引き直すと、その頃には爆風が消えていて
    // 原因が分からなくなる。
    const world = makeWorld();
    const player = world.players[0]!;
    placeBomb(world, player);
    advance(world, onlyFor(world, 0, press({})), 200);
    expect(player.lastHitBy).toBe(0);
  });

  it('被弾するとアイテムを1つ吐き出す', () => {
    const world = makeWorld();
    const player = world.players[0]!;
    const before = world.items.length;
    const events = spitPowerUp(world, player);
    expect(events).toHaveLength(1);
    expect(world.items.length).toBe(before + 1);
  });
});

describe('イベントの受け取り', () => {
  it('受け取らなければ何も起きない', () => {
    // 音を消すフラグもテスト用のモードも無い。呼ばなければ鳴らない。
    const world = makeWorld();
    const sim = new Simulation();
    const events = sim.step(world, onlyFor(world, 0, press({ bomb: true })));
    expect(events.some((e) => e.type === 'bombPlaced')).toBe(true);
    // ここで presenter.consume を呼ばない。それだけで無音になる。
  });

  it('すべての種類を扱える', () => {
    // 扱い漏れがあれば assertNever が投げる。
    const played: string[] = [];
    const presenter = new Presenter({
      play: (name) => {
        played.push(name);
      },
    });
    const all: SimEvent[] = [
      { type: 'bombPlaced', cell: { col: 1, row: 1 }, owner: 0 },
      { type: 'exploded', cell: { col: 1, row: 1 }, owner: 0, chained: 2 },
      { type: 'blockDestroyed', cell: { col: 2, row: 1 } },
      { type: 'itemDropped', cell: { col: 2, row: 1 }, kind: 'fire' },
      { type: 'itemTaken', cell: { col: 2, row: 1 }, kind: 'fire', taker: 0 },
      { type: 'itemBurned', cell: { col: 2, row: 1 }, kind: 'fire' },
      { type: 'effectApplied', target: 0, effect: 'slow' },
      { type: 'playerHurt', target: 0, by: 1, amount: 2 },
      { type: 'playerDown', target: 0, by: 1 },
    ];
    expect(() => presenter.consume(all)).not.toThrow();
    expect(played.length).toBeGreaterThan(0);
  });

  it('知らない種類が来たら止まる', () => {
    const presenter = new Presenter();
    const bogus = { type: 'そんなイベントはない' } as unknown as SimEvent;
    expect(() => presenter.consume([bogus])).toThrow();
  });
});

describe('アイテムを拾う', () => {
  it('足元のアイテムを拾う', () => {
    const world = makeWorld();
    const player = world.players[0]!;
    player.position = centerOf({ col: 1, row: 1 });
    world.items.push({ id: world.ids.take(), cell: { col: 1, row: 1 }, kind: 'fire' });
    const before = player.power;
    advance(world, onlyFor(world, 0, press({})), 1);
    expect(player.power).toBe(before + 1);
    expect(world.items).toHaveLength(0);
  });
});
