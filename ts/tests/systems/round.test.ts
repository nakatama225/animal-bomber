import { describe, expect, it } from 'vitest';

import { GameSession, ROUND_INTERMISSION } from '../../src/app/GameSession.js';
import { IdleInputSource } from '../../src/domain/input/InputSource.js';
import { defaultMatchConfig, seedForRound } from '../../src/domain/rules/MatchConfig.js';
import { OUT } from '../../src/domain/state/Life.js';
import { winsOf } from '../../src/domain/state/MatchState.js';
import { isAlive } from '../../src/domain/state/PlayerState.js';
import { createWorld, hashWorld, type WorldState } from '../../src/domain/state/WorldState.js';
import { centerOf } from '../../src/domain/core/Coord.js';
import { secondsToTicks } from '../../src/domain/core/Tick.js';
import { SPAWN_CELLS } from '../../src/domain/rules/tuning.js';
import type { SimEvent } from '../../src/domain/events/SimEvent.js';
import { IDLE_INPUT, type PlayerInput } from '../../src/domain/input/PlayerInput.js';
import { Simulation } from '../../src/domain/systems/Simulation.js';
import { onlyFor, press } from '../helpers.js';

/** 決着のあとの待ちを飛ばして、次のラウンドの盤面まで進める。 */
function skipIntermission(game: GameSession): void {
  while (game.betweenRounds) game.tick();
}

function session(overrides: Partial<ReturnType<typeof defaultMatchConfig>> = {}): GameSession {
  const config = { ...defaultMatchConfig(777, ['rabbit', 'elephant']), ...overrides };
  const game = new GameSession(config);
  for (const player of game.world.players) game.attach(new IdleInputSource(player.id));
  return game;
}

describe('ラウンドの進行', () => {
  it('最後の1人になるとラウンドが終わる', () => {
    const game = session();
    game.world.players[1]!.life = OUT;
    const events = game.tick();
    expect(events.some((e) => e.type === 'roundEnded')).toBe(true);
    expect(winsOf(game.match, 0)).toBe(1);
  });

  it('延長戦を切ってあれば、時間切れは引き分けにする', () => {
    // 体力の多いほうを勝ちにすると、開幕から隅で待つのが
    // いちばん強い戦術になってしまう。
    const game = session({ roundLimit: secondsToTicks(0.05), suddenDeath: false });
    let ended: { winner: number | null } | null = null;
    for (let i = 0; i < 10 && ended === null; i += 1) {
      for (const event of game.tick()) {
        if (event.type === 'roundEnded') ended = { winner: event.winner };
      }
    }
    expect(ended).not.toBeNull();
    expect(ended?.winner).toBeNull();
    expect(winsOf(game.match, 0)).toBe(0);
  });

  it('勝利数が揃うと試合が終わる', () => {
    const game = session({ winsToTake: 2 });
    for (let round = 0; round < 2; round += 1) {
      game.world.players[1]!.life = OUT;
      game.tick();
      skipIntermission(game);
    }
    expect(game.match.finished).toBe(true);
    expect(game.match.champion).toBe(0);
  });

  it('試合が終わったあとは進まない', () => {
    const game = session({ winsToTake: 1 });
    game.world.players[1]!.life = OUT;
    game.tick();
    expect(game.match.finished).toBe(true);
    expect(game.tick()).toHaveLength(0);
  });

  it('次のラウンドでは盤面が作り直される', () => {
    const game = session({ winsToTake: 3 });
    const before = hashWorld(game.world);
    game.world.players[1]!.life = OUT;
    game.tick();
    skipIntermission(game);
    expect(game.match.round).toBe(2);
    expect(hashWorld(game.world)).not.toBe(before);
    expect(isAlive(game.world.players[1]!)).toBe(true);
  });

  it('決着のあと、しばらくは前の盤面のまま止まる', () => {
    // 決まった tick のうちに盤面を作り直すと、決着の場面が1度も描かれない。
    const game = session({ winsToTake: 3 });
    game.world.players[1]!.life = OUT;
    game.tick();
    const decided = game.world;
    const frozen = hashWorld(decided);
    for (let i = 0; i < ROUND_INTERMISSION - 1; i += 1) {
      expect(game.tick()).toHaveLength(0);
      expect(game.world).toBe(decided);
    }
    expect(hashWorld(decided)).toBe(frozen);
    game.tick();
    expect(game.world).not.toBe(decided);
    expect(game.betweenRounds).toBe(false);
  });

  it('試合通算の tick は、決着のあとの待ちの間も進む', () => {
    // 通信対戦の時刻に使う。world.now は待ちの間は止まり、ラウンドごとに 0 へ戻る。
    const game = session({ winsToTake: 3 });
    game.world.players[1]!.life = OUT;
    game.tick();
    const nowAtDecision = game.world.now;
    skipIntermission(game);

    expect(game.elapsed).toBe(1 + ROUND_INTERMISSION);
    expect(game.world.now).toBeLessThan(nowAtDecision + ROUND_INTERMISSION);
  });

  it('試合が終わったら、試合通算の tick も進まない', () => {
    const game = session({ winsToTake: 1 });
    game.world.players[1]!.life = OUT;
    game.tick();
    expect(game.match.finished).toBe(true);

    game.tick();
    expect(game.elapsed).toBe(1);
  });

  it('ラウンドごとに違う盤面になる', () => {
    const config = defaultMatchConfig(777, ['rabbit', 'elephant']);
    expect(seedForRound(config, 1)).not.toBe(seedForRound(config, 2));
  });

  it('同じ設定からは同じ試合になる', () => {
    // 種1つで試合全体が再現できる。「3ラウンド目だけ見たい」も
    // 設定だけで足りる。
    const first = session({ winsToTake: 3 });
    const second = session({ winsToTake: 3 });
    for (const game of [first, second]) {
      game.world.players[1]!.life = OUT;
      game.tick();
      skipIntermission(game);
    }
    expect(hashWorld(first.world)).toBe(hashWorld(second.world));
  });
});

describe('次のラウンドへ送る（1台の試合で、ラウンドの幕をボタンで送る。原型の advanceBanner）', () => {
  /** 負けるプレイヤーを倒し、ラウンドを決める tick を1つ進める。 */
  function finishRound(game: GameSession): void {
    game.world.players[1]!.life = OUT;
    game.tick();
  }

  /** 送ったときの例外の文。送れてしまったら空の文字列（あとの盤面も同じテストで見るため、toThrow を使わない）。 */
  function refusal(game: GameSession): string {
    try {
      game.startNextRound();
    } catch (error) {
      return error instanceof Error ? error.message : String(error);
    }
    return '';
  }

  it('待ちを切り上げて、待ち終えたときと同じ次の盤面を作る', () => {
    const sent = session({ winsToTake: 3, startingHp: [2, 10] });
    const waited = session({ winsToTake: 3, startingHp: [2, 10] });
    for (const game of [sent, waited]) finishRound(game);
    const decided = sent.world;
    sent.tick();
    sent.startNextRound();
    skipIntermission(waited);
    expect(sent.betweenRounds).toBe(false);
    expect(sent.world).not.toBe(decided);
    expect(sent.match.round).toBe(2);
    expect(sent.world.now).toBe(0);
    expect(sent.world.players.map((player) => player.hp)).toEqual([2, 12]);
    expect(sent.world.players.every((player) => isAlive(player))).toBe(true);
    expect(hashWorld(sent.world)).toBe(hashWorld(waited.world));
  });

  it('試合通算の tick は進めず、次の tick は続きの番号で進める（切り上げた待ちの tick は進めていない）', () => {
    const asked: number[] = [];
    const game = new GameSession({ ...defaultMatchConfig(777, ['rabbit', 'elephant']), winsToTake: 3 });
    for (const player of game.world.players) {
      game.attach({
        playerId: player.id,
        next: () => {
          asked.push(game.elapsed);
          return IDLE_INPUT;
        },
      });
    }
    finishRound(game);
    game.tick();
    game.startNextRound();
    expect(game.elapsed).toBe(2);
    asked.length = 0;
    game.tick();
    expect(asked).toEqual([2, 2]);
    expect(game.elapsed).toBe(3);
  });

  it('送ったあとは、待ちの長さが過ぎても盤面を作り直さない', () => {
    const game = session({ winsToTake: 3 });
    finishRound(game);
    game.startNextRound();
    const started = game.world;
    for (let i = 0; i < ROUND_INTERMISSION + 1; i += 1) game.tick();
    expect(game.world).toBe(started);
    expect(game.match.round).toBe(2);
  });

  it('待ちの最中でなければ例外にし、盤面を替えない（ラウンドの最中に送ると、決着のつかないまま盤面が替わる）', () => {
    const playing = session({ winsToTake: 3 });
    const before = playing.world;
    expect(refusal(playing)).toContain('待ちの最中でない');
    expect(playing.world).toBe(before);
    expect(playing.match.round).toBe(1);

    const twice = session({ winsToTake: 3 });
    finishRound(twice);
    twice.startNextRound();
    const started = twice.world;
    expect(refusal(twice)).toContain('待ちの最中でない');
    expect(twice.world).toBe(started);
  });

  it('試合が決まったあとは例外にし、盤面を替えない（「もういっかい」は新しい試合）', () => {
    const game = session({ winsToTake: 1 });
    finishRound(game);
    expect(game.match.finished).toBe(true);
    const decided = game.world;
    expect(refusal(game)).toContain('待ちの最中でない');
    expect(game.world).toBe(decided);
  });

  it('押したまま送っても、次のラウンドの開始位置に爆弾を置かない（盤面を作るときの「押していた扱い」）', () => {
    const holdBomb = press({ bomb: true });
    const game = new GameSession({ ...defaultMatchConfig(3, ['rabbit', 'frog']), winsToTake: 3 });
    for (const player of game.world.players) game.attach({ playerId: player.id, next: () => holdBomb });
    game.world.players[1]!.life = OUT;
    game.tick();
    game.startNextRound();
    expect(game.match.round).toBe(2);
    expect(game.tick().filter((event) => event.type === 'bombPlaced')).toHaveLength(0);
    expect(game.world.bombs).toHaveLength(0);
  });
});

describe('開始位置', () => {
  const positionsOf = (world: WorldState) => world.players.map((p) => p.position);
  const facingsOf = (world: WorldState) => world.players.map((p) => p.facing);

  it('2人の試合は、左上と右下の対角から始まり、盤面の内側を向く', () => {
    const world = createWorld({ seed: 5, animals: ['rabbit', 'frog'] });
    expect(positionsOf(world)).toEqual([centerOf(SPAWN_CELLS[0]), centerOf(SPAWN_CELLS[3])]);
    expect(facingsOf(world)).toEqual(['down', 'up']);
  });

  it('3人と4人の試合は、プレイヤー番号の順に4隅から始まる', () => {
    const four = createWorld({ seed: 5, animals: ['rabbit', 'frog', 'fox', 'mole'] });
    expect(positionsOf(four)).toEqual(SPAWN_CELLS.map(centerOf));
    expect(facingsOf(four)).toEqual(['down', 'down', 'up', 'up']);
    const three = createWorld({ seed: 5, animals: ['rabbit', 'frog', 'fox'] });
    expect(positionsOf(three)).toEqual(SPAWN_CELLS.slice(0, 3).map(centerOf));
  });

  it('開始位置の並びを渡すと、プレイヤーごとにその隅から始まる（2人＋CPU2体で 2P を右下へ）', () => {
    const world = createWorld({ seed: 5, animals: ['rabbit', 'frog', 'fox', 'mole'], spawnOrder: [0, 3, 1, 2] });
    expect(positionsOf(world)).toEqual([0, 3, 1, 2].map((corner) => centerOf(SPAWN_CELLS[corner]!)));
    expect(facingsOf(world)).toEqual(['down', 'up', 'down', 'up']);
  });

  it('開始位置の並びが人数と合わない・隅の番号でない・重なるときは、盤面を作らない', () => {
    // 黙って番号の順に戻すと、1台だけ並びを取り違えても試合が始まり、気づけない。
    const animals = ['rabbit', 'frog', 'fox', 'mole'];
    for (const spawnOrder of [[0, 3, 1], [0, 3, 1, 4], [0, 3, 1, 1], [0, 3, 1, 1.5], [0, 3, 1, -1]]) {
      expect(() => createWorld({ seed: 5, animals, spawnOrder }), JSON.stringify(spawnOrder)).toThrow('開始位置の並び');
    }
    // 人数より長く、違う隅がちょうど人数ぶんある並び。長さを比べる条件でしか止まらず、止めないと
    // 余りを黙って捨てて試合が始まる。上の [0, 3, 1] は、隅が重ならないかの条件でも止まる。
    const tooLong = [
      { animals: ['rabbit', 'frog'], spawnOrder: [0, 3, 0] },
      { animals, spawnOrder: [0, 3, 1, 2, 0] },
    ];
    for (const { animals: players, spawnOrder } of tooLong) {
      expect(() => createWorld({ seed: 5, animals: players, spawnOrder }), JSON.stringify(spawnOrder)).toThrow(
        '開始位置の並び',
      );
    }
  });

  it('次のラウンドも、渡した並びの隅から始まる', () => {
    const animals = ['rabbit', 'frog', 'fox', 'mole'];
    const game = new GameSession({ ...defaultMatchConfig(777, animals), spawnOrder: [0, 3, 1, 2] });
    for (const player of game.world.players) game.attach(new IdleInputSource(player.id));
    for (const id of [1, 2, 3]) game.world.players[id]!.life = OUT;
    game.tick();
    skipIntermission(game);
    expect(game.match.round).toBe(2);
    expect(positionsOf(game.world)).toEqual([0, 3, 1, 2].map((corner) => centerOf(SPAWN_CELLS[corner]!)));
  });

  it('盤面は人数によらず同じ（4隅とも空けて作る）', () => {
    // 人数で盤面の作り方を変えると、同じ種でも2人と4人で別の盤面になり、
    // 右下の隅が空いているかも人数しだいになる。
    const two = createWorld({ seed: 5, animals: ['rabbit', 'frog'] });
    const four = createWorld({ seed: 5, animals: ['rabbit', 'frog', 'fox', 'mole'] });
    expect(two.board.encode()).toBe(four.board.encode());
  });

  it('次のラウンドも、2人の試合は対角から始まる', () => {
    const game = session();
    game.world.players[1]!.life = OUT;
    game.tick();
    skipIntermission(game);
    expect(game.match.round).toBe(2);
    expect(positionsOf(game.world)).toEqual([centerOf(SPAWN_CELLS[0]), centerOf(SPAWN_CELLS[3])]);
  });
});

describe('ラウンドの始まりに押していたボタン', () => {
  const holdBomb = press({ bomb: true });

  it('爆弾のボタンを押したまま始まっても置かず、離して押し直すと置く', () => {
    const world = createWorld({ seed: 5, animals: ['rabbit', 'frog'] });
    const sim = new Simulation();
    const placed = (playerInput: PlayerInput): number =>
      sim.step(world, onlyFor(world, 0, playerInput)).filter((e) => e.type === 'bombPlaced').length;
    expect(placed(holdBomb)).toBe(0);
    expect(placed(holdBomb)).toBe(0);
    expect(placed(IDLE_INPUT)).toBe(0);
    expect(placed(holdBomb)).toBe(1);
  });

  it('押したまま次のラウンドに入っても、開始位置に爆弾を置かない', () => {
    // 決着のあとの待ちの間も押し続けていた場合。原型でも、決着の幕を送った押下が
    // 次のラウンドの最初に届いて、開始位置に爆弾を置いた。
    const game = new GameSession(defaultMatchConfig(3, ['rabbit', 'frog']));
    for (const player of game.world.players) game.attach({ playerId: player.id, next: () => holdBomb });
    const bombsOf = (events: readonly SimEvent[]) => events.filter((e) => e.type === 'bombPlaced').length;
    expect(bombsOf(game.tick())).toBe(0);
    game.world.players[1]!.life = OUT;
    game.tick();
    skipIntermission(game);
    // 前提：2ラウンド目の最初の tick にいる。
    expect(game.match.round).toBe(2);
    expect(game.world.now).toBe(0);
    expect(bombsOf(game.tick())).toBe(0);
    expect(game.world.bombs).toHaveLength(0);
  });
});

describe('プレイヤーごとの体力', () => {
  // うさぎには体力の上乗せが無く、ぞうには爆風1回ぶん（2）ある。
  const ELEPHANT_BONUS = 2;

  it('設定した体力で始まり、動物ごとの上乗せはその上に足す', () => {
    const game = session({ startingHp: [2, 10] });
    expect(game.world.players.map((p) => p.hp)).toEqual([2, 10 + ELEPHANT_BONUS]);
  });

  it('体力の既定は爆風1回ぶん（原型の既定 hpP1・hpP2・hpCPU = 1）。ぞうは上乗せで2回ぶん', () => {
    const game = session();
    expect(game.world.players.map((p) => p.hp)).toEqual([2, 2 + ELEPHANT_BONUS]);
    expect(createWorld({ seed: 1, animals: ['rabbit'] }).players[0]!.hp).toBe(2);
  });

  it('次のラウンドも、設定した体力で始まる', () => {
    // 1ラウンド目だけ正しいと、2ラウンド目から全員が既定の体力に戻る。
    // 原型では、体力を1人ずつ変えられるようにしたときに、この形の誤りを避けた。
    const game = session({ startingHp: [2, 10] });
    game.world.players[1]!.life = OUT;
    game.tick();
    skipIntermission(game);
    expect(game.match.round).toBe(2);
    expect(game.world.players.map((p) => p.hp)).toEqual([2, 10 + ELEPHANT_BONUS]);
  });

  it('体力の数が動物の数と合わなければ、試合を作らない', () => {
    // 足りない人を既定値で埋めると、設定の画面の並びがずれたことに気づけない。
    expect(() => session({ startingHp: [6] })).toThrow('初期体力の数');
  });
});
