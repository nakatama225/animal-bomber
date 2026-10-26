import { describe, expect, it } from 'vitest';

import { decideBomb } from '../../src/ai/BombPlacement.js';
import type { CpuBehavior } from '../../src/ai/CpuBehavior.js';
import { CpuContext } from '../../src/ai/CpuContext.js';
import { CpuInputSource, cpuSeed } from '../../src/ai/CpuInputSource.js';
import { CPU_LEVELS, type CpuLevelKey } from '../../src/ai/CpuLevel.js';
import { freshMemory, type CpuMemory } from '../../src/ai/CpuMemory.js';
import { BREAK_BLOCKS } from '../../src/ai/behaviors/BreakBlocks.js';
import { DEFAULT_CHAIN } from '../../src/ai/behaviors/DefaultChain.js';
import { FLEE } from '../../src/ai/behaviors/Flee.js';
import { OUT_OF_BOMBS_BAN, SAME_SPOT_BAN, UNSAFE_SPOT_BAN } from '../../src/ai/margins.js';
import { directionAlong } from '../../src/ai/PathFollower.js';
import { FOX_TACTIC } from '../../src/ai/tactics/FoxTactic.js';
import { FROG_TACTIC } from '../../src/ai/tactics/FrogTactic.js';
import { BurntTongueActor } from '../../src/domain/abilities/frog/TongueAction.js';
import type { ActiveAction } from '../../src/domain/abilities/ActiveAction.js';
import { cellOf, centerOf, type Cell } from '../../src/domain/core/Coord.js';
import { Rng } from '../../src/domain/core/Rng.js';
import { secondsToTicks, tick } from '../../src/domain/core/Tick.js';
import type { SimEvent } from '../../src/domain/events/SimEvent.js';
import { IdleInputSource, InputGatherer } from '../../src/domain/input/InputSource.js';
import { IDLE_INPUT } from '../../src/domain/input/PlayerInput.js';
import { placeBomb, placeBombAt } from '../../src/domain/mutations/bombs.js';
import { enterSuddenDeath } from '../../src/domain/mutations/suddenDeath.js';
import { DangerMap } from '../../src/domain/query/DangerMap.js';
import { findPath } from '../../src/domain/query/PathFinder.js';
import { itemEffectTicks } from '../../src/domain/rules/items.js';
import { BLAST_DURATION, BOMB_FUSE } from '../../src/domain/rules/tuning.js';
import type { PlayerId, PlayerState } from '../../src/domain/state/PlayerState.js';
import { hashWorld, type WorldState } from '../../src/domain/state/WorldState.js';
import { Simulation } from '../../src/domain/systems/Simulation.js';
import { clearBoard, grantSpecial, makeWorld } from '../helpers.js';


interface CpuSpec {
  readonly id: PlayerId;
  readonly level: CpuLevelKey;
  readonly chain?: readonly CpuBehavior[];
  readonly seed?: number;
}

/** 指定したプレイヤーを CPU に、残りを何もしないプレイヤーにした盤面。 */
function arena(world: WorldState, cpus: readonly CpuSpec[], matchSeed = 1234) {
  const gatherer = new InputGatherer();
  const sources = new Map<PlayerId, CpuInputSource>();
  for (const player of world.players) {
    const spec = cpus.find((c) => c.id === player.id);
    if (spec === undefined) {
      gatherer.add(new IdleInputSource(player.id));
      continue;
    }
    const source = new CpuInputSource(
      player.id,
      CPU_LEVELS[spec.level],
      spec.seed ?? cpuSeed(matchSeed, player.id),
      spec.chain,
    );
    sources.set(player.id, source);
    gatherer.add(source);
  }
  const sim = new Simulation();
  return {
    sources,
    /** `ticks` 回進める。起きたイベントをすべて返す。 */
    run(ticks: number): SimEvent[] {
      const events: SimEvent[] = [];
      for (let i = 0; i < ticks; i += 1) events.push(...sim.step(world, gatherer.gather(world)));
      return events;
    },
  };
}

const ALL_FOUR = ['rabbit', 'elephant', 'fox', 'frog'];

describe('CPU は入力を返すだけ', () => {
  it('入力を返す前と後で、試合の状態が変わらない', () => {
    // 型の Readonly は浅く、中の配列やプレイヤーの書き換えは止められない。
    // 状態の要約を前後で比べて、実際に書き換えていないことを見る。
    // 要約には試合の乱数を取り出した回数も入るので、試合の乱数を取り出していないことも分かる。
    const world = makeWorld(7, ALL_FOUR);
    const gatherer = new InputGatherer();
    for (const player of world.players) {
      gatherer.add(new CpuInputSource(player.id, CPU_LEVELS.oni, cpuSeed(7, player.id)));
    }
    const sim = new Simulation();
    for (let i = 0; i < 1500; i += 1) {
      const before = hashWorld(world);
      const playerInputs = gatherer.gather(world);
      expect(hashWorld(world)).toBe(before);
      sim.step(world, playerInputs);
    }
  });

  it('同じ種なら、CPU どうしの試合は何度やっても同じになる', () => {
    const play = (cpuSeedOffset: number): number => {
      const world = makeWorld(99, ALL_FOUR);
      const game = arena(
        world,
        world.players.map((p) => ({ id: p.id, level: 'hard', seed: cpuSeed(99, p.id) + cpuSeedOffset })),
      );
      game.run(3000);
      return hashWorld(world);
    };
    expect(play(0)).toBe(play(0));
    // 対照：CPU の種だけを変えると別の試合になる。種が反映されていることの確認。
    expect(play(1)).not.toBe(play(0));
  });
});

describe('身を守る', () => {
  it('足元に置かれた爆弾から逃げ切る', () => {
    // 爆発する tick に、爆風の届かないマスに立っている。
    // ⚠️ 爆発のあとまでは見ない。手持ちが戻ると、まだ燃えているマスの先へ逃げる前提で次を置くことがある
    // （原型の canEscapeAfterBomb も、逃げ道が燃えているかは見ない）。
    const world = makeWorld(3, ['rabbit', 'elephant']);
    const cpu = world.players[0]!;
    const game = arena(world, [{ id: 0, level: 'hard' }]);
    const bomb = placeBomb(world, cpu)!;
    const hp = cpu.hp;
    const reach = DangerMap.of(world);
    game.run(BOMB_FUSE - 1);
    expect(world.bombs).toContain(bomb);
    expect(reach.isSafe(cellOf(cpu.position))).toBe(true);
    const events = game.run(2);
    expect(events.some((e) => e.type === 'exploded')).toBe(true);
    expect(cpu.hp).toBe(hp);
  });

  it('「そうさ反転」がかかっていても、行きたい向きへ歩く', () => {
    // ゲームの側は入力の段階で向きを反転する。CPU は反転を知っていて打ち消す。
    // 原型の CPU は反転の影響を受けなかったので、同じ強さに揃えている。
    const world = makeWorld(3, ['rabbit', 'elephant']);
    clearBoard(world);
    const cpu = world.players[0]!;
    world.players[1]!.position = centerOf({ col: 11, row: 1 });
    cpu.effects.add('reverse', tick(600), tick(600));
    const game = arena(world, [{ id: 0, level: 'hard' }]);
    const startX = cpu.position.x;
    game.run(30);
    expect(cpu.position.x).toBeGreaterThan(startX + 1);
  });
});

describe('攻める', () => {
  it('射線に入った相手を狙って置く', () => {
    const world = makeWorld(3, ['rabbit', 'elephant']);
    clearBoard(world);
    const cpu = world.players[0]!;
    cpu.power = 3;
    world.players[1]!.position = centerOf({ col: 3, row: 1 });
    const game = arena(world, [{ id: 0, level: 'hard' }]);
    const events = game.run(10);
    expect(events.some((e) => e.type === 'bombPlaced' && e.owner === 0)).toBe(true);
  });

  it('⛔ 開幕の袋小路でも、5秒以内に爆弾を置く', () => {
    // 開幕は周りがブロックだらけで、どこも袋小路になっている。
    // 原型で「袋小路では置かない」を加えたところ、つよい CPU が
    // 40秒のあいだ1個も置かず、うろつくだけになった。
    for (const seed of [1, 2, 3, 4, 5]) {
      const world = makeWorld(seed, ['rabbit', 'elephant']);
      const game = arena(world, [{ id: 0, level: 'hard' }], seed);
      const events = game.run(secondsToTicks(5));
      expect(events.some((e) => e.type === 'bombPlaced' && e.owner === 0)).toBe(true);
    }
  });

  it('規則を1つ足すだけで振る舞いが変わる：「袋小路では待つ」を足すと1個も置かなくなる', () => {
    // 判断の規則は配列に並んでいるだけなので、試したい規則を1行足せば試せる。
    // ここでは原型で失敗した規則（4歩以内に行けるマスが8未満なら、爆弾を置かずに
    // その場に留まる）を、逃げる規則のすぐ後ろに差し込み、10秒で爆弾が0個になることを見る。
    const waitInDeadEnd: CpuBehavior = {
      name: 'waitInDeadEnd',
      decide(ctx) {
        let open = 0;
        findPath(ctx.world, ctx.me, ctx.here, () => {
          open += 1;
          return false;
        }, { maxDistance: 4 });
        return open < 8 ? { mode: 'wander', path: [], wantBomb: false } : null;
      },
    };
    const chain = [FLEE, waitInDeadEnd, ...DEFAULT_CHAIN.slice(1)];

    const world = makeWorld(1, ['rabbit', 'elephant']);
    const game = arena(world, [{ id: 0, level: 'hard', chain }]);
    const events = game.run(secondsToTicks(10));
    expect(events.filter((e) => e.type === 'bombPlaced' && e.owner === 0)).toHaveLength(0);
  });

  it('とくぎは、原型の CPU と同じく直に出す（長押しを待たず、押した瞬間の通常技も出ない）', () => {
    // 原型の CPU は useSpecial を直に呼ぶ。うさぎなら跳ばずに、その場で撒く。
    const world = makeWorld(3, ['rabbit', 'elephant']);
    clearBoard(world);
    const cpu = world.players[0]!;
    grantSpecial(cpu, 1);
    world.players[1]!.position = centerOf({ col: 4, row: 1 });
    const game = arena(world, [{ id: 0, level: 'hard' }]);
    const start = cellOf(cpu.position);
    let usedAt: number | null = null;
    for (let t = 1; t <= 10 && usedAt === null; t += 1) {
      if (game.run(1).some((e) => e.type === 'techniqueUsed' && e.player === 0)) usedAt = t;
    }
    expect(usedAt).toBe(1);
    expect(cpu.specialCharges).toBe(0);
    expect(cpu.effects.has('scattering')).toBe(true);
    expect(cellOf(cpu.position)).toEqual(start);
  });
});

describe('爆弾を置いてよいかの判断', () => {
  /** 判断に使う文脈を、盤面の左上に立つプレイヤー 0 について作る。 */
  function context(world: WorldState) {
    const me = world.players[0]!;
    const here: Cell = { col: 1, row: 1 };
    const memory = freshMemory(new Rng(1));
    memory.wantBomb = true;
    const ctx = new CpuContext(world, me, here, DangerMap.of(world), false, CPU_LEVELS.hard, memory, new Rng(1));
    return { ctx, memory };
  }

  it('逃げ切れるなら置く', () => {
    const world = makeWorld(3);
    clearBoard(world);
    const { ctx } = context(world);
    expect(decideBomb(ctx, 'down')).toBe('bomb');
  });

  it('逃げ切れないなら置かず、しばらく爆弾を狙わない', () => {
    const world = makeWorld(3);
    clearBoard(world);
    world.board.set({ col: 2, row: 1 }, 'soft');
    world.board.set({ col: 1, row: 2 }, 'soft');
    const { ctx, memory } = context(world);
    expect(decideBomb(ctx, 'down')).toBeNull();
    expect(memory.bombBan).toBe(UNSAFE_SPOT_BAN);
  });

  it('⛔ 少し前に置いたマスには置き直さない', () => {
    // 置く → 自分の爆風から逃げて離れる → 爆発が終わると戻ってまた置く、の往復を防ぐ。
    const world = makeWorld(3);
    clearBoard(world);
    const { ctx, memory } = context(world);
    memory.lastBomb = { cell: { col: 1, row: 1 }, at: tick(world.now - SAME_SPOT_BAN + 1) };
    expect(decideBomb(ctx, 'down')).toBeNull();
    expect(memory.bombBan).toBe(UNSAFE_SPOT_BAN);
  });

  it('十分に時間がたてば、同じマスにも置ける', () => {
    const world = makeWorld(3);
    clearBoard(world);
    const { ctx, memory } = context(world);
    memory.lastBomb = { cell: { col: 1, row: 1 }, at: tick(world.now - SAME_SPOT_BAN) };
    expect(decideBomb(ctx, 'down')).toBe('bomb');
  });

  it('前の tick に爆弾のボタンを押していたら、この tick は何も決めずに待つ（押した瞬間にだけ有効）', () => {
    const world = makeWorld(3);
    clearBoard(world);
    world.players[0]!.previousInput = { ...IDLE_INPUT, bomb: true };
    const { ctx, memory } = context(world);
    expect(decideBomb(ctx, 'down')).toBeNull();
    expect([memory.wantBomb, memory.bombBan, memory.lastBomb]).toEqual([true, 0, null]);
  });

  it('爆弾おけないだけなら置かず、「勝手に設置」が重なっている間は置く（ゲームの側の canPlaceBomb と同じ）', () => {
    // 原型の CPU は cpuUpdate で canPlaceBomb を見る。原型を画面なしで動かして測ると、爆弾おけないだけなら
    // 置けず、勝手に設置が重なっていれば置ける。
    const decide = (withAutobomb: boolean) => {
      const world = makeWorld(3);
      clearBoard(world);
      world.players[0]!.effects.add('nobomb', itemEffectTicks(6), itemEffectTicks(18));
      if (withAutobomb) world.players[0]!.effects.add('autobomb', itemEffectTicks(4), itemEffectTicks(12));
      const { ctx } = context(world);
      return decideBomb(ctx, 'down');
    };
    expect(decide(false)).toBeNull();
    expect(decide(true)).toBe('bomb');
  });

  it('自分の爆弾が多すぎるときは、短く待つだけにする', () => {
    const world = makeWorld(3);
    clearBoard(world);
    const me = world.players[0]!;
    me.maxBombs = 10;
    for (const col of [9, 11, 13]) placeBombAt(world, me, { col, row: 9 });
    const { ctx, memory } = context(world);
    expect(decideBomb(ctx, 'down')).toBeNull();
    expect(memory.bombBan).toBe(OUT_OF_BOMBS_BAN);
  });
});

describe('ボタンの押し方', () => {
  it('前の tick に押していたボタンは押さず、次の tick に押す（押した瞬間にだけ有効）', () => {
    // 射線に相手がいて、すぐ置きたい場面。前の tick に爆弾のボタンを押していた扱いにすると、
    // この tick は押さずに置きたいままでいて、次の tick に押す。
    const world = makeWorld(3, ['rabbit', 'elephant']);
    clearBoard(world);
    const cpu = world.players[0]!;
    cpu.power = 3;
    world.players[1]!.position = centerOf({ col: 3, row: 1 });
    cpu.previousInput = { ...IDLE_INPUT, bomb: true };
    const source = new CpuInputSource(0, CPU_LEVELS.oni, 1);
    const sim = new Simulation();
    const first = source.next(world);
    expect([first.bomb, source.memory.wantBomb]).toEqual([false, true]);
    sim.step(world, new Map([[0, first], [1, IDLE_INPUT]]));
    expect(source.next(world).bomb).toBe(true);
  });
});

describe('ラウンドをまたぐ', () => {
  it('盤面が作り直されたら、前のラウンドの記憶を捨てる', () => {
    const first = makeWorld(3, ['rabbit', 'elephant']);
    const source = new CpuInputSource(0, CPU_LEVELS.hard, 1);
    const sim = new Simulation();
    for (let i = 0; i < 600 && source.memory.lastBomb === null; i += 1) {
      sim.step(first, new Map([[0, source.next(first)]]));
    }
    expect(source.memory.lastBomb).not.toBeNull();

    source.next(makeWorld(4, ['rabbit', 'elephant']));
    expect(source.memory.lastBomb).toBeNull();
  });

  it('延長戦に入っても記憶を捨てない。経路も置き直さない記憶も揺らぎもそのまま（原型の enterSuddenDeath L4435-4465 は p.ai に触らない）', () => {
    // 延長戦では盤面を作り直さず、全員を開始位置へ移す。原型は CPU の記憶を作り直さないので、次に考え直すまでは
    // 移る前の経路の先のマスへ歩く。前はここで捨てていた（この確認も捨てる側を見ていた）が、原型に合わせた。
    // 作り直すと判断の間隔の揺らぎ（jitter）を引き直し、CPU の乱数が1つ進む。
    const world = makeWorld(3, ['rabbit', 'elephant']);
    const source = new CpuInputSource(0, CPU_LEVELS.hard, 1);
    const sim = new Simulation();
    for (let i = 0; i < 600 && source.memory.lastBomb === null; i += 1) {
      sim.step(world, new Map([[0, source.next(world)]]));
    }
    expect(source.memory.lastBomb).not.toBeNull();
    const before = source.memory as CpuMemory;
    const { jitter, lastBomb } = before;
    before.path = [{ col: 9, row: 9 }];
    before.thinkIn = 99;

    enterSuddenDeath(world, [0, 1], 'timeUp');
    source.next(world);
    expect(source.memory).toBe(before);
    expect(source.memory.jitter).toBe(jitter);
    expect(source.memory.lastBomb).toEqual(lastBomb);
    expect(source.memory.path).toEqual([{ col: 9, row: 9 }]);
  });
});

describe('経路の追従（原型 cpuUpdate の「経路追従」）', () => {
  it('経路が尽きたら、その場に立ち止まる（中央へは寄らない）', () => {
    const world = makeWorld(3);
    const me = world.players[0]!;
    me.position = { x: 5.5, y: 2.11 };
    expect(directionAlong(me, [])).toBeNull();
  });

  it('次のマスの中央から 0.15 以内に来たら、並びから消して、その tick は歩かない', () => {
    const world = makeWorld(3);
    const me = world.players[0]!;
    me.position = { x: 5.64, y: 2.5 };
    const path = [{ col: 5, row: 2 }, { col: 5, row: 3 }];
    expect(directionAlong(me, path)).toBeNull();
    expect(path).toEqual([{ col: 5, row: 3 }]);
    // 0.15 ちょうどは、まだ着いていない（原型は 0.15 未満で着いたとみなす）。
    me.position = { x: 5.65, y: 2.5 };
    expect(directionAlong(me, [{ col: 5, row: 2 }])).toBe('left');
  });

  it('縦も横も 0.06 より離れていれば離れているほうの軸だけ、片方が 0.06 以内なら両方の軸を見て横を押す', () => {
    const world = makeWorld(3);
    const me = world.players[0]!;
    // 横に 0.04・縦に 1.0 離れている：横は 0.06 以内なので消さず、0.03 より離れているので横を押す
    // （原型の movePlayer は斜めを横に丸める）。
    me.position = { x: 9.46, y: 1.5 };
    expect(directionAlong(me, [{ col: 9, row: 2 }])).toBe('right');
    // 横に 0.03 以内なら横は押さず、縦を押す。
    me.position = { x: 9.48, y: 1.5 };
    expect(directionAlong(me, [{ col: 9, row: 2 }])).toBe('down');
    // 横に 0.1・縦に 1.0：両方 0.06 より離れているので、離れているほう（縦）だけ。
    me.position = { x: 9.4, y: 1.5 };
    expect(directionAlong(me, [{ col: 9, row: 2 }])).toBe('down');
  });
});

describe('同じ長さの経路の選び方', () => {
  it('隣のマスを右・左・下・上の順に探索する（原型の bfsPath と同じ）', () => {
    // (3,3) から (5,1) へは、右右上上 と 上上右右 の2通りがあり、どちらも4歩（(4,2) は柱）。
    // 右を上より先に探索するので 右右上上。上を先に探索すると 上上右右 になる。
    const world = makeWorld(3);
    clearBoard(world);
    const me = world.players[0]!;
    const path = findPath(world, me, { col: 3, row: 3 }, (cell) => cell.col === 5 && cell.row === 1, {
      maxDistance: 6,
    });
    expect(path).toEqual([
      { col: 4, row: 3 },
      { col: 5, row: 3 },
      { col: 5, row: 2 },
      { col: 5, row: 1 },
    ]);
  });
});

describe('技の最中と技の出し方', () => {
  /**
   * 確認のための作り物の振る舞い。ticks のあいだ続く。
   *
   * いまの動物の振る舞いは、どれも移動を乗っ取り、爆弾を置けない。CPU の側には「乗っ取らない振る舞い」
   * 「置ける振る舞い」のときの決まりがあるので、その決まりは作り物で確認する。
   */
  function probe(options: { drivesMovement: boolean; canPlaceBomb: boolean }, ticks = 120): ActiveAction {
    let left = ticks;
    return {
      kind: 'probe',
      drivesMovement: options.drivesMovement,
      damageCap: null,
      untouchable: false,
      canPlaceBomb: options.canPlaceBomb,
      blocksButtons: false,
      sweepsItems: false,
      tick: () => {
        left -= 1;
        return { events: [], done: left <= 0 };
      },
    };
  }

  it('移動を乗っ取らない技の最中は、歩いて爆弾から逃げる', () => {
    // 技の最中を一律に「動けない」と扱うと、足元に置かれた爆弾の前で固まって当たる。
    const world = makeWorld(3, ['rabbit', 'elephant']);
    clearBoard(world);
    const cpu = world.players[0]!;
    const foe = world.players[1]!;
    foe.position = centerOf({ col: 4, row: 1 });
    const game = arena(world, [{ id: 0, level: 'oni' }]);
    cpu.action = probe({ drivesMovement: false, canPlaceBomb: false }, BOMB_FUSE + BLAST_DURATION + 30);
    foe.maxBombs = 5;
    placeBombAt(world, foe, cellOf(cpu.position));
    const hp = cpu.hp;
    game.run(BOMB_FUSE + BLAST_DURATION + 10);
    expect(cpu.action?.kind).toBe('probe');
    expect(cpu.hp).toBe(hp);
  });

  it('うさぎが撒いている間も、歩いて爆弾から逃げる（撒くのは盤面の側の物で、うさぎは乗っ取られない）', () => {
    const world = makeWorld(3, ['rabbit', 'elephant']);
    clearBoard(world);
    const cpu = world.players[0]!;
    const foe = world.players[1]!;
    grantSpecial(cpu, 1);
    foe.position = centerOf({ col: 4, row: 1 });
    const game = arena(world, [{ id: 0, level: 'oni' }]);
    for (let i = 0; i < 120 && !cpu.effects.has('scattering'); i += 1) game.run(1);
    expect(cpu.effects.has('scattering')).toBe(true);
    expect(cpu.action).toBeNull();

    foe.maxBombs = 5;
    placeBombAt(world, foe, cellOf(cpu.position));
    const hp = cpu.hp;
    game.run(BOMB_FUSE + BLAST_DURATION + 10);
    expect(cpu.hp).toBe(hp);
  });

  it('爆弾を置ける技の最中は爆弾を置き、置けない技の最中はボタンを押さない', () => {
    // 置けるかは技の canPlaceBomb が決める（ゲームの側の canPlaceBomb と同じ）。
    /** 技の最中に爆弾のボタンを押した回数と、技の最中に初めて置いた tick。 */
    const whileAction = (canPlaceBomb: boolean): { pressed: number; placedAt: number | null } => {
      const world = makeWorld(1, ['rabbit', 'frog']);
      const rabbit = world.players[0]!;
      rabbit.action = probe({ drivesMovement: false, canPlaceBomb });
      const source = new CpuInputSource(0, CPU_LEVELS.oni, 1);
      const sim = new Simulation();
      let pressed = 0;
      for (let t = 0; t < 120; t += 1) {
        // 技が続いている間だけを数える。技が終わってから置いたのでは確認にならない。
        const during = rabbit.action?.kind === 'probe';
        const input = source.next(world);
        if (during && input.bomb) pressed += 1;
        const events = sim.step(world, new Map([[0, input], [1, IDLE_INPUT]]));
        if (events.some((e) => e.type === 'bombPlaced' && e.owner === 0)) {
          return { pressed, placedAt: during ? t : null };
        }
      }
      return { pressed, placedAt: null };
    };
    expect(whileAction(true).placedAt).not.toBeNull();
    // 置けない技の最中は、CPU の判断でボタンを押さない。置いたかだけを見ると、CPU が押しても
    // ゲームの側（BombSystem の canPlaceBomb）が止めるので、CPU の判断を確認できない。
    expect(whileAction(false)).toEqual({ pressed: 0, placedAt: null });
  });

  it('安全なマスの CPU のもぐらは、とくぎを直に出して、その場で掘り始める（原型の CPU も安全なときに useSpecial を直に呼ぶ）', () => {
    const world = makeWorld(3, ['mole', 'rabbit']);
    clearBoard(world);
    const mole = world.players[0]!;
    mole.position = centerOf({ col: 5, row: 7 });
    world.players[1]!.position = centerOf({ col: 11, row: 7 });
    grantSpecial(mole, 1);
    // ラウンドの始まりと同じく、前の tick に技のボタンを押していた扱いにする（`HELD_AT_ROUND_START`）。
    // 技のボタンで出すなら、一度離す tick が要る。とくぎを直に出すボタンなら、最初の tick に出る。
    mole.previousInput = { ...IDLE_INPUT, bomb: true, action: true };
    const game = arena(world, [{ id: 0, level: 'hard' }]);
    let dugAt: number | null = null;
    for (let t = 1; t <= 60 && dugAt === null; t += 1) {
      if (game.run(1).some((e) => e.type === 'techniqueUsed' && e.player === 0 && e.special)) dugAt = t;
    }
    // 最初の tick に掘り始める。長押し（30 tick）を待たない。
    expect(dugAt).toBe(1);
    expect(mole.action?.kind).toBe('dig');
    expect(cellOf(mole.position)).toEqual({ col: 5, row: 7 });
  });

});

describe('ブロックを壊しに行く（原型 planCPU の「ソフトブロックを壊しに行く」）', () => {
  /**
   * 1行目の 1〜5 列だけが空いた細い通路。ほかは柱。`softs` のマスを壊せるブロックにして、
   * プレイヤー 0 を `at` に立たせた判断の文脈を作る。
   */
  function corridor(animal: string, softs: readonly Cell[], at: Cell): CpuContext {
    const world = makeWorld(3, [animal, 'rabbit']);
    for (const { cell, tile } of world.board.cells()) {
      if (tile !== 'hard') world.board.set(cell, 'hard');
    }
    for (let col = 1; col <= 5; col += 1) world.board.set({ col, row: 1 }, 'empty');
    for (const cell of softs) world.board.set(cell, 'soft');
    world.items = [];
    const me = world.players[0]!;
    me.position = centerOf(at);
    return new CpuContext(world, me, at, DangerMap.of(world), false, CPU_LEVELS.hard, freshMemory(new Rng(1)), new Rng(1));
  }

  it('いま立っているマスのほかに壊せる場所が無ければ、この規則は使わない（いまのマスが壊せる場所でも）', () => {
    // 原型は、壊せる場所までの道（出発点そのものは含まない）が見つかったときだけ「壊しに行く」を選ぶ。
    expect(BREAK_BLOCKS.decide(corridor('rabbit', [{ col: 1, row: 2 }], { col: 1, row: 1 }))).toBeNull();
    // 対照：もう1か所あれば、そこへの道を持ち、いまのマスで置く。
    expect(
      BREAK_BLOCKS.decide(corridor('rabbit', [{ col: 1, row: 2 }, { col: 5, row: 2 }], { col: 1, row: 1 })),
    ).toEqual({ mode: 'dig', path: [{ col: 2, row: 1 }, { col: 3, row: 1 }, { col: 4, row: 1 }, { col: 5, row: 1 }], wantBomb: true });
  });

  it('立ち位置の指定がある動物は、置くかを指定の場所に立っているかで決める（隣に立つ場所への道で妥協したときも）', () => {
    // きつねは「1マス空けた手前」に立ちたい。(1,1) と (5,1) がブロックのとき、(3,1) がその場所で、(4,1) は隣。
    // (4,1) に立てば (3,1) への道を持つが置かない（左へ並べれば (1,1) に届くが、立っているのは隣）。
    // (3,1) に立てば、ほかに指定の場所が無いので隣の (4,1) への道で妥協し、いまのマスで置く。
    // 原型のコメントは「隣に立って足元に置く」と書くが、置く判定は指定の場所のまま（コードに合わせた）。
    const soft = [{ col: 1, row: 1 }, { col: 5, row: 1 }];
    expect(BREAK_BLOCKS.decide(corridor('fox', soft, { col: 4, row: 1 }))).toEqual({
      mode: 'dig',
      path: [{ col: 3, row: 1 }],
      wantBomb: false,
    });
    expect(BREAK_BLOCKS.decide(corridor('fox', soft, { col: 3, row: 1 }))).toEqual({
      mode: 'dig',
      path: [{ col: 4, row: 1 }],
      wantBomb: true,
    });
  });

  it('きつねは、並べる向きのどれにも一列と爆風で届く壊せるブロックが無ければ置かない', () => {
    // (3,1) に立ち (5,1) がブロック。手持ち 1・火力 1 なら届く長さは 2 で (5,1) に届く。前のマスに爆弾があれば届かない。
    const ctx = corridor('fox', [{ col: 5, row: 1 }], { col: 3, row: 1 });
    expect(FOX_TACTIC.confirmsBreakBomb?.(ctx)).toBe(true);
    placeBombAt(ctx.world, ctx.world.players[1]!, { col: 4, row: 1 });
    expect(FOX_TACTIC.confirmsBreakBomb?.(ctx)).toBe(false);
  });
});

/** プレイヤー 0 が (1,1) に右向きで立つ盤面で、判断の文脈を作る（危なくない・つよい）。 */
function frogContext(world: WorldState): CpuContext {
  const me = world.players[0]!;
  me.position = centerOf({ col: 1, row: 1 });
  me.facing = 'right';
  return new CpuContext(
    world, me, { col: 1, row: 1 }, DangerMap.of(world), false, CPU_LEVELS.hard, freshMemory(new Rng(1)), new Rng(1),
  );
}

describe('かえるの舌', () => {
  it('焼けて短くなった舌が届かないアイテムには、舌を伸ばさない（原型の CPU も今の長さを見る）', () => {
    const decide = (burntTo: number | null): boolean => {
      const world = makeWorld(3, ['frog', 'rabbit']);
      clearBoard(world);
      world.items = [];
      world.items.push({ id: world.ids.take(), cell: { col: 6, row: 1 }, kind: 'fire' });
      if (burntTo !== null) world.actors.push(new BurntTongueActor(0, burntTo));
      return FROG_TACTIC.beforePlan?.when(frogContext(world)) ?? false;
    };
    // 5 マス先の火。焼けていなければ届くので伸ばし、3 マスまでに焼けていれば伸ばさない。
    expect(decide(null)).toBe(true);
    expect(decide(5)).toBe(true);
    expect(decide(3)).toBe(false);
  });

  it('チキンを持っていれば舌を伸ばさない（原型 cpuUpdate の `!p.chicken`）', () => {
    const decide = (charges: number): boolean => {
      const world = makeWorld(3, ['frog', 'rabbit']);
      clearBoard(world);
      world.items = [{ id: world.ids.take(), cell: { col: 3, row: 1 }, kind: 'fire' }];
      grantSpecial(world.players[0]!, charges);
      return FROG_TACTIC.beforePlan?.when(frogContext(world)) ?? false;
    };
    expect(decide(0)).toBe(true);
    expect(decide(1)).toBe(false);
  });

  it('舌は技のボタンを押した瞬間で伸ばし、その tick は歩かない', () => {
    expect([FROG_TACTIC.beforePlan?.button, FROG_TACTIC.beforePlan?.endsTurn]).toEqual(['action', true]);
  });
});

describe('きつねの狐火', () => {
  it('相手が歩ける道で 6 マス以内なら放ち、7 マス先なら放たない（原型の CPU は届く長さ 8 マスの 8 割まで）', () => {
    const decide = (distance: number): boolean => {
      const world = makeWorld(3, ['fox', 'rabbit']);
      clearBoard(world);
      const [me, foe] = world.players as [PlayerState, PlayerState];
      me.position = centerOf({ col: 1, row: 1 });
      foe.position = centerOf({ col: 1 + distance, row: 1 });
      grantSpecial(me, 1);
      // 技を使うかの抽選が必ず当たる強さ（skillUse 1）にする。乱数を検証するテストにしないため。
      const ctx = new CpuContext(
        world, me, { col: 1, row: 1 }, DangerMap.of(world), false, CPU_LEVELS.hard, freshMemory(new Rng(1)), new Rng(1),
      );
      return FOX_TACTIC.afterMove?.(ctx) ?? false;
    };
    expect(decide(6)).toBe(true);
    expect(decide(7)).toBe(false);
  });
});
