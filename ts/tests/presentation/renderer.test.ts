import { describe, expect, it } from 'vitest';

import { CpuInputSource, cpuSeed } from '../../src/ai/CpuInputSource.js';
import { CPU_LEVELS } from '../../src/ai/CpuLevel.js';
import { GameSession } from '../../src/app/GameSession.js';
import { TongueAction } from '../../src/domain/abilities/frog/TongueAction.js';
import { cellOf, centerOf } from '../../src/domain/core/Coord.js';
import { swapPlaces } from '../../src/domain/mutations/negibon.js';
import { enterSuddenDeath } from '../../src/domain/mutations/suddenDeath.js';
import { alongsFacing, laneSpot } from '../../src/domain/negibon/lane.js';
import { LeekActor } from '../../src/domain/negibon/LeekActor.js';
import { defaultMatchConfig } from '../../src/domain/rules/MatchConfig.js';
import { SPAWN_CELLS } from '../../src/domain/rules/tuning.js';
import { tick } from '../../src/domain/core/Tick.js';
import type { InputSource } from '../../src/domain/input/InputSource.js';
import { OUT } from '../../src/domain/state/Life.js';
import { isAlive, type PlayerState } from '../../src/domain/state/PlayerState.js';
import { hashWorld } from '../../src/domain/state/WorldState.js';
import { boardLayoutFor, layoutFor, screenX } from '../../src/presentation/render/Layout.js';
import { Renderer } from '../../src/presentation/render/Renderer.js';
import { grantSpecial, makeWorld } from '../helpers.js';
import { fakeCanvas, type FakeCanvas } from './fakeCanvas.js';

/**
 * CPU の操作に、とくぎを直に出すボタン（`PlayerInput.special`）を重ねる窓口。`wants` が真の間、1 tick おきに押す
 * （押した瞬間でないと出ないので、押したままにしない）。CPU の判断はそのまま毎 tick 進める。
 */
function pressingSpecial(cpu: InputSource, wants: () => boolean): InputSource {
  let pressed = false;
  return {
    playerId: cpu.playerId,
    next: (world) => {
      const playerInput = cpu.next(world);
      pressed = !pressed && wants();
      return pressed ? { ...playerInput, special: true } : playerInput;
    },
  };
}

/**
 * 描画の通し検査。
 *
 * CPU どうしの試合を、決着まで毎 tick 描く。舌・跳ね回る爆弾・突進・撒く技・
 * 追いかける炎・外周の葱ボンと葱が現れ、ラウンドの切り替わり（決着のあとの待ちと、
 * 盤面の作り直し）も通る。どの種で何が現れるかは、試合の中身が変わると変わるので、
 * 途中で現れたものを数えて確認している。
 */
describe('描画', () => {
  it('CPU どうしの試合を毎 tick 描いても例外が出ず、状態も変わらない', () => {
    // すべての技と外周の葱ボン・葱が現れるまで、種を順に替えて試合を実行する（上限 40 試合）。現れたものは
    // 試合をまたいで数える。種を1つに決め打ちすると、技や CPU の判断を修正して試合の流れが変わるたびに
    // 現れないものが出て、そのたびに種を選び直す（2026-10-04・10-11 に選び直した）。
    // 12 から始めるのは、2026-10-11 の時点で1試合ですべて現れた種だったため。
    // 上限は、体力の既定を爆風1回にして試合が短くなったときに 8 から広げた（2026-10-13。8 試合では
    // 追いかける炎が一度も現れなかった）。
    // とくぎの絵（跳ね回る爆弾・突進・撒く技・追いかける炎）は、ラウンドの始まりに全員へチキンを1つ渡して
    // 出す。CPU がチキンを拾うかどうかに任せると、外周の CPU を原型に合わせたとき（2026-10-18）に、
    // 40 試合のうち追いかける炎が出たのは1試合、葱のよけを合わせると0試合になった。とくぎの絵が出るかを
    // 種の運に頼らない。
    // ただし、かえるには舌が一度現れるまで渡さない。かえるの CPU はチキンを持っていると舌を伸ばさない
    // （FrogTactic の `!ctx.me.hasSpecial`。原型 L1931 の `!p.chicken` も同じ）。ラウンドの始まりに渡すと、舌が
    // 出るのは粘膜爆弾を使うか外周から戻ったあとだけになり、舌が出るかが種の運に寄る。
    // 跳ね回る爆弾は、チキンを持たせても CPU が投げるのはまれ（爆弾を置く段のあとに、危なくなく、相手まで歩いて
    // 8 マス以内にいるときだけ）。そこで、舌が現れてから跳ね回る爆弾が現れるまでの間は、盤面にいるかえるにチキンを渡し、
    // とくぎを直に出すボタン（`special`。CPU が押すボタン）を押させる。ボタンを通すので、チキンを使う・出せない
    // 間は出ない、の決まりはそのまま通る。チキンを渡すのは盤面にいるときだけにする（外周にいる間はアイテムを
    // 拾えないので、試合では起きない状態になる）。
    // 2026-10-18 に測ると、全員に渡す形では舌が初めて出たのが 7 試合目、跳ね回る爆弾が 6 試合目の6ラウンド目
    // だった。この形では、どちらも1試合目の2ラウンド目に出る。
    const animals = ['rabbit', 'frog', 'elephant', 'fox'];
    const wanted = ['tongue', 'slime', 'charge', 'scatter', 'foxfire', 'negibon', 'leek'];
    const canvas = fakeCanvas({ keepLog: false });
    const seen = new Set<string>();
    const wantsSlime = (): boolean => seen.has('tongue') && !seen.has('slime');
    let matches = 0;
    for (let seed = 12; seed < 52 && !wanted.every((kind) => seen.has(kind)); seed += 1) {
      const game = new GameSession({ ...defaultMatchConfig(seed, animals), winsToTake: 2 });
      game.world.players.forEach((player) => {
        const cpu = new CpuInputSource(player.id, CPU_LEVELS.oni, cpuSeed(seed, player.id));
        game.attach(player.animal === 'frog' ? pressingSpecial(cpu, wantsSlime) : cpu);
      });
      const renderer = new Renderer(canvas.context, layoutFor(920, 680));
      let intermissions = 0;
      let granted: unknown = null;
      let frogGranted: unknown = null;
      // 試合の長さは種によって大きく変わる（この顔ぶれで 80 通りの種を試すと 6,967〜29,303 tick。
      // 2026-10-11 に測った）。上限は余裕を見て大きくとる。
      for (let i = 0; i < 60000 && !game.match.finished; i += 1) {
        const world = game.world;
        if (world !== granted) {
          for (const player of world.players) if (player.animal !== 'frog') grantSpecial(player, 1);
          granted = world;
        }
        if (world !== frogGranted && wantsSlime()) {
          const frog = world.players.find((player) => player.animal === 'frog' && isAlive(player));
          if (frog !== undefined) {
            grantSpecial(frog, 1);
            frogGranted = world;
          }
        }
        renderer.beforeTick(world);
        const events = game.tick();
        renderer.afterTick(events, world);
        if (game.betweenRounds) intermissions += 1;
        for (const actor of game.world.actors) seen.add(actor.kind);
        for (const player of game.world.players) {
          if (player.action !== null) seen.add(player.action.kind);
          if (player.life.kind === 'negibon') seen.add('negibon');
        }
        const before = hashWorld(game.world);
        renderer.draw(game.world, 0.5);
        expect(hashWorld(game.world)).toBe(before);
      }
      expect(game.match.finished, `種 ${seed}`).toBe(true);
      expect(intermissions, `種 ${seed}`).toBeGreaterThan(0);
      matches += 1;
    }
    expect(matches).toBeGreaterThan(0);
    for (const kind of wanted) {
      expect(seen.has(kind), kind).toBe(true);
    }
    // 数万回の描画を偽の canvas に通すので、既定の制限時間では足りない。
  }, 600_000);

  it('延長戦で開始位置へ飛び移ったプレイヤーを、前の位置との途中に描かない', () => {
    // 歩いた距離なら間を埋めると滑らかに見えるが、飛び移ったぶんを埋めると
    // 盤面を横切って滑っていくように見える。
    const world = makeWorld(3, ['rabbit']);
    world.players[0]!.position = { x: 20.5, y: 14.5 };
    const canvas = fakeCanvas();
    const renderer = new Renderer(canvas.context, layoutFor(920, 680));
    renderer.beforeTick(world);
    renderer.afterTick(enterSuddenDeath(world, [0], 'timeUp'), world);
    renderer.draw(world, 0.5);

    const layout = layoutFor(920, 680);
    const spawn = centerOf(SPAWN_CELLS[0]!);
    const drawnAt = canvas.log.filter((call) => call.name === 'translate').map((call) => call.args[0] as number);
    const near = (x: number): boolean => drawnAt.some((drawn) => Math.abs(drawn - screenX(layout, x)) < 1);
    expect(near(spawn.x)).toBe(true);
    expect(near((20.5 + spawn.x) / 2)).toBe(false);
  });

  it('葱を当てて戻ったプレイヤーを、倒れた場所との途中に描かない', () => {
    // 外周にいる間は描かないので、1つ前の位置は倒れた場所のまま残っている。
    const world = makeWorld(3, ['rabbit', 'elephant']);
    const [shooter, target] = world.players as [PlayerState, PlayerState];
    shooter.position = { x: 20.5, y: 14.5 };
    shooter.life = { kind: 'negibon', along: 0, readyAt: tick(0) };
    target.position = { x: 1.5, y: 3.5 };
    const canvas = fakeCanvas();
    const renderer = new Renderer(canvas.context, layoutFor(920, 680));
    renderer.beforeTick(world);
    renderer.afterTick(swapPlaces(world, shooter, target), world);
    renderer.draw(world, 0.5);

    const layout = layoutFor(920, 680);
    const drawnAt = canvas.log.filter((call) => call.name === 'translate').map((call) => call.args[0] as number);
    const near = (x: number): boolean => drawnAt.some((drawn) => Math.abs(drawn - screenX(layout, x)) < 1);
    expect(near(1.5)).toBe(true);
    expect(near((20.5 + 1.5) / 2)).toBe(false);
  });

  it('外周の葱ボンと飛んでいる葱のいる盤面を描いても例外が出ず、状態も変わらない', () => {
    // 試合を通す検査では、葱ボンが出るか・葱が飛ぶかは CPU の振る舞い次第なので、ここで置く。
    const sides = alongsFacing({ col: 5, row: 5 });
    const drawWith = (leeks: boolean): FakeCanvas => {
      const world = makeWorld(3, ['rabbit', 'elephant', 'frog', 'fox']);
      world.now = tick(600);
      world.players[1]!.life = { kind: 'negibon', along: sides[0], readyAt: world.now };
      world.players[2]!.life = { kind: 'negibon', along: sides[2], readyAt: tick(world.now + 30) };
      if (leeks) {
        for (const along of sides) {
          const spot = laneSpot(along);
          world.actors.push(new LeekActor(spot.position, spot.facing, 1));
        }
      }
      const canvas = fakeCanvas();
      const before = hashWorld(world);
      new Renderer(canvas.context, layoutFor(920, 680)).draw(world, 0.5);
      expect(hashWorld(world)).toBe(before);
      return canvas;
    };

    const canvas = drawWith(true);
    // 撃つ向きの点線を引くのは葱ボンの絵だけなので、葱ボン1人につき1回になる。
    expect(canvas.calls.get('setLineDash') ?? 0).toBe(2);
    // 葱は1本につき1回、飛ぶ向きへ回す。
    const rotations = (drawn: FakeCanvas): number => drawn.calls.get('rotate') ?? 0;
    expect(rotations(canvas) - rotations(drawWith(false))).toBe(sides.length);
  });

  it('盤面にいないプレイヤーの、止まったまま残っている舌は描かない（原型の drawPlayer L4753 は盤面にいないプレイヤーを描かずに返る）', () => {
    // 倒れたかえるの舌は、外周にいる間も退場したあとも外さずに止めておく（`TongueAction.staysOffBoard`）。
    // 描くのは盤面にいるプレイヤーだけなので、止まった舌は見えない。
    const drawWith = (life: 'negibon' | 'out' | 'alive', tongue: boolean): FakeCanvas['log'] => {
      const world = makeWorld(3, ['frog', 'rabbit']);
      const frog = world.players[0]!;
      frog.position = centerOf({ col: 3, row: 5 });
      frog.facing = 'right';
      const action = new TongueAction(cellOf(frog.position), frog.facing);
      for (let t = 1; t <= 40; t += 1) action.tick(world, frog);
      if (tongue) frog.action = action;
      if (life === 'negibon') frog.life = { kind: 'negibon', along: 5, readyAt: tick(0) };
      if (life === 'out') frog.life = OUT;
      const canvas = fakeCanvas();
      new Renderer(canvas.context, layoutFor(920, 680)).draw(world, 0.5);
      return canvas.log;
    };
    expect(drawWith('negibon', true)).toEqual(drawWith('negibon', false));
    expect(drawWith('out', true)).toEqual(drawWith('out', false));
    // 対照：盤面にいれば舌を描く（同じ比べ方で違いが出る）。
    expect(drawWith('alive', true)).not.toEqual(drawWith('alive', false));
  });
});

describe('ポーズの幕（原型の draw の最後。L4566-4573）', () => {
  /** 呼んだ命令と、書いた値（`fillStyle` など）を、起きた順に控える canvas。命令は偽の canvas に渡す。 */
  function recordingCanvas(): { context: CanvasRenderingContext2D; steps: string[] } {
    const fake = fakeCanvas({ keepLog: false });
    const steps: string[] = [];
    const target = fake.context as unknown as Record<string, unknown>;
    const context = new Proxy(target, {
      get(_target, property) {
        const value = target[property as string];
        if (typeof value !== 'function') return value;
        return (...args: unknown[]) => {
          steps.push(`${String(property)}(${args.map((arg) => JSON.stringify(arg)).join(',')})`);
          return (value as (...a: unknown[]) => unknown)(...args);
        };
      },
      set(_target, property, value) {
        steps.push(`${String(property)}=${JSON.stringify(value)}`);
        target[property as string] = value;
        return true;
      },
    }) as unknown as CanvasRenderingContext2D;
    return { context, steps };
  }

  it('止めている間は、盤面全体を暗くし、真ん中に PAUSE、30px 下に「P で再開」を、原型の色と書体で描く', () => {
    const { context, steps } = recordingCanvas();
    new Renderer(context, layoutFor(920, 680)).draw(makeWorld(3, ['rabbit']), 0.5, true);
    const start = steps.lastIndexOf('fillStyle="rgba(10,6,4,.6)"');
    expect(start).toBeGreaterThan(0);
    expect(steps.slice(start)).toEqual([
      'fillStyle="rgba(10,6,4,.6)"',
      'fillRect(0,0,920,680)',
      'fillStyle="#ffd23f"',
      'font="900 34px system-ui"',
      'textAlign="center"',
      'textBaseline="middle"',
      'fillText("PAUSE",460,340)',
      'font="600 14px system-ui"',
      'fillStyle="#c9ab97"',
      'fillText("P で再開",460,370)',
      // 画面の揺れ（save のあとの平行移動）の内側で描き、最後に戻す（原型と同じ）。
      'restore()',
    ]);
    expect(steps.lastIndexOf('save()')).toBeLessThan(start);
  });

  it('止めていなければ描かない', () => {
    const { context, steps } = recordingCanvas();
    new Renderer(context, layoutFor(920, 680)).draw(makeWorld(3, ['rabbit']), 0.5);
    expect(steps.some((step) => step.startsWith('fillText("PAUSE"'))).toBe(false);
    expect(steps).not.toContain('fillStyle="rgba(10,6,4,.6)"');
  });

  it('寸法を替えたら（窓の大きさが替わったとき）、新しい寸法で描く', () => {
    const { context, steps } = recordingCanvas();
    const renderer = new Renderer(context, layoutFor(920, 680));
    renderer.resize(boardLayoutFor(1440, 900));
    renderer.draw(makeWorld(3, ['rabbit']), 0.5, true);
    expect(steps).toContain('fillRect(0,0,1115,839)');
    expect(steps).toContain('fillText("PAUSE",557.5,419.5)');
  });
});

describe('盤面の寸法を窓の大きさから決める（原型の fitBoard。L583-606）', () => {
  it('窓の幅から横の板などの 312px、高さから 56px を引いた所に入る、いちばん大きいマスにする', () => {
    // 1440×900：幅 1128 / 24.24 = 46.5…、高さ 844 / 18.24 = 46.2… → 46。描画面は 24.24 × 46 と 18.24 × 46 を丸める。
    expect(boardLayoutFor(1440, 900)).toEqual({ tile: 46, originX: 0.62 * 46, originY: 0.62 * 46, width: 1115, height: 839 });
    // 1024×768：幅 712 / 24.24 = 29.3… が狭いほう → 29。
    expect(boardLayoutFor(1024, 768)).toMatchObject({ tile: 29, width: 703, height: 529 });
    // 高さが狭いほうになるとき（1920×900：幅 1608 / 24.24 = 66.3…、高さ 844 / 18.24 = 46.2…）。
    expect(boardLayoutFor(1920, 900).tile).toBe(46);
  });

  it('マスは 26 より小さくせず、96 より大きくしない（原型の TILE_MIN・TILE_MAX）。読めない大きさ（0）は 1280×800 とみなす', () => {
    expect(boardLayoutFor(300, 200).tile).toBe(26);
    expect(boardLayoutFor(5000, 3000).tile).toBe(96);
    expect(boardLayoutFor(0, 0)).toEqual(boardLayoutFor(1280, 800));
    expect(boardLayoutFor(1280, 800).tile).toBe(39);
  });

  it('描画面から決め直すと1つ小さいマスになる大きさでも、決めたマスのまま（丸めた幅を割ると、わずかに足りない）', () => {
    const layout = boardLayoutFor(1440, 900);
    expect(layoutFor(layout.width, layout.height).tile).toBe(45);
    expect(layout.tile).toBe(46);
  });
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
