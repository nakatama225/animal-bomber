import type { PlayerId } from './PlayerState.js';

/**
 * ラウンドをまたいで残る状態。
 *
 * `WorldState`（盤面とプレイヤー）とは分けてある。ラウンドが変われば
 * 盤面は作り直されるが、勝利数は引き継がれるため。
 */
export interface MatchState {
  /** いま何ラウンド目か。1 から数える。 */
  round: number;
  /** プレイヤーごとの勝利数。 */
  readonly wins: Map<PlayerId, number>;
  /** 試合が決まっていれば、その勝者。引き分けで終わった場合は null。 */
  champion: PlayerId | null;
  /** 試合が終わったか。 */
  finished: boolean;
}

/** 試合を始める。 */
export function createMatch(): MatchState {
  return { round: 1, wins: new Map(), champion: null, finished: false };
}

/** そのプレイヤーの勝利数。 */
export function winsOf(match: MatchState, id: PlayerId): number {
  return match.wins.get(id) ?? 0;
}

/** 勝利数を1つ足す。 */
export function addWin(match: MatchState, id: PlayerId): void {
  match.wins.set(id, winsOf(match, id) + 1);
}
