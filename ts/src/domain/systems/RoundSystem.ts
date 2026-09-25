import type { SimEvent } from '../events/SimEvent.js';
import type { MatchConfig } from '../rules/MatchConfig.js';
import { addWin, winsOf, type MatchState } from '../state/MatchState.js';
import type { PlayerId } from '../state/PlayerState.js';
import type { WorldState } from '../state/WorldState.js';

/** ラウンドが終わった理由と結果。 */
export interface RoundOutcome {
  /** 勝者。引き分けなら null。 */
  readonly winner: PlayerId | null;
  readonly reason: 'lastStanding' | 'timeUp';
}

/**
 * ラウンドの終わりを見張る。
 *
 * 盤面には手を出さない。終わったかどうかを判定して返すだけで、
 * 次のラウンドを始めるのは呼び出し側（`GameSession`）の仕事にしてある。
 * 盤面の作り直しをここに入れると、「1 tick 進める」という約束の中で
 * 世界がまるごと入れ替わることになり、記録の再生が追えなくなる。
 */
export class RoundSystem {
  /**
   * ラウンドが終わったかを見る。
   *
   * @returns 終わっていれば結果、続いていれば null
   */
  check(world: WorldState, config: MatchConfig): RoundOutcome | null {
    const alive = world.players.filter((player) => player.life === 'alive');

    if (alive.length <= 1) {
      return { winner: alive[0]?.id ?? null, reason: 'lastStanding' };
    }
    if (world.now >= config.roundLimit) {
      // 時間切れは引き分け。体力が多いほうを勝ちにすると、
      // 開幕から隅で待つのがいちばん強い戦術になってしまう。
      return { winner: null, reason: 'timeUp' };
    }
    return null;
  }
}

/**
 * ラウンドの結果を試合へ反映する。
 *
 * @returns 起きたイベント
 */
export function applyOutcome(
  match: MatchState,
  config: MatchConfig,
  outcome: RoundOutcome,
): SimEvent[] {
  const events: SimEvent[] = [
    { type: 'roundEnded', round: match.round, winner: outcome.winner },
  ];
  if (outcome.winner !== null) {
    addWin(match, outcome.winner);
    if (winsOf(match, outcome.winner) >= config.winsToTake) {
      match.champion = outcome.winner;
      match.finished = true;
      events.push({ type: 'matchEnded', champion: match.champion });
    }
  }
  if (!match.finished) match.round += 1;
  return events;
}
