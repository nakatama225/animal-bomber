import type { SimEvent } from '../domain/events/SimEvent.js';
import type { WorldState } from '../domain/state/WorldState.js';
import type { Roster } from '../presentation/hud/roster.js';
import type { HudSource } from '../presentation/hud/scoreboard.js';
import type { GameSession } from './GameSession.js';

/**
 * 画面のループから見た「試合を進めるもの」。
 *
 * 1台で遊ぶときと通信対戦とで、画面のループを同じ形にするために置いている。
 * 違うのは「次の tick をいつ進めてよいか」と「止められるか」と、ラウンドの幕の消し方。
 *
 * - 1台：止めていなければ（ポーズ・ラウンドの幕・決まった試合）いつでも進めてよい。ラウンドの幕は原型どおり
 *   ボタンで送る（`startNextRound`）ので、決着のあとの待ちの間は進めない
 * - 通信対戦：全員の入力がそろうまで待つ。1人だけ止めることはできない。ラウンドの幕は決着のあとの待ち
 *   （`ROUND_INTERMISSION`）を進めて消す（全端末が同じ tick に次のラウンドへ進むため）
 */
export interface MatchRunner {
  /** いま描く盤面。まだ試合が始まっていなければ null。 */
  readonly world: WorldState | null;
  /** 横の板と幕に出す材料。まだ試合が始まっていなければ null。 */
  readonly hud: HudSource | null;
  /**
   * 試合の最中か（始まっていて、終わっておらず、止まってもおらず、ラウンドの幕の間でもない）。曲はこの間だけ鳴らす
   * （原型の `endGame` はラウンドが決まるたびに曲を止め、次のラウンドの頭で鳴らし直す。L4469・L4159）。
   */
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
   * 1台の試合を、わざと止めているか（ポーズ・ラウンドの幕・決まった試合）。止めている間は、押してすぐ離したキーを
   * 毎フレーム忘れる（`Shell`。忘れないと、ポーズ中に押した爆弾のキーで、再開した最初の tick に爆弾を置く）。
   *
   * 通信対戦はいつも false。入力を待って進めないのは止めているのではなく、押したキーは送るまで残す。
   */
  readonly stopped: boolean;
  /** 止める・再開する。止められない試合（通信対戦）と、ラウンドの最中でないときは何もしない。 */
  readonly togglePause: () => void;
  /**
   * ラウンドの幕を送り、次のラウンドを始める（1台の試合だけ。`GameSession.startNextRound`）。決着のあとの待ちの
   * 最中でなければ何もしない。通信対戦は待ちが尽きて進むので、何もしない。
   */
  readonly startNextRound: () => void;
  /** 1 tick 進める。`ready` のときだけ呼ぶ。 */
  readonly step: () => SimEvent[];
  /** 1枚描いたあとに呼ぶ。盤面の外に出す案内を書き換える。 */
  readonly afterDraw: () => void;
  /** 試合を抜ける。接続などの後始末をする。 */
  readonly close: () => void;
}

/**
 * 1台で遊ぶ試合。止めていなければ、いつでも次の tick を進めてよい。
 *
 * ラウンドの幕が出ている間（決着のあとの待ち）は進めない（原型の `loop` も `G.phase==='play'` の間だけ `update` を
 * 呼ぶ。L4256）。待ちを tick で数えて消すのは通信対戦だけで、1台はボタンで送る（`startNextRound`）。
 */
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
    return !this.session.match.finished && !this.#paused && !this.session.betweenRounds;
  }

  get ready(): boolean {
    return !this.#paused && !this.session.betweenRounds;
  }

  get paused(): boolean {
    return this.#paused;
  }

  get stopped(): boolean {
    return this.#paused || this.session.betweenRounds || this.session.match.finished;
  }

  togglePause(): void {
    // 止められるのはラウンドの最中だけ（原型の `togglePause` の `G.phase!=='play'`。L4215）。決まった試合は止めても
    // 意味がなく、決着のあとの待ちの間は幕が出ている（原型の幕の間も止められない）。
    if (this.session.match.finished || this.session.betweenRounds) return;
    this.#paused = !this.#paused;
  }

  startNextRound(): void {
    // 決まった試合は待ちが無いので、ここを通らない（次の試合は `Shell.restart` が作り直す）。
    if (this.session.betweenRounds) this.session.startNextRound();
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
