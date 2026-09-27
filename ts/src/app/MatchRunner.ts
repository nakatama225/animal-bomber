import type { SimEvent } from '../domain/events/SimEvent.js';
import type { WorldState } from '../domain/state/WorldState.js';
import type { Roster } from '../presentation/hud/roster.js';
import type { HudSource } from '../presentation/hud/scoreboard.js';
import type { GameSession } from './GameSession.js';

/**
 * 画面のループから見た「試合を進めるもの」。
 *
 * 1台で遊ぶときと通信対戦とで、画面のループを同じ形にするために置いている。
 * 違うのは「次の tick をいつ進めてよいか」と「止められるか」で、1台なら常に進めてよく
 * 止めることもでき、通信対戦では全員の入力がそろうまで待ち、1人だけ止めることはできない。
 */
export interface MatchRunner {
  /** いま描く盤面。まだ試合が始まっていなければ null。 */
  readonly world: WorldState | null;
  /** 横の板と幕に出す材料。まだ試合が始まっていなければ null。 */
  readonly hud: HudSource | null;
  /** 試合の最中か（始まっていて、終わっておらず、止まってもいない）。曲はこの間だけ鳴らす。 */
  readonly inProgress: boolean;
  /** 次の tick を進めてよいか。 */
  readonly ready: boolean;
  /** 止めているか。 */
  readonly paused: boolean;
  /** 止める・再開する。止められない試合（通信対戦）では何もしない。 */
  readonly togglePause: () => void;
  /** 1 tick 進める。`ready` のときだけ呼ぶ。 */
  readonly step: () => SimEvent[];
  /** 1枚描いたあとに呼ぶ。盤面の外に出す案内を書き換える。 */
  readonly afterDraw: () => void;
  /** 試合を抜ける。接続などの後始末をする。 */
  readonly close: () => void;
}

/** 1台で遊ぶ試合。止めていなければ、いつでも次の tick を進めてよい。 */
export class LocalMatch implements MatchRunner {
  #paused = false;

  constructor(
    private readonly session: GameSession,
    private readonly roster: Roster,
  ) {}

  get world(): WorldState {
    return this.session.world;
  }

  get hud(): HudSource {
    return {
      world: this.session.world,
      match: this.session.match,
      config: this.session.config,
      roster: this.roster,
      betweenRounds: this.session.betweenRounds,
    };
  }

  get inProgress(): boolean {
    return !this.session.match.finished && !this.#paused;
  }

  get ready(): boolean {
    return !this.#paused;
  }

  get paused(): boolean {
    return this.#paused;
  }

  togglePause(): void {
    // 決まった試合は止めても意味がない（進めても何も起きない）。
    if (this.session.match.finished) return;
    this.#paused = !this.#paused;
  }

  step(): SimEvent[] {
    return this.session.tick();
  }

  afterDraw(): void {
    // 盤面の外に出す案内は無い。
  }

  close(): void {
    // 後始末するものは無い。
  }
}
