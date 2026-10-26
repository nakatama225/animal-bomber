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
  /**
   * いまの盤面が、この試合の流れで何試合目か。1台の試合はいつも 1（次の試合は作り直す）。
   *
   * 通信対戦は、接続を保ったまま次の試合を始めるたびに増える。画面の側は、これが変わったら
   * 試合ごとの部品（描く部品・幕・秒読み）を作り直す。
   */
  readonly generation: number;
  /** 止めているか。 */
  readonly paused: boolean;
  /**
   * 1台の試合を、わざと止めているか（ポーズ・決まった試合）。止めている間は、押してすぐ離したキーを
   * 毎フレーム忘れる（`Shell`。忘れないと、ポーズ中に押した爆弾のキーで、再開した最初の tick に爆弾を置く）。
   *
   * 通信対戦はいつも false。入力を待って進めないのは止めているのではなく、押したキーは送るまで残す。
   */
  readonly stopped: boolean;
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
  readonly generation = 1;
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

  get stopped(): boolean {
    return this.#paused || this.session.match.finished;
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
