import { lookOf } from '../../content/animals.js';
import type { SimEvent } from '../../domain/events/SimEvent.js';
import { winsOf } from '../../domain/state/MatchState.js';
import { isAlive, type PlayerId } from '../../domain/state/PlayerState.js';
import type { WorldState } from '../../domain/state/WorldState.js';
import { ALL_DOWN, TIME_UP } from '../notices.js';
import { isCpu, labelOf } from './roster.js';
import type { HudSource } from './scoreboard.js';

/** ラウンドの幕のボタン（原型 L4498）。 */
export const NEXT_ROUND_BUTTON = 'つぎのラウンド ▶';

/** 優勝の幕のボタン（原型 L4489）。 */
export const AGAIN_BUTTON = 'もういっかい';

/** どちらの幕にも出す2つ目のボタン（原型 L549）。行き先はタイトル（原型の `backToSetup`）。 */
export const SETUP_BUTTON = '⚙ 設定をやりなおす';

/** 延長戦で決まったラウンドの幕に添える行（原型 L4497）。 */
const SUDDEN_NOTE = '⚡サドンデス決着';

/** 勝ち数の行の区切りと、題の「ラウンドN」のあとの区切り（全角の空白。原型 L4482・L4494・L4502）。 */
const SEPARATOR = '\u3000';

/** 時間切れのひきわけで、残ったプレイヤーの前に置く文（原型 L4504）。 */
const LEFT_LABEL = `${SEPARATOR}のこり: `;

/** 幕の中身（原型の `#bE`・`#bT`・`#bS`・`#bAgain`）。 */
export interface BannerView {
  /** 大きく出す絵文字。 */
  readonly emoji: string;
  readonly title: string;
  /** 題の下の1行目（勝ち数の残り・達成・ひきわけのわけ）。 */
  readonly summary: string;
  /** 勝ち数の行（原型は1行目より大きい字で出す）。 */
  readonly board: string;
  /** 勝ち数の行の下に添える行（延長戦で決まったラウンド）。無ければ null。 */
  readonly note: string | null;
  /** 1つ目のボタンの文（「つぎのラウンド ▶」か「もういっかい」）。 */
  readonly button: string;
  /** 試合が決まった幕か。決まったら消えない。 */
  readonly final: boolean;
}

/**
 * ラウンドが決まったときに出す幕（窓の全体を覆う。写すのは `platform/ui/BannerOverlay.ts`）。
 *
 * 文の形は原型の3つ（優勝・ラウンドの勝ち・ひきわけ。`endGame` L4467-4511）を Python 版の
 * `hud/banner.py` と同じく写した。
 *
 * - 優勝：題は「うさぎ（1P） 優勝！」（CPU は「（CPU）」）。延長戦で決まっても、そう添えない
 * - ラウンドの勝ち：題は動物の名前だけ（「ラウンド1」と「うさぎの かち」を全角の空白でつなぐ）。同じ動物を2人が選ぶと、題からは
 *   どちらの勝ちか分からない（原型 L4494 のまま）。延長戦で決まったら「⚡サドンデス決着」を添える
 * - ひきわけ：わけ（「同時にやられた」「時間切れ」）と、時間切れなら残ったプレイヤー
 *
 * 勝ち数の行は、全員の「絵文字と勝ち数」を全角の空白でつなぐ（原型 L4482）。
 *
 * ## 次の盤面に替わったら消える
 *
 * 試合が決まっていなければ、次のラウンドの盤面に替わったら消す。試合が決まった幕は、別の盤面を
 * 渡されても消さない（「もういっかい」を押すまで結果を見せる）。
 *
 * ## イベントから作る
 *
 * 誰が勝ったかは、決まった tick のイベント（`roundEnded`）にしか載っていない。
 * 試合の状態には勝ち数しか残らないので、あとから読んでも「このラウンドの勝者」は分からない。
 */
export class RoundBanner {
  #view: BannerView | null = null;
  /** 幕を出したときの盤面。これと違う盤面になったら、次のラウンドが始まっている。 */
  #shownOn: Readonly<WorldState> | null = null;

  /**
   * tick を進めたあとに呼ぶ。ラウンドと試合が同じ tick に決まったら、試合が決まった幕を出す（原型の
   * `endGame` も、優勝者がいれば優勝の幕を出す）。
   *
   * @param source 進める前に控えた材料。盤面は決着の tick のうちは差し替わらないので、決着の tick の盤面が、
   *   幕を出す盤面になる
   */
  onEvents(events: readonly SimEvent[], source: HudSource): void {
    let ended: Extract<SimEvent, { type: 'roundEnded' }> | null = null;
    let champion: PlayerId | null = null;
    for (const event of events) {
      if (event.type === 'roundEnded') ended = event;
      if (event.type === 'matchEnded') champion = event.champion;
    }
    if (ended === null) return;
    this.#view = describeBanner(source, ended.round, ended.winner, champion);
    this.#shownOn = source.world;
  }

  /** いま出す幕。次のラウンドの盤面に替わっていれば、消して null を返す。 */
  current(world: Readonly<WorldState>): BannerView | null {
    if (this.#view !== null && !this.#view.final && world !== this.#shownOn) {
      this.#view = null;
      this.#shownOn = null;
    }
    return this.#view;
  }
}

/**
 * 決着の tick の幕。
 *
 * @param round 決まったラウンド
 * @param winner そのラウンドの勝者。ひきわけなら null
 * @param champion 試合を取ったプレイヤー。試合が決まっていなければ null
 */
export function describeBanner(
  source: HudSource,
  round: number,
  winner: PlayerId | null,
  champion: PlayerId | null,
): BannerView {
  const { world, match, config, roster } = source;
  const wins = config.winsToTake;
  const board = world.players
    .map((player) => `${lookOf(player.animal).emoji}${winsOf(match, player.id)}`)
    .join(SEPARATOR);
  if (champion !== null) {
    const { name } = lookOf(playerOf(world, champion).animal);
    const who = isCpu(roster, champion) ? '（CPU）' : `（${labelOf(roster, champion, name)}）`;
    return {
      emoji: '🏆',
      title: `${name}${who} 優勝！`,
      summary: `${wins}勝先取を達成（全${round}ラウンド）`,
      board,
      note: null,
      button: AGAIN_BUTTON,
      final: true,
    };
  }
  const head = `ラウンド${round}${SEPARATOR}`;
  if (winner !== null) {
    const look = lookOf(playerOf(world, winner).animal);
    return {
      emoji: look.emoji,
      title: `${head}${look.name}の かち`,
      summary: `${wins}勝先取まで あと ${wins - winsOf(match, winner)}勝`,
      board,
      note: world.suddenDeath ? SUDDEN_NOTE : null,
      button: NEXT_ROUND_BUTTON,
      final: false,
    };
  }
  return {
    emoji: '🤝',
    title: `${head}ひきわけ`,
    summary: drawReason(world),
    board,
    note: null,
    button: NEXT_ROUND_BUTTON,
    final: false,
  };
}

/**
 * ひきわけのわけ（原型 L4503-4504）。
 *
 * `roundEnded` はわけを運ばないが、決まったラウンドの盤面から分かる。盤面にだれもいなければ「同時に
 * やられた」、2人以上残っていれば時間切れで、残ったプレイヤーの動物の名前を「・」でつないで添える
 * （試合の側がひきわけにするのは、この2つだけ。延長戦のあとでも同じ形）。
 */
export function drawReason(world: Readonly<WorldState>): string {
  const left = world.players.filter((player) => isAlive(player)).map((player) => lookOf(player.animal).name);
  if (left.length === 0) return ALL_DOWN;
  return `${TIME_UP}${LEFT_LABEL}${left.join('・')}`;
}

function playerOf(world: Readonly<WorldState>, id: PlayerId): Readonly<WorldState['players'][number]> {
  const player = world.players[id];
  if (player === undefined) throw new Error(`プレイヤー ${id} がいない`);
  return player;
}
