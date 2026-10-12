import { describe, expect, it } from 'vitest';

import { footBomb, decideBomb } from '../../src/ai/BombPlacement.js';
import { ButtonMacro } from '../../src/ai/ButtonMacro.js';
import type { CpuBehavior } from '../../src/ai/CpuBehavior.js';
import { CpuContext } from '../../src/ai/CpuContext.js';
import { CpuInputSource, cpuSeed } from '../../src/ai/CpuInputSource.js';
import { CPU_LEVELS, type CpuLevelKey } from '../../src/ai/CpuLevel.js';
import { freshMemory, type CpuMemory } from '../../src/ai/CpuMemory.js';
import { DEFAULT_CHAIN } from '../../src/ai/behaviors/DefaultChain.js';
import { FLEE } from '../../src/ai/behaviors/Flee.js';
import { OUT_OF_BOMBS_BAN, SAME_SPOT_BAN, UNSAFE_SPOT_BAN } from '../../src/ai/margins.js';
import { directionAlong } from '../../src/ai/PathFollower.js';
import { FOX_TACTIC } from '../../src/ai/tactics/FoxTactic.js';
import { FROG_TACTIC } from '../../src/ai/tactics/FrogTactic.js';
import { BurntTongueActor } from '../../src/domain/abilities/frog/TongueAction.js';
import type { ActiveAction } from '../../src/domain/abilities/ActiveAction.js';
import { abilityOf } from '../../src/domain/abilities/registry.js';
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
import { isAlive, type PlayerId, type PlayerState } from '../../src/domain/state/PlayerState.js';
import { hashWorld, type WorldState } from '../../src/domain/state/WorldState.js';
import { Simulation } from '../../src/domain/systems/Simulation.js';
import { clearBoard, makeWorld } from '../helpers.js';


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
    // 要約には試合の乱数を引いた回数も入るので、試合の乱数を引いていないことも分かる。
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
    // 対照：CPU の種だけを変えると別の試合になる。種が効いていることの確認。
    expect(play(1)).not.toBe(play(0));
  });
});

describe('身を守る', () => {
  it('足元に置かれた爆弾から逃げ切る', () => {
    const world = makeWorld(3, ['rabbit', 'elephant']);
    const cpu = world.players[0]!;
    const game = arena(world, [{ id: 0, level: 'hard' }]);
    placeBomb(world, cpu);
    const hp = cpu.hp;
    game.run(BOMB_FUSE + BLAST_DURATION + 10);
    expect(isAlive(cpu)).toBe(true);
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
    // 原型で「袋小路では置かない」を入れたところ、つよい CPU が
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

  it('とくぎは、人間と同じく長押しで出す', () => {
    const world = makeWorld(3, ['rabbit', 'elephant']);
    clearBoard(world);
    const cpu = world.players[0]!;
    cpu.specialCharges = 1;
    world.players[1]!.position = centerOf({ col: 4, row: 1 });
    const game = arena(world, [{ id: 0, level: 'hard' }]);
    game.run(abilityOf('rabbit').holdTicks + 5);
    expect(cpu.specialCharges).toBe(0);
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
    expect(decideBomb(ctx, [footBomb(ctx)])).not.toBeNull();
  });

  it('逃げ切れないなら置かず、しばらく爆弾を狙わない', () => {
    const world = makeWorld(3);
    clearBoard(world);
    world.board.set({ col: 2, row: 1 }, 'soft');
    world.board.set({ col: 1, row: 2 }, 'soft');
    const { ctx, memory } = context(world);
    expect(decideBomb(ctx, [footBomb(ctx)])).toBeNull();
    expect(memory.bombBan).toBe(UNSAFE_SPOT_BAN);
  });

  it('⛔ 少し前に置いたマスには置き直さない', () => {
    // 置く → 自分の爆風から逃げて離れる → 爆発が終わると戻ってまた置く、の往復を防ぐ。
    const world = makeWorld(3);
    clearBoard(world);
    const { ctx, memory } = context(world);
    memory.lastBomb = { cell: { col: 1, row: 1 }, at: tick(world.now - SAME_SPOT_BAN + 1) };
    expect(decideBomb(ctx, [footBomb(ctx)])).toBeNull();
    expect(memory.bombBan).toBe(UNSAFE_SPOT_BAN);
  });

  it('十分に時間がたてば、同じマスにも置ける', () => {
    const world = makeWorld(3);
    clearBoard(world);
    const { ctx, memory } = context(world);
    memory.lastBomb = { cell: { col: 1, row: 1 }, at: tick(world.now - SAME_SPOT_BAN) };
    expect(decideBomb(ctx, [footBomb(ctx)])).not.toBeNull();
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
      return decideBomb(ctx, [footBomb(ctx)]);
    };
    expect(decide(false)).toBeNull();
    expect(decide(true)).not.toBeNull();
  });

  it('自分の爆弾が多すぎるときは、短く待つだけにする', () => {
    const world = makeWorld(3);
    clearBoard(world);
    const me = world.players[0]!;
    me.maxBombs = 10;
    for (const col of [9, 11, 13]) placeBombAt(world, me, { col, row: 9 });
    const { ctx, memory } = context(world);
    expect(decideBomb(ctx, [footBomb(ctx)])).toBeNull();
    expect(memory.bombBan).toBe(OUT_OF_BOMBS_BAN);
  });
});

describe('ボタンの押し方の手順', () => {
  function drain(macro: ButtonMacro) {
    const steps = [];
    for (let step = macro.next(); step !== null; step = macro.next()) steps.push(step);
    return steps;
  }

  it('爆弾は1 tick 押して、次の tick に離す', () => {
    // 押しっぱなしにすると、ゲームの側からは押し下げた瞬間が1回しか無い。
    const steps = drain(ButtonMacro.dropBomb());
    expect(steps.map((s) => s.bomb)).toEqual([true, false]);
    // 置く瞬間は歩かない。歩くと隣のマスに置いてしまう。
    expect(steps[0]!.still).toBe(true);
  });

  it('長押しは指定の長さだけ押し続けてから離す', () => {
    const steps = drain(ButtonMacro.hold(3, false));
    expect(steps.map((s) => s.action)).toEqual([true, true, true, false]);
  });

  it('向きを変えてから技を出せる', () => {
    const steps = drain(ButtonMacro.facing('up', ButtonMacro.tap()));
    expect(steps.map((s) => [s.face, s.action])).toEqual([
      ['up', false],
      [null, true],
      [null, false],
    ]);
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

  it('延長戦に入ったら、それまでの記憶を捨てる', () => {
    // 延長戦では盤面を作り直さず、全員を開始位置へ移す。盤面が同じものなので、
    // 作り直しだけを見ていると、移る前の場所で立てた道筋をたどり続ける。
    const world = makeWorld(3, ['rabbit', 'elephant']);
    const source = new CpuInputSource(0, CPU_LEVELS.hard, 1);
    const sim = new Simulation();
    for (let i = 0; i < 600 && source.memory.lastBomb === null; i += 1) {
      sim.step(world, new Map([[0, source.next(world)]]));
    }
    expect(source.memory.lastBomb).not.toBeNull();

    enterSuddenDeath(world, [0, 1], 'timeUp');
    source.next(world);
    expect(source.memory.lastBomb).toBeNull();
  });
});

describe('経路の追従', () => {
  it('経路が尽きても、マスの端では止まらず中央へ寄る', () => {
    // 端に立つと体が隣のマスにはみ出し、そこへ来た爆風に当たる。
    // 実際に、強い CPU の自爆の多くがこれだった。
    const world = makeWorld(3);
    const me = world.players[0]!;
    me.position = { x: 5.5, y: 2.11 };
    expect(directionAlong(me, [])).toBe('down');
    me.position = centerOf({ col: 5, row: 2 });
    expect(directionAlong(me, [])).toBeNull();
  });

  it('隣のマスへ向かうときは、位置の違う軸だけを押す', () => {
    // 直角の軸まで押すと、中央を挟んで左右に震えて前へ進まない。
    // 通路の中央へ寄せるのはゲームの側の移動処理がやる。
    const world = makeWorld(3);
    const me = world.players[0]!;
    me.position = { x: 9.46, y: 1.5 };
    expect(directionAlong(me, [{ col: 9, row: 2 }])).toBe('down');
  });
});

describe('技の最中と技の出し方', () => {
  /**
   * 確かめのための作り物の振る舞い。ticks のあいだ続く。
   *
   * いまの動物の振る舞いは、どれも移動を乗っ取り、爆弾を置けない。CPU の側には「乗っ取らない振る舞い」
   * 「置ける振る舞い」のときの決まりがあるので、その決まりは作り物で確かめる。
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
    cpu.specialCharges = 1;
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
        // 技が続いている間だけを数える。技が終わってから置いたのでは確かめにならない。
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
    // ゲームの側（BombSystem の canPlaceBomb）が止めるので、CPU の判断を確かめられない。
    expect(whileAction(false)).toEqual({ pressed: 0, placedAt: null });
  });

  it('押して離すだけの技は、途中で危なくなっても向きを変えずに出し切る', () => {
    // 一列に並べる技の途中で歩かせると向きが変わり、自分の逃げ道に爆弾を並べる。
    const world = makeWorld(3, ['fox', 'rabbit']);
    clearBoard(world);
    const fox = world.players[0]!;
    const enemy = world.players[1]!;
    fox.position = centerOf({ col: 5, row: 1 });
    fox.maxBombs = 3;
    const source = new CpuInputSource(0, CPU_LEVELS.oni, 1);
    const sim = new Simulation();
    const step = (): void => {
      sim.step(world, new Map([[0, source.next(world)], [1, IDLE_INPUT]]));
    };
    step(); // 記憶を作る（盤面が変わった扱い）
    (source.memory as CpuMemory).macro = ButtonMacro.facing('right', ButtonMacro.tap());
    step(); // 右を向く
    enemy.maxBombs = 5;
    enemy.power = 2;
    placeBombAt(world, enemy, { col: 7, row: 1 });
    step(); // 押す → 一列が出る
    step(); // 離す
    const mine = world.bombs.filter((bomb) => bomb.owner === 0);
    expect(mine.length).toBeGreaterThan(0);
    expect(mine.every((bomb) => bomb.cell.row === 1)).toBe(true);
  });

  it('安全なマスの CPU のもぐらは、長押しせずにその場で押して離して掘り始める（原型の CPU も安全なときに useSpecial を直に呼ぶ）', () => {
    const world = makeWorld(3, ['mole', 'rabbit']);
    clearBoard(world);
    const mole = world.players[0]!;
    mole.position = centerOf({ col: 5, row: 7 });
    world.players[1]!.position = centerOf({ col: 11, row: 7 });
    mole.specialCharges = 1;
    const game = arena(world, [{ id: 0, level: 'hard' }]);
    let dugAt: number | null = null;
    for (let t = 1; t <= 60 && dugAt === null; t += 1) {
      if (game.run(1).some((e) => e.type === 'techniqueUsed' && e.player === 0 && e.special)) dugAt = t;
    }
    // ラウンドの始まりの「とくぎを出し終えた扱い」が外れる tick・押す tick（押した tick に掘り始める）。
    // 長押し（30 tick）を待たない。
    expect(dugAt).toBe(2);
    expect(mole.action?.kind).toBe('dig');
    expect(cellOf(mole.position)).toEqual({ col: 5, row: 7 });
  });

  it('立ち止まって長押ししている途中で危なくなったら、離さずに押し続けたまま歩いて逃げる（離すと、この押し方のとくぎが出ない）', () => {
    // 押した瞬間の通常技（鼻水）は出る（ActionSystem）。危なくなってから、長押しのしきい値に届く前までを見る。
    const holdThenDanger = (animal: string): { used: number; moved: boolean; held: number } => {
      const world = makeWorld(3, [animal, 'rabbit']);
      clearBoard(world);
      const me = world.players[0]!;
      const enemy = world.players[1]!;
      me.position = centerOf({ col: 5, row: 7 });
      enemy.position = centerOf({ col: 15, row: 7 });
      me.specialCharges = 1;
      const holdTicks = abilityOf(animal).holdTicks;
      const source = new CpuInputSource(0, CPU_LEVELS.oni, 1);
      const sim = new Simulation();
      let used = 0;
      const step = (): void => {
        const events = sim.step(world, new Map([[0, source.next(world)], [1, IDLE_INPUT]]));
        used += events.filter((e) => e.type === 'techniqueUsed' && e.player === 0).length;
      };
      step(); // 記憶を作る（盤面が変わった扱い）
      (source.memory as CpuMemory).macro = ButtonMacro.hold(holdTicks, true);
      for (let t = 0; t < 10; t += 1) step();
      const start = cellOf(me.position);
      enemy.maxBombs = 5;
      enemy.power = 3;
      placeBombAt(world, enemy, { col: 7, row: 7 });
      for (let t = 0; t < holdTicks - 15; t += 1) step();
      const now = cellOf(me.position);
      return { used, moved: now.col !== start.col || now.row !== start.row, held: me.actionHeld };
    };
    const holdTicks = abilityOf('elephant').holdTicks;
    expect(holdThenDanger('elephant')).toEqual({ used: 1, moved: true, held: holdTicks - 5 });
  });

  it('立ち位置の指定がある動物も、ブロックの隣しか無ければ足元に置いて壊す', () => {
    // きつねは「1マス空けた手前」に立ちたいが、行き止まりにはその場所が無い。
    // 妥協して隣に立ったなら、そこで置かないと永久に出られない。
    const world = makeWorld(3, ['fox', 'rabbit']);
    for (const { cell, tile } of world.board.cells()) {
      if (tile !== 'hard') world.board.set(cell, 'hard');
    }
    for (let col = 1; col <= 5; col += 1) world.board.set({ col, row: 1 }, 'empty');
    world.board.set({ col: 1, row: 2 }, 'soft');
    const game = arena(world, [{ id: 0, level: 'hard' }]);
    const events = game.run(300);
    expect(events.some((e) => e.type === 'bombPlaced' && e.owner === 0)).toBe(true);
  });
});

describe('かえるの舌', () => {
  it('焼けて短くなった舌が届かないアイテムには、舌を伸ばさない（原型の CPU も今の長さを見る）', () => {
    const decide = (burntTo: number | null): ButtonMacro | null => {
      const world = makeWorld(3, ['frog', 'rabbit']);
      clearBoard(world);
      world.items = [];
      const me = world.players[0]!;
      me.position = centerOf({ col: 1, row: 1 });
      me.facing = 'right';
      world.items.push({ id: world.ids.take(), cell: { col: 6, row: 1 }, kind: 'fire' });
      if (burntTo !== null) world.actors.push(new BurntTongueActor(me.id, burntTo));
      const ctx = new CpuContext(
        world, me, { col: 1, row: 1 }, DangerMap.of(world), false, CPU_LEVELS.hard, freshMemory(new Rng(1)), new Rng(1),
      );
      return FROG_TACTIC.reflex?.(ctx) ?? null;
    };
    // 5 マス先の火。焼けていなければ届くので伸ばし、3 マスまでに焼けていれば伸ばさない。
    expect(decide(null)).not.toBeNull();
    expect(decide(5)).not.toBeNull();
    expect(decide(3)).toBeNull();
  });
});

describe('きつねの狐火', () => {
  it('相手が歩ける道で 6 マス以内なら放ち、7 マス先なら放たない（原型の CPU は届く長さ 8 マスの 8 割まで）', () => {
    const decide = (distance: number): ButtonMacro | null => {
      const world = makeWorld(3, ['fox', 'rabbit']);
      clearBoard(world);
      const [me, foe] = world.players as [PlayerState, PlayerState];
      me.position = centerOf({ col: 1, row: 1 });
      foe.position = centerOf({ col: 1 + distance, row: 1 });
      me.specialCharges = 1;
      // 技を使うかの抽選が必ず当たる強さ（skillUse 1）にする。乱数を確かめるテストにしないため。
      const ctx = new CpuContext(
        world, me, { col: 1, row: 1 }, DangerMap.of(world), false, CPU_LEVELS.hard, freshMemory(new Rng(1)), new Rng(1),
      );
      return FOX_TACTIC.reflex?.(ctx) ?? null;
    };
    expect(decide(6)).not.toBeNull();
    expect(decide(7)).toBeNull();
  });
});
