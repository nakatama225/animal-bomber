import { describe, expect, it } from 'vitest';

import { ChargeAction } from '../../src/domain/abilities/elephant/ChargeAction.js';
import { TongueAction } from '../../src/domain/abilities/frog/TongueAction.js';
import { PitAction } from '../../src/domain/abilities/mole/PitAction.js';
import { centerOf, sameCell, type Cell } from '../../src/domain/core/Coord.js';
import type { SimEvent } from '../../src/domain/events/SimEvent.js';
import { AUTOBOMB_INTERVAL, MAX_BOMBS, MAX_POWER, MAX_SHOES } from '../../src/domain/rules/tuning.js';
import { itemEffectTicks, POOP_LIFETIME, POOP_STACK_LIMIT, type ItemKind } from '../../src/domain/rules/items.js';
import type { WorldState } from '../../src/domain/state/WorldState.js';
import { OUT } from '../../src/domain/state/Life.js';
import { isAlive, powerOf, speedOf, type PlayerState } from '../../src/domain/state/PlayerState.js';
import { NEGIBON_CUTOFF } from '../../src/domain/rules/negibon.js';
import { tick } from '../../src/domain/core/Tick.js';
import { addBlast, detonate } from '../../src/domain/mutations/explode.js';
import { placeBomb } from '../../src/domain/mutations/bombs.js';
import { applyItem, placedItem, spitPowerUp } from '../../src/domain/mutations/items.js';
import { DamageSystem } from '../../src/domain/systems/DamageSystem.js';
import { Simulation } from '../../src/domain/systems/Simulation.js';
import { Presenter } from '../../src/presentation/Presenter.js';
import { advance, clearBoard, makeWorld, onlyFor, press } from '../helpers.js';

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

  it('バナナとたまねぎは、かかっている間に拾い直しても足さず、残りを3秒に戻す（原型の applyItem）', () => {
    const world = makeWorld();
    const player = world.players[0]!;
    for (const [kind, effect] of [
      ['banana', 'slide'],
      ['onion', 'stun'],
    ] as const) {
      player.effects.clear(effect);
      applyItem(world, player, kind);
      // 残りを減らしてから拾い直す（どちらも3秒）。
      player.effects.set(effect, tick(100));
      applyItem(world, player, kind);
      expect(player.effects.remaining(effect), kind).toBe(itemEffectTicks(3));
      applyItem(world, player, kind);
      expect(player.effects.remaining(effect), kind).toBe(itemEffectTicks(3));
    }
  });

  it('効果が2倍の動物は、バナナとたまねぎも2倍の長さに置き換える（足さない）', () => {
    const world = makeWorld(1234, ['frog', 'rabbit']);
    const player = world.players[0]!;
    for (const [kind, effect] of [
      ['banana', 'slide'],
      ['onion', 'stun'],
    ] as const) {
      applyItem(world, player, kind, 2);
      applyItem(world, player, kind, 2);
      expect(player.effects.remaining(effect), kind).toBe(itemEffectTicks(6));
    }
  });

  it('うんこの悪い状態は重ねると伸びる', () => {
    // 上書きにすると、何個踏んでも1つぶんの時間で済んでしまい、
    // 踏むコストが頭打ちになる（原型も 2026-08-23 から足す形）。
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

  it('超スローの上にとまれないを重ねても、超スローは適用され続ける', () => {
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
});

/*
 * 滑っている間の動き（原型の humanUpdate の滑りの枝）。期待値は、原型を画面なしで動かして
 * 同じ場面で測った位置（どれも (3,7) の中央から右向きに滑り始める）。
 */
describe('滑っている間の動き', () => {
  function slideArena(animal: string): { world: WorldState; player: PlayerState } {
    const world = makeWorld(5, [animal, 'frog']);
    clearBoard(world);
    world.items = [];
    const player = world.players[0]!;
    player.position = centerOf({ col: 3, row: 7 });
    player.facing = 'right';
    world.players[1]!.position = centerOf({ col: 19, row: 13 });
    applyItem(world, player, 'banana');
    return { world, player };
  }

  it('向きを押しても曲がらず、向きも変わらず、滑る速さで進む', () => {
    const { world, player } = slideArena('fox');
    const sim = new Simulation();
    const xs: number[] = [];
    for (let i = 0; i < 6; i += 1) {
      sim.step(world, onlyFor(world, 0, press({ up: true })));
      xs.push(player.position.x);
      expect(player.position.y).toBe(7.5);
      expect(player.facing).toBe('right');
    }
    [3.577083, 3.654167, 3.73125, 3.808333, 3.885417, 3.9625].forEach((x, i) => expect(xs[i]).toBeCloseTo(x, 5));
  });

  it('通路の中央へ寄せる強さはふだんの速さで、歩いた距離（足の動きの絵）は増えない', () => {
    const { world, player } = slideArena('fox');
    player.position = { x: 3.5, y: 7.6 };
    player.walked = 0;
    const sim = new Simulation();
    sim.step(world, onlyFor(world, 0, press({})));
    expect(player.position.x).toBeCloseTo(3.577083, 5);
    expect(player.position.y).toBeCloseTo(7.538333, 5);
    sim.step(world, onlyFor(world, 0, press({})));
    expect(player.position.y).toBe(7.5);
    expect(player.walked).toBe(0);
  });

  it('泣いている間にバナナを拾うと、泣いたまま滑る', () => {
    const { world, player } = slideArena('fox');
    player.effects.clear('slide');
    applyItem(world, player, 'onion');
    applyItem(world, player, 'banana');
    advance(world, onlyFor(world, 0, press({})), 4);
    expect(player.position.x).toBeCloseTo(3.808333, 5);
    expect(player.effects.has('stun')).toBe(true);
  });

  it('穴を掘っている最中も滑り、マスを出た次の tick に掘りが取り消される', () => {
    const { world, player } = slideArena('mole');
    player.action = new PitAction({ col: 3, row: 7 });
    advance(world, onlyFor(world, 0, press({})), 8);
    expect(player.position.x).toBeCloseTo(4.055, 5);
    expect(player.action?.kind).toBe('dig');
    advance(world, onlyFor(world, 0, press({})), 1);
    expect(player.position.x).toBeCloseTo(4.124375, 5);
    expect(player.action).toBeNull();
    expect(world.actors).toEqual([]);
  });

  it('舌を伸ばしている最中も滑る（舌は出したマスから伸びる）', () => {
    const { world, player } = slideArena('frog');
    player.action = new TongueAction({ col: 3, row: 7 }, 'right');
    advance(world, onlyFor(world, 0, press({})), 6);
    expect(player.position.x).toBeCloseTo(3.9625, 5);
    expect(player.action?.kind).toBe('tongue');
  });

  it('ブロックを壊しながら進む技の最中は、その技と滑りの両方で進む', () => {
    const { world, player } = slideArena('elephant');
    player.action = new ChargeAction('right');
    const sim = new Simulation();
    for (const x of [3.76675, 4.0335, 4.30025, 4.567]) {
      sim.step(world, onlyFor(world, 0, press({})));
      expect(player.position.x).toBeCloseTo(x, 5);
    }
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

  it('勝手に設置は 0.5 秒に1回だけ置こうとする', () => {
    // 毎 tick 置こうとすると、歩きながら隣り合うマスに続けて置く。
    // 原型は 0.5 秒に1回で、素の速さで歩くと1マスおきに並ぶ。
    const world = makeWorld();
    clearBoard(world);
    const player = world.players[0]!;
    player.position = centerOf({ col: 1, row: 1 });
    player.maxBombs = 3;
    player.effects.add('autobomb', itemEffectTicks(4), itemEffectTicks(12));
    const sim = new Simulation();
    const placedAt: number[] = [];
    for (let t = 0; t < 70; t += 1) {
      const events = sim.step(world, onlyFor(world, 0, press({ right: true })));
      if (events.some((event) => event.type === 'bombPlaced')) placedAt.push(t);
    }
    expect(placedAt).toEqual([0, AUTOBOMB_INTERVAL, AUTOBOMB_INTERVAL * 2]);
  });

  it('勝手に設置は、手持ちが戻っても次の拍まで置き直さない', () => {
    // 毎 tick 置こうとすると、爆発で手持ちが戻った次の tick に置き直す。
    const world = makeWorld();
    clearBoard(world);
    const player = world.players[0]!;
    player.hp = 100;
    player.effects.add('autobomb', itemEffectTicks(4), itemEffectTicks(12));
    const sim = new Simulation();
    const placedAt: number[] = [];
    for (let t = 0; t < 200; t += 1) {
      const events = sim.step(world, onlyFor(world, 0, press({})));
      if (events.some((event) => event.type === 'bombPlaced')) placedAt.push(t);
    }
    expect(placedAt.length).toBeGreaterThanOrEqual(2);
    for (const t of placedAt) expect(t % AUTOBOMB_INTERVAL).toBe(0);
  });

  it('勝手に設置の拍の合間でも、ボタンを押せば置ける', () => {
    // 原型も、ボタンで置く処理と勝手に設置は別々に置こうとする。
    const world = makeWorld();
    clearBoard(world);
    const player = world.players[0]!;
    player.position = centerOf({ col: 1, row: 1 });
    player.maxBombs = 3;
    player.effects.add('autobomb', itemEffectTicks(4), itemEffectTicks(12));
    const sim = new Simulation();
    sim.step(world, onlyFor(world, 0, press({})));
    // 隣のマスへ歩く。次の拍より手前で止める。
    advance(world, onlyFor(world, 0, press({ right: true })), 20, sim);
    const events = sim.step(world, onlyFor(world, 0, press({ right: true, bomb: true })));
    expect(events.filter((event) => event.type === 'bombPlaced')).toHaveLength(1);
    expect(world.bombs).toHaveLength(2);
  });

  it('勝手に設置は、その tick に動く前のマスに置く', () => {
    // 原型は効果の処理の中で全員ぶんの勝手に設置を処理してから、各プレイヤーを動かす。
    // 拍の tick にマスの境目をまたいでも、置くのは今までいたマス。
    const world = makeWorld();
    clearBoard(world);
    const player = world.players[0]!;
    player.position = { x: 1.99, y: 1.5 };
    player.effects.add('autobomb', itemEffectTicks(4), itemEffectTicks(12));
    const events = new Simulation().step(world, onlyFor(world, 0, press({ right: true })));
    expect(player.position.x).toBeGreaterThan(2);
    expect(events).toContainEqual({ type: 'bombPlaced', cell: { col: 1, row: 1 }, owner: 0 });
  });

  it('ボタンで置く爆弾は、その tick に動いたあとのマスに置く', () => {
    // 原型の humanUpdate も、動いてから爆弾のボタンを見る。違うのは勝手に設置だけ。
    // 修正する前から通る対照（ボタンの爆弾を移動の前へ動かす変更を検出する）。
    const world = makeWorld();
    clearBoard(world);
    const player = world.players[0]!;
    player.position = { x: 1.99, y: 1.5 };
    const events = new Simulation().step(world, onlyFor(world, 0, press({ right: true, bomb: true })));
    expect(events).toContainEqual({ type: 'bombPlaced', cell: { col: 2, row: 1 }, owner: 0 });
  });

  it('勝手に設置の拍の tick にボタンも押すと、動く前と動いたあとのマスに1つずつ置く', () => {
    // 原型も、効果の処理で勝手に設置を置いたあと、humanUpdate でボタンの爆弾を置く。
    const world = makeWorld();
    clearBoard(world);
    const player = world.players[0]!;
    player.position = { x: 1.99, y: 1.5 };
    player.maxBombs = 2;
    player.effects.add('autobomb', itemEffectTicks(4), itemEffectTicks(12));
    const events = new Simulation().step(world, onlyFor(world, 0, press({ right: true, bomb: true })));
    expect(events.filter((event) => event.type === 'bombPlaced')).toEqual([
      { type: 'bombPlaced', cell: { col: 1, row: 1 }, owner: 0 },
      { type: 'bombPlaced', cell: { col: 2, row: 1 }, owner: 0 },
    ]);
  });

  it('勝手に設置がかかっていれば、爆弾おけないでも拍の合間にボタンで置ける', () => {
    // ボタンの爆弾の側でも、勝手に設置が爆弾おけないに勝つ（BombSystem の forced）。
    const world = makeWorld();
    clearBoard(world);
    const player = world.players[0]!;
    player.position = centerOf({ col: 1, row: 1 });
    player.maxBombs = 3;
    player.effects.add('nobomb', itemEffectTicks(6), itemEffectTicks(18));
    player.effects.add('autobomb', itemEffectTicks(4), itemEffectTicks(12));
    const sim = new Simulation();
    sim.step(world, onlyFor(world, 0, press({})));
    expect(world.bombs).toHaveLength(1);
    // 隣のマスへ歩く。次の拍より手前で止める。
    advance(world, onlyFor(world, 0, press({ right: true })), 20, sim);
    const events = sim.step(world, onlyFor(world, 0, press({ right: true, bomb: true })));
    expect(events.filter((event) => event.type === 'bombPlaced')).toHaveLength(1);
    expect(world.bombs).toHaveLength(2);
  });

  it('同じ tick では、全員の勝手に設置をボタンの爆弾より先に置く', () => {
    // 原型は効果の処理で全員ぶんの勝手に設置を処理してから、入力の処理でボタンを見る。
    // 番号の小さいプレイヤーがボタンで置いても、拍のプレイヤーの爆弾が先に並ぶ（識別子も先）。
    // 誰も動かない場面でも、並び（同じ tick に導火線が尽きたときの爆発の順）が変わる。
    const world = makeWorld();
    clearBoard(world);
    const [first, second] = world.players;
    first!.position = centerOf({ col: 3, row: 1 });
    second!.position = centerOf({ col: 5, row: 3 });
    second!.effects.add('autobomb', itemEffectTicks(4), itemEffectTicks(12));
    new Simulation().step(world, onlyFor(world, 0, press({ bomb: true })));
    expect(world.bombs.map((bomb) => [bomb.owner, bomb.cell])).toEqual([
      [1, { col: 5, row: 3 }],
      [0, { col: 3, row: 1 }],
    ]);
    expect(world.bombs[0]!.id).toBeLessThan(world.bombs[1]!.id);
  });

  it('勝手に設置が切れても、待ちは残る', () => {
    // 待ちを 0 に戻すのはラウンドの始まりだけ（原型と同じ）。
    const world = makeWorld();
    clearBoard(world);
    const player = world.players[0]!;
    player.effects.add('autobomb', itemEffectTicks(4), itemEffectTicks(12));
    const sim = new Simulation();
    sim.step(world, onlyFor(world, 0, press({})));
    player.effects.clear('autobomb');
    advance(world, onlyFor(world, 0, press({})), 10, sim);
    expect(player.autobombWait).toBe(AUTOBOMB_INTERVAL);
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

/*
 * うんこのアイテムは、焼けずに吹き飛び、15 秒で消える（原型の blowPoop・POOP_LIFE）。
 * 盤面を空にして、プレイヤー0の爆弾を置いて爆発させる。吹き飛ぶ先は、原型を画面なしで
 * 動かして同じ場面で測った答え（爆心の上の場面は、原型も乱数で向きを選ぶ）。
 */
describe('うんこのアイテム', () => {
  function poopArena(): WorldState {
    const world = makeWorld();
    clearBoard(world);
    world.items = [];
    return world;
  }

  function putItem(world: WorldState, cell: Cell, kind: ItemKind): void {
    world.items.push({ id: world.ids.take(), cell, kind });
  }

  function explodeAt(world: WorldState, cell: Cell, power: number): SimEvent[] {
    const player = world.players[0]!;
    player.position = centerOf(cell);
    player.power = power;
    const bomb = placeBomb(world, player)!;
    return detonate(world, bomb).events;
  }

  it('爆風に触れても焼けず、爆心から外向きに1マス吹き飛ぶ。残る長さは吹き飛んだ tick から数え直す', () => {
    const world = poopArena();
    world.now = tick(40);
    world.items.push({ ...placedItem(world, { col: 5, row: 3 }, 'poop'), expiresAt: tick(3) });
    const events = explodeAt(world, { col: 3, row: 3 }, 3);
    expect(events.filter((e) => e.type === 'itemBurned')).toEqual([]);
    expect(events).toContainEqual({ type: 'itemBlown', from: { col: 5, row: 3 }, to: { col: 6, row: 3 }, kind: 'poop' });
    expect(world.items.map((item) => [item.cell.col, item.cell.row, item.expiresAt])).toEqual([
      [6, 3, 40 + POOP_LIFETIME],
    ]);
  });

  it('外向きのマスへ行けなければ、右・左・下・上の順に試す', () => {
    const world = poopArena();
    // 外向き（右）はブロック、左は別のアイテムで塞ぐ。下へ飛ぶ。
    world.board.set({ col: 6, row: 3 }, 'soft');
    putItem(world, { col: 4, row: 3 }, 'fire');
    putItem(world, { col: 5, row: 3 }, 'poop');
    const events = explodeAt(world, { col: 3, row: 3 }, 2);
    expect(events).toContainEqual({ type: 'itemBlown', from: { col: 5, row: 3 }, to: { col: 5, row: 4 }, kind: 'poop' });
    // 左を塞いでいたアイテムは、吹き飛んだあとで焼ける（配列の後ろから順に見る）。
    expect(events).toContainEqual({ type: 'itemBurned', cell: { col: 4, row: 3 }, kind: 'fire' });
  });

  it('いちばん近い爆心が斜めの位置にあれば、斜めに飛ぶ（爆心は、いま盤面にある爆風から選ぶ）', () => {
    const world = poopArena();
    // 残っている爆風の爆心 (5,4) までは2歩、いま爆発する (1,3) までは3歩。
    addBlast(world, { col: 5, row: 4 }, 1, true);
    putItem(world, { col: 4, row: 3 }, 'poop');
    const events = explodeAt(world, { col: 1, row: 3 }, 3);
    expect(events).toContainEqual({ type: 'itemBlown', from: { col: 4, row: 3 }, to: { col: 3, row: 2 }, kind: 'poop' });
  });

  it('同じ近さの爆心が2つあれば、先に置かれた爆風の爆心から外向きに飛ぶ', () => {
    const world = poopArena();
    // 残っている爆風の爆心 (6,3) と、いま爆発する (2,3) は、どちらも2歩。
    addBlast(world, { col: 6, row: 3 }, 1, true);
    putItem(world, { col: 4, row: 3 }, 'poop');
    const events = explodeAt(world, { col: 2, row: 3 }, 2);
    expect(events).toContainEqual({ type: 'itemBlown', from: { col: 4, row: 3 }, to: { col: 3, row: 3 }, kind: 'poop' });
  });

  it('爆弾のあるマスへは飛ばない（爆風の届かない爆弾が外向きのマスにあれば、次の向きへ）', () => {
    const world = poopArena();
    const far = world.players[1]!;
    far.position = centerOf({ col: 6, row: 3 });
    placeBomb(world, far);
    far.position = centerOf({ col: 11, row: 9 });
    putItem(world, { col: 5, row: 3 }, 'poop');
    const events = explodeAt(world, { col: 3, row: 3 }, 2);
    expect(events).toContainEqual({ type: 'itemBlown', from: { col: 5, row: 3 }, to: { col: 4, row: 3 }, kind: 'poop' });
    expect(world.bombs.map((bomb) => bomb.cell)).toEqual([{ col: 6, row: 3 }]);
  });

  it('爆心の上にあれば、試合の乱数を1回だけ取り出して向きを選ぶ', () => {
    const world = poopArena();
    putItem(world, { col: 3, row: 3 }, 'poop');
    const before = world.rng.calls;
    const events = explodeAt(world, { col: 3, row: 3 }, 1);
    expect(world.rng.calls).toBe(before + 1);
    const blown = events.find((e) => e.type === 'itemBlown');
    expect(blown?.type === 'itemBlown' ? [blown.to] : []).toEqual([world.items[0]!.cell]);
    expect(
      [
        { col: 4, row: 3 },
        { col: 2, row: 3 },
        { col: 3, row: 4 },
        { col: 3, row: 2 },
      ].some((cell) => sameCell(cell, world.items[0]!.cell)),
    ).toBe(true);
  });

  it('どこへも行けなければ、焼けずにその場に残る（残る長さも数え直さない）', () => {
    const world = poopArena();
    // 隅の (1,1)。外は壁、右と下はブロック。
    world.board.set({ col: 2, row: 1 }, 'soft');
    world.board.set({ col: 1, row: 2 }, 'soft');
    world.items.push({ ...placedItem(world, { col: 1, row: 1 }, 'poop'), expiresAt: tick(7) });
    const events = explodeAt(world, { col: 1, row: 1 }, 1);
    expect(events.filter((e) => e.type === 'itemBurned' || e.type === 'itemBlown')).toEqual([]);
    const poop = world.items.filter((item) => item.kind === 'poop');
    expect(poop.map((item) => [item.cell.col, item.cell.row, item.expiresAt])).toEqual([[1, 1, 7]]);
  });

  it('置いた tick を 0 として、15 秒（900 tick）を過ぎた 901 tick 目に消える。ほかのアイテムは消えない', () => {
    // 原型は「いまの時刻 − 置いた時刻 > 15 秒」で消す。60 tick で1秒なので、901 tick 目
    // （原型は小数の足し算の誤差で 900 tick 目になる時刻もある。POOP_LIFETIME の説明）。
    const world = poopArena();
    const sim = new Simulation();
    world.items.push(placedItem(world, { col: 9, row: 5 }, 'poop'), placedItem(world, { col: 9, row: 7 }, 'fire'));
    expect(world.items.map((item) => item.expiresAt)).toEqual([POOP_LIFETIME, undefined]);
    for (let i = 0; i <= POOP_LIFETIME; i += 1) sim.step(world, onlyFor(world, 0, press({})));
    expect(world.items.map((item) => item.kind)).toEqual(['poop', 'fire']);
    expect(world.now).toBe(POOP_LIFETIME + 1);
    const events = sim.step(world, onlyFor(world, 0, press({})));
    expect(events).toContainEqual({ type: 'itemExpired', cell: { col: 9, row: 5 }, kind: 'poop', scattered: false });
    expect(world.items.map((item) => item.kind)).toEqual(['fire']);
  });

  it('壊したブロックから落ちたうんこにも、残る長さが付く', () => {
    // うんこが落ちる種を順に探す（種で盤面の乱数が変わる）。
    for (let seed = 0; seed < 200; seed += 1) {
      const world = makeWorld(seed);
      clearBoard(world);
      world.items = [];
      world.board.set({ col: 5, row: 3 }, 'soft');
      const events = explodeAt(world, { col: 3, row: 3 }, 3);
      const dropped = events.find((e) => e.type === 'itemDropped');
      if (dropped?.type !== 'itemDropped' || dropped.kind !== 'poop') continue;
      expect(world.items.map((item) => item.expiresAt)).toEqual([world.now + POOP_LIFETIME]);
      return;
    }
    throw new Error('うんこが落ちる場面が見つからない');
  });
});

describe('被弾', () => {
  it('爆風が重なったマスでは、あとから置かれた爆風の持ち主が当てた扱いになる', () => {
    // 相手の爆風に誘爆された自分の爆弾のマスで当たったら、自爆として数える。
    // 原型が爆風の持ち主を控えていたのは、自爆の割合を測るため。
    const world = makeWorld();
    clearBoard(world);
    const [first, second] = world.players;
    first!.position = centerOf({ col: 5, row: 5 });
    first!.power = 2;
    const trigger = placeBomb(world, first!)!;
    second!.position = centerOf({ col: 7, row: 5 });
    placeBomb(world, second!);
    first!.position = centerOf({ col: 1, row: 1 });
    detonate(world, trigger);
    const owners = world.blasts
      .filter((blast) => blast.cell.col === 7 && blast.cell.row === 5)
      .map((blast) => blast.owner);
    expect(owners).toEqual([0, 1]);

    const events = new DamageSystem().step(world);
    expect(events).toContainEqual(expect.objectContaining({ type: 'playerHurt', target: 1, by: 1 }));
    expect(second!.lastHitBy).toBe(1);
  });

  it('兄弟の爆弾の腕が交わるマスでは、原型と同じく右・左・下・上の順で当てたプレイヤーが決まる', () => {
    // 同じ爆弾に誘爆された2つの爆弾は、爆風を伸ばす向きの順（右・左・下・上）に待ち行列へ積む。
    // 右の (7,5)（1P）を先に、上の (5,3)（2P）をあとに積むので、(7,3) の最後の爆風は 2P。
    // 期待値は原型を画面なしで動かして実測した答え（blastOwner が 1）。
    const world = makeWorld();
    clearBoard(world);
    const [first, second] = world.players;
    first!.power = 2;
    first!.maxBombs = 2;
    second!.power = 2;
    first!.position = centerOf({ col: 5, row: 5 });
    const trigger = placeBomb(world, first!)!;
    first!.position = centerOf({ col: 7, row: 5 });
    placeBomb(world, first!);
    second!.position = centerOf({ col: 5, row: 3 });
    placeBomb(world, second!);
    second!.position = centerOf({ col: 7, row: 3 });
    first!.position = centerOf({ col: 1, row: 1 });
    detonate(world, trigger);
    const owners = world.blasts
      .filter((blast) => blast.cell.col === 7 && blast.cell.row === 3)
      .map((blast) => blast.owner);
    expect(owners).toEqual([0, 1]);

    const events = new DamageSystem().step(world);
    expect(events).toContainEqual(expect.objectContaining({ type: 'playerHurt', target: 1, by: 1 }));
  });

  it('下の兄弟を先に積むので、誘爆された上の自分の爆弾のマスは自爆になる', () => {
    // A（1P）が上の B（2P）と下の C（1P）を誘爆し、C の上の腕が B のマスまで届く。
    // 下の C を先に積むので、B のマスの最後の爆風は B の中心（2P。自爆）。
    // 期待値は原型を画面なしで動かして実測した答え（持ち主の並び [0,0,1]、blastOwner が 1）。
    const world = makeWorld();
    clearBoard(world);
    const [first, second] = world.players;
    first!.maxBombs = 2;
    first!.power = 1;
    first!.position = centerOf({ col: 5, row: 5 });
    const trigger = placeBomb(world, first!)!;
    first!.power = 2;
    first!.position = centerOf({ col: 5, row: 6 });
    placeBomb(world, first!);
    second!.power = 1;
    second!.position = centerOf({ col: 5, row: 4 });
    placeBomb(world, second!);
    first!.position = centerOf({ col: 1, row: 1 });
    detonate(world, trigger);
    const owners = world.blasts
      .filter((blast) => blast.cell.col === 5 && blast.cell.row === 4)
      .map((blast) => blast.owner);
    expect(owners).toEqual([0, 0, 1]);

    const events = new DamageSystem().step(world);
    expect(events).toContainEqual(expect.objectContaining({ type: 'playerHurt', target: 1, by: 1 }));
  });

  it('上下を返すと、誘爆された下の自分の爆弾のマスは、あとから積んだ兄弟の腕の持ち主になる', () => {
    // A（1P）が下の B（2P）と上の C（1P）を誘爆し、C の下の腕が B のマスまで届く。
    // 下の B を先に、上の C をあとに積むので、B のマスの最後の爆風は C の腕（1P）で、
    // 自爆にならない。誘爆された自分の爆弾のマスがいつも自爆になるのではなく、順で決まる。
    // 期待値は原型を画面なしで動かして実測した答え（持ち主の並び [0,1,0]、blastOwner が 0）。
    const world = makeWorld();
    clearBoard(world);
    const [first, second] = world.players;
    first!.maxBombs = 2;
    first!.power = 1;
    first!.position = centerOf({ col: 5, row: 5 });
    const trigger = placeBomb(world, first!)!;
    second!.power = 1;
    second!.position = centerOf({ col: 5, row: 6 });
    placeBomb(world, second!);
    first!.power = 2;
    first!.position = centerOf({ col: 5, row: 4 });
    placeBomb(world, first!);
    first!.position = centerOf({ col: 1, row: 1 });
    detonate(world, trigger);
    const owners = world.blasts
      .filter((blast) => blast.cell.col === 5 && blast.cell.row === 6)
      .map((blast) => blast.owner);
    expect(owners).toEqual([0, 1, 0]);

    const events = new DamageSystem().step(world);
    expect(events).toContainEqual(expect.objectContaining({ type: 'playerHurt', target: 1, by: 0 }));
  });

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

  it('体力が尽きると盤面から外れ、残り時間があれば外周へ回る', () => {
    const world = makeWorld();
    const player = world.players[0]!;
    player.hp = 2;
    placeBomb(world, player);
    advance(world, onlyFor(world, 0, press({})), 200);
    expect(isAlive(player)).toBe(false);
    expect(player.life.kind).toBe('negibon');
  });

  it('残り時間が短ければ、倒れた人は外周へ回らず退場する', () => {
    // 倒れた tick のうちに退場していることを見る。いったん外周へ回ってから、
    // 次の tick に外周が閉じて退場しても、最後の状態だけでは区別がつかない。
    const world = makeWorld();
    world.endsAt = tick(world.now + NEGIBON_CUTOFF);
    const player = world.players[0]!;
    player.hp = 2;
    placeBomb(world, player);
    const sim = new Simulation();
    for (let i = 0; i < 200; i += 1) {
      const events = sim.step(world, onlyFor(world, 0, press({})));
      expect(events.some((e) => e.type === 'lanesClosed')).toBe(false);
      if (events.some((e) => e.type === 'playerDown')) break;
    }
    expect(player.life).toBe(OUT);
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
      { type: 'exploded', cell: { col: 1, row: 1 }, owner: 0, chained: 2, blocks: 1 },
      { type: 'blockDestroyed', cell: { col: 2, row: 1 } },
      { type: 'itemDropped', cell: { col: 2, row: 1 }, kind: 'fire' },
      { type: 'itemTaken', cell: { col: 2, row: 1 }, kind: 'fire', taker: 0 },
      { type: 'itemBurned', cell: { col: 2, row: 1 }, kind: 'fire' },
      { type: 'itemBlown', from: { col: 2, row: 1 }, to: { col: 3, row: 1 }, kind: 'poop' },
      { type: 'itemExpired', cell: { col: 3, row: 1 }, kind: 'poop', scattered: false },
      { type: 'effectApplied', target: 0, effect: 'slow' },
      { type: 'playerHurt', target: 0, by: 1, amount: 2 },
      { type: 'playerDown', target: 0, by: 1, at: { x: 1.5, y: 1.5 } },
      { type: 'suddenDeath', reason: 'timeUp', players: [0, 1] },
      { type: 'leekThrown', player: 0, from: { x: 1.5, y: -0.31 }, facing: 'down' },
      { type: 'leekStopped', cell: { col: 1, row: 1 }, by: 'bomb' },
      { type: 'leekStopped', cell: { col: 1, row: 1 }, by: 'range' },
      { type: 'revived', player: 0, replaced: 1, at: { x: 1.5, y: 1.5 } },
      { type: 'lanesClosed', players: [0] },
      { type: 'techniqueUsed', player: 0, special: true },
      { type: 'techniqueUsed', player: 1, special: false },
      { type: 'techniqueMoment', player: 0, moment: 'ringScattered' },
      { type: 'burntOff', player: 0, cell: { col: 2, row: 1 } },
      { type: 'roundEnded', round: 1, winner: null },
      { type: 'matchEnded', champion: 0 },
    ];
    expect(() => presenter.consume(all, makeWorld())).not.toThrow();
    expect(played.length).toBeGreaterThan(0);
  });

  it('知らない種類が来たら止まる', () => {
    const presenter = new Presenter();
    const bogus = { type: 'そんなイベントはない' } as unknown as SimEvent;
    expect(() => presenter.consume([bogus], makeWorld())).toThrow();
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
