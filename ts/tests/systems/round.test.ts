import { describe, expect, it } from 'vitest';

import { GameSession, ROUND_INTERMISSION } from '../../src/app/GameSession.js';
import { IdleIntentSource } from '../../src/domain/intent/IntentSource.js';
import { defaultMatchConfig, seedForRound } from '../../src/domain/rules/MatchConfig.js';
import { OUT } from '../../src/domain/state/Life.js';
import { winsOf } from '../../src/domain/state/MatchState.js';
import { isAlive } from '../../src/domain/state/PlayerState.js';
import { hashWorld } from '../../src/domain/state/WorldState.js';
import { secondsToTicks } from '../../src/domain/core/Tick.js';

/** 決着のあとの待ちを飛ばして、次のラウンドの盤面まで進める。 */
function skipIntermission(game: GameSession): void {
  while (game.betweenRounds) game.tick();
}

function session(overrides: Partial<ReturnType<typeof defaultMatchConfig>> = {}): GameSession {
  const config = { ...defaultMatchConfig(777, ['rabbit', 'elephant']), ...overrides };
  const game = new GameSession(config);
  for (const player of game.world.players) game.attach(new IdleIntentSource(player.id));
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

describe('プレイヤーごとの体力', () => {
  // うさぎには体力の上乗せが無く、ぞうには爆風1回ぶん（2）ある。
  const ELEPHANT_BONUS = 2;

  it('設定した体力で始まり、動物ごとの上乗せはその上に足す', () => {
    const game = session({ startingHp: [2, 10] });
    expect(game.world.players.map((p) => p.hp)).toEqual([2, 10 + ELEPHANT_BONUS]);
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
