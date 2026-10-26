import { describe, expect, it } from 'vitest';

import { CpuInputSource, cpuSeed } from '../../src/ai/CpuInputSource.js';
import { CPU_LEVELS } from '../../src/ai/CpuLevel.js';
import { GameSession } from '../../src/app/GameSession.js';
import { ANIMAL_LOOKS } from '../../src/content/animals.js';
import { centerOf } from '../../src/domain/core/Coord.js';
import { secondsToTicks } from '../../src/domain/core/Tick.js';
import type { PlayerId } from '../../src/domain/state/PlayerState.js';
import { POOP_EFFECTS } from '../../src/domain/rules/items.js';
import { SPAWN_CELLS } from '../../src/domain/rules/tuning.js';
import { POOP_MARKS } from '../../src/presentation/hud/effectLabels.js';
import { tagOf } from '../../src/presentation/hud/roster.js';
import { hitsForHp, hpForHits } from '../../src/presentation/menu/choices.js';
import { DEFAULT_SETUP, planLocalMatch, type LocalSetup } from '../../src/presentation/menu/localSetup.js';
import { MenuFlow } from '../../src/presentation/menu/MenuFlow.js';

describe('選んだものから試合を作る', () => {
  it('1人で遊ぶときは、人間1人と CPU 3体', () => {
    const plan = planLocalMatch({ ...DEFAULT_SETUP, mode: 'solo', picks: ['fox', 'frog'] }, 11);
    expect(plan.config.animals).toHaveLength(4);
    expect(plan.config.animals[0]).toBe('fox');
    expect(plan.controllers).toEqual([
      { kind: 'keys', layout: 'solo' },
      { kind: 'cpu', level: 'normal' },
      { kind: 'cpu', level: 'normal' },
      { kind: 'cpu', level: 'normal' },
    ]);
    expect(plan.roster.map((c) => c.kind)).toEqual(['human', 'cpu', 'cpu', 'cpu']);
    // 1台を囲んでいる全員が同じ画面を見ているので、「あなた」の印は付けない。
    expect(tagOf(plan.roster, 0)).toBe('1P');
    // CPU は何体目かを付ける（原型の `CPU${cpuIdx+1}`。L5507）。
    expect([1, 2, 3].map((id) => tagOf(plan.roster, id as PlayerId))).toEqual([
      'CPU1・ふつう',
      'CPU2・ふつう',
      'CPU3・ふつう',
    ]);
  });

  it('2人のときはキーボードを左右に分け、タイマンでは CPU を入れない', () => {
    const duo = planLocalMatch({ ...DEFAULT_SETUP, mode: 'duo' }, 11);
    expect(duo.controllers.slice(0, 2)).toEqual([
      { kind: 'keys', layout: 'left' },
      { kind: 'keys', layout: 'right' },
    ]);
    expect(duo.config.animals).toHaveLength(4);

    const versus = planLocalMatch({ ...DEFAULT_SETUP, mode: 'versus', picks: ['mole', 'mole'] }, 11);
    expect(versus.config.animals).toEqual(['mole', 'mole']);
    // タイマンも左右に分ける。1人ぶんの操作（solo）にすると、パッドまで試合に繋がり、
    // 試合が決まった幕でもパッドを受け付ける（Shell の drivesPad）。
    expect(versus.controllers).toEqual([
      { kind: 'keys', layout: 'left' },
      { kind: 'keys', layout: 'right' },
    ]);
  });

  it('CPU の動物は、人間が選ばなかった動物から重ならずに選ぶ', () => {
    for (let seed = 0; seed < 50; seed += 1) {
      const animals = planLocalMatch({ ...DEFAULT_SETUP, mode: 'duo', picks: ['rabbit', 'frog'] }, seed).config.animals;
      const cpu = animals.slice(2);
      expect(cpu.some((a) => a === 'rabbit' || a === 'frog')).toBe(false);
      expect(new Set(cpu).size).toBe(cpu.length);
    }
  });

  it('CPU の顔ぶれは種で決まり、種が違えば変わりうる', () => {
    const setup: LocalSetup = { ...DEFAULT_SETUP, mode: 'solo', picks: ['rabbit', 'frog'] };
    expect(planLocalMatch(setup, 3).config.animals).toEqual(planLocalMatch(setup, 3).config.animals);
    const lineups = new Set(
      Array.from({ length: 20 }, (_, seed) => planLocalMatch(setup, seed).config.animals.join(',')),
    );
    expect(lineups.size).toBeGreaterThan(1);
  });

  it('体力・CPU の強さ・勝ち数・時間・延長戦が、そのまま設定に入る', () => {
    const plan = planLocalMatch(
      {
        ...DEFAULT_SETUP,
        mode: 'duo',
        hits: { p1: 1, p2: 5, cpu: 2 },
        cpuLevels: ['oni', 'easy', 'hard'],
        winsToTake: 7,
        roundSeconds: 60,
        suddenDeath: false,
      },
      99,
    );
    expect(plan.config).toMatchObject({
      startingHp: [2, 10, 4, 4],
      winsToTake: 7,
      roundLimit: secondsToTicks(60),
      suddenDeath: false,
      seed: 99,
    });
    // CPU の強さは、前から CPU の数だけ使う（3体目の値は使わない）。
    expect(plan.controllers.slice(2)).toEqual([
      { kind: 'cpu', level: 'oni' },
      { kind: 'cpu', level: 'easy' },
    ]);
  });

  it('開始位置は原型と同じ。2人＋CPU2体では、2P が右下、CPU が右上と左下から始まる', () => {
    // 原型の setupPlayers：1P は左上。2人のときの 2P は右下（対角）。CPU は残りの隅を右上・左下・右下の順に使う。
    // 画面で選んだものから本物の試合を作り、プレイヤーが立っている隅の番号を読む。
    const cornersOf = (mode: LocalSetup['mode']): number[] => {
      const game = new GameSession(planLocalMatch({ ...DEFAULT_SETUP, mode }, 11).config);
      return game.world.players.map((player) =>
        SPAWN_CELLS.findIndex((cell) => {
          const center = centerOf(cell);
          return center.x === player.position.x && center.y === player.position.y;
        }),
      );
    };
    expect(cornersOf('solo')).toEqual([0, 1, 2, 3]);
    expect(cornersOf('duo')).toEqual([0, 3, 1, 2]);
    expect(cornersOf('versus')).toEqual([0, 3]);
  });

  it('作った設定で、試合が最後まで進む（2人のタイマンも）', () => {
    // 2人だけの試合は、ほかのテストの多くが前提にしている4人の形と違う。
    for (const mode of ['solo', 'versus'] as const) {
      const plan = planLocalMatch({ ...DEFAULT_SETUP, mode, winsToTake: 3, roundSeconds: 60 }, 5);
      const game = new GameSession({ ...plan.config, winsToTake: 1 });
      // 人間の代わりに CPU を繋ぐ。画面なしで決着まで進めるため。
      for (const player of game.world.players) {
        game.attach(new CpuInputSource(player.id, CPU_LEVELS.hard, cpuSeed(plan.config.seed, player.id)));
      }
      for (let i = 0; i < 60_000 && !game.match.finished; i += 1) game.tick();
      expect(game.match.finished, mode).toBe(true);
    }
  }, 60_000);
});

describe('画面の流れ', () => {
  it('タイトル → 動物 → ルール と進み、もどるで1つずつ戻る', () => {
    const flow = new MenuFlow();
    flow.chooseMode('duo');
    expect(flow.screen).toBe('pick');
    flow.next();
    expect(flow.screen).toBe('rules');
    flow.back();
    expect(flow.screen).toBe('pick');
    flow.back();
    expect(flow.screen).toBe('title');
    flow.back();
    expect(flow.screen).toBe('title');
  });

  it('遊び方を行き来しても、選んだものは残る', () => {
    const flow = new MenuFlow();
    flow.chooseMode('duo');
    flow.pick(1, 'mole');
    flow.back();
    flow.chooseMode('solo');
    flow.back();
    flow.chooseMode('duo');
    expect(flow.setup.picks[1]).toBe('mole');
  });

  it('その遊び方にいない人や、選べない値は受け付けない', () => {
    const flow = new MenuFlow();
    flow.chooseMode('solo');
    expect(() => flow.pick(1, 'fox')).toThrow('2P はいない');
    expect(() => flow.pick(0, 'dragon')).toThrow('知らない動物');
    expect(() => flow.setWinsToTake(4)).toThrow('勝ち数');
    expect(() => flow.setHits('p1', 0)).toThrow('爆風の回数');
    flow.chooseMode('versus');
    expect(() => flow.setCpuLevel(0, 'hard')).toThrow('CPU1 はいない');
  });
});

describe('表どうしの食い違い', () => {
  it('爆風の回数と体力は行き来できる', () => {
    for (const hits of [1, 2, 3, 4, 5, 6]) expect(hitsForHp(hpForHits(hits))).toBe(hits);
  });

  it('名札のうんこの印は、ルールの層のうんこの表の状態をちょうど1つずつ持つ', () => {
    // 呼び方はルールの層の表（POOP_EFFECTS の label）をそのまま使う。印の表に状態が欠けると、名札にその状態が出ない。
    expect(POOP_MARKS.map(([kind]) => kind).sort()).toEqual(POOP_EFFECTS.map((effect) => effect.kind).sort());
  });

  it('選べる動物は、能力の登録と同じ顔ぶれ', () => {
    const plan = planLocalMatch({ ...DEFAULT_SETUP, mode: 'solo', picks: ['rabbit', 'frog'] }, 1);
    const known = new Set(ANIMAL_LOOKS.map((look) => look.key));
    for (const animal of plan.config.animals) expect(known.has(animal)).toBe(true);
    // 試合を作れること（能力が登録されていない動物なら、ここで失敗する）。
    expect(() => new GameSession(plan.config)).not.toThrow();
    expect(plan.config.animals.map((_, id) => id as PlayerId)).toEqual([0, 1, 2, 3]);
  });
});
