import type { SimEvent } from '../events/SimEvent.js';
import type { MatchConfig } from '../rules/MatchConfig.js';
import { addWin, winsOf, type MatchState } from '../state/MatchState.js';
import type { PlayerId } from '../state/PlayerState.js';
import { isAlive } from '../state/PlayerState.js';
import type { WorldState } from '../state/WorldState.js';

/** ラウンドが終わった理由と結果。 */
export interface RoundOutcome {
  /** 勝者。引き分けなら null。 */
  readonly winner: PlayerId | null;
  /**
   * - `lastStanding` … 盤面に1人だけ残った
   * - `allDown` … 残っていた全員が同じ tick に倒れた
   * - `timeUp` … 時間切れで2人以上残った
   */
  readonly reason: 'lastStanding' | 'allDown' | 'timeUp';
}

/** ラウンドの判定。続けるか、延長戦に入るか、終わるか。 */
export type RoundVerdict =
  | { readonly type: 'continue' }
  | {
      readonly type: 'suddenDeath';
      readonly reason: 'allDown' | 'timeUp';
      /** 延長戦に加わるプレイヤー。 */
      readonly players: readonly PlayerId[];
    }
  | { readonly type: 'over'; readonly outcome: RoundOutcome };

const CONTINUE: RoundVerdict = { type: 'continue' };

/**
 * ラウンドの終わりを見張る。
 *
 * 盤面には手を出さない。判定を返すだけで、延長戦の準備や次のラウンドを
 * 始めるのは呼び出し側（`GameSession`）の仕事にしてある。
 * 盤面の作り直しをここに入れると、「1 tick 進める」という約束の中で
 * 世界がまるごと入れ替わることになり、記録の再生が追えなくなる。
 *
 * ## 判定の順
 *
 * | 盤面にいる人数 | 判定 |
 * |---|---|
 * | 0 人 | 同じ tick に2人以上倒れていれば延長戦、でなければ引き分け |
 * | 1 人 | その人の勝ち。時間が残っていても待たない |
 * | 2 人以上 | 時間切れなら延長戦、延長戦のあとの時間切れなら引き分け |
 *
 * 延長戦は1ラウンドに1回だけ。設定で切ってあれば、延長戦の代わりに引き分けにする。
 */
export class RoundSystem {
  /**
   * @param tickEvents この tick に起きたイベント。同じ tick に倒れた人を知るのに使う
   */
  judge(world: WorldState, config: MatchConfig, tickEvents: readonly SimEvent[]): RoundVerdict {
    const alive = world.players.filter(isAlive);
    const canExtend = config.suddenDeath && !world.suddenDeath;

    if (alive.length === 0) {
      // 残っていた全員が同じ tick に倒れた。決着のつけようがない。
      const downed = downedThisTick(world, tickEvents);
      if (canExtend && downed.length >= 2) {
        return { type: 'suddenDeath', reason: 'allDown', players: downed };
      }
      return { type: 'over', outcome: { winner: null, reason: 'allDown' } };
    }
    if (alive.length === 1) {
      return { type: 'over', outcome: { winner: alive[0]!.id, reason: 'lastStanding' } };
    }
    if (world.now >= world.endsAt) {
      if (canExtend) {
        return { type: 'suddenDeath', reason: 'timeUp', players: alive.map((player) => player.id) };
      }
      // 時間切れは引き分け。体力が多いほうを勝ちにすると、
      // 開幕から隅で待つのがいちばん強い戦術になってしまう。
      return { type: 'over', outcome: { winner: null, reason: 'timeUp' } };
    }
    return CONTINUE;
  }
}

/** この tick に倒れたプレイヤーを、プレイヤー番号の順に並べる。 */
function downedThisTick(world: WorldState, tickEvents: readonly SimEvent[]): PlayerId[] {
  const downed = new Set<PlayerId>();
  for (const event of tickEvents) if (event.type === 'playerDown') downed.add(event.target);
  return world.players.filter((player) => downed.has(player.id)).map((player) => player.id);
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
