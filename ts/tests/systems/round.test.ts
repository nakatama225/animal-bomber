import { describe, expect, it } from 'vitest';

import { GameSession } from '../../src/app/GameSession.js';
import { IdleIntentSource } from '../../src/domain/intent/IntentSource.js';
import { defaultMatchConfig, seedForRound } from '../../src/domain/rules/MatchConfig.js';
import { winsOf } from '../../src/domain/state/MatchState.js';
import { hashWorld } from '../../src/domain/state/WorldState.js';
import { secondsToTicks } from '../../src/domain/core/Tick.js';

function session(overrides: Partial<ReturnType<typeof defaultMatchConfig>> = {}): GameSession {
  const config = { ...defaultMatchConfig(777, ['rabbit', 'elephant']), ...overrides };
  const game = new GameSession(config);
  for (const player of game.world.players) game.attach(new IdleIntentSource(player.id));
  return game;
}

describe('ラウンドの進行', () => {
  it('最後の1人になるとラウンドが終わる', () => {
    const game = session();
    game.world.players[1]!.life = 'dead';
    const events = game.tick();
    expect(events.some((e) => e.type === 'roundEnded')).toBe(true);
    expect(winsOf(game.match, 0)).toBe(1);
  });

  it('時間切れは引き分けにする', () => {
    // 体力の多いほうを勝ちにすると、開幕から隅で待つのが
    // いちばん強い戦術になってしまう。
    const game = session({ roundLimit: secondsToTicks(0.05) });
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
      game.world.players[1]!.life = 'dead';
      game.tick();
    }
    expect(game.match.finished).toBe(true);
    expect(game.match.champion).toBe(0);
  });

  it('試合が終わったあとは進まない', () => {
    const game = session({ winsToTake: 1 });
    game.world.players[1]!.life = 'dead';
    game.tick();
    expect(game.match.finished).toBe(true);
    expect(game.tick()).toHaveLength(0);
  });

  it('次のラウンドでは盤面が作り直される', () => {
    const game = session({ winsToTake: 3 });
    const before = hashWorld(game.world);
    game.world.players[1]!.life = 'dead';
    game.tick();
    expect(game.match.round).toBe(2);
    expect(hashWorld(game.world)).not.toBe(before);
    expect(game.world.players[1]!.life).toBe('alive');
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
      game.world.players[1]!.life = 'dead';
      game.tick();
    }
    expect(hashWorld(first.world)).toBe(hashWorld(second.world));
  });
});
