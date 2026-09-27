import type { SimEvent } from '../domain/events/SimEvent.js';
import type { WorldState } from '../domain/state/WorldState.js';
import type { GameSession } from './GameSession.js';

/**
 * 画面のループから見た「試合を進めるもの」。
 *
 * 1台で遊ぶときと通信対戦とで、画面のループ（`main.ts`）を同じ形にするために置いている。
 * 違うのは「次の tick をいつ進めてよいか」だけで、1台なら常に進めてよく、
 * 通信対戦では全員の入力がそろうまで待つ。
 */
export interface MatchRunner {
  /** いま描く盤面。まだ試合が始まっていなければ null。 */
  readonly world: WorldState | null;
  /** 試合の最中か（始まっていて、終わっておらず、止まってもいない）。曲はこの間だけ鳴らす。 */
  readonly inProgress: boolean;
  /** 次の tick を進めてよいか。 */
  readonly ready: boolean;
  /** 1 tick 進める。`ready` のときだけ呼ぶ。 */
  step(): SimEvent[];
  /** 1枚描いたあとに呼ぶ。盤面の外に出す案内を書き換える。 */
  afterDraw(): void;
}

/** 1台で遊ぶ試合。いつでも次の tick を進めてよい。 */
export class LocalMatch implements MatchRunner {
  readonly ready = true;

  constructor(private readonly session: GameSession) {}

  get world(): WorldState {
    return this.session.world;
  }

  get inProgress(): boolean {
    return !this.session.match.finished;
  }

  step(): SimEvent[] {
    return this.session.tick();
  }

  afterDraw(): void {
    // 盤面の外に出す案内は無い。
  }
}
