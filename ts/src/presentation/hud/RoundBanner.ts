import { lookOf } from '../../content/animals.js';
import type { SimEvent } from '../../domain/events/SimEvent.js';
import { winsOf } from '../../domain/state/MatchState.js';
import type { PlayerId } from '../../domain/state/PlayerState.js';
import type { WorldState } from '../../domain/state/WorldState.js';
import { displayName } from './roster.js';
import type { HudSource } from './scoreboard.js';

/** 盤面に重ねる幕の中身。 */
export interface BannerView {
  readonly emoji: string;
  readonly title: string;
  /** 補足の行。上から順に出す。 */
  readonly lines: readonly string[];
  /** 試合が決まった幕か。決まったら消えない。 */
  readonly final: boolean;
}

/**
 * ラウンドが決まったときに、盤面に重ねる幕。
 *
 * ## 幕は時間で消える
 *
 * 出している間は、決着のあとの待ち（`GameSession` の `ROUND_INTERMISSION`）と重なる。
 * 待ちが終わって次の盤面に替わったら消す。ボタンで送る形にはしていない。
 * 送る操作を足すと、通信対戦では「誰の操作で次へ進むか」を全員で揃える必要が出てくる。
 * 待ちの長さは試合の側が tick で数えているので、全員の端末で同じ tick に次へ進む。
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
   * tick を進めたあとに呼ぶ。
   *
   * @param source 進める前の盤面を持つもの。決着の tick の盤面が、幕を出す盤面になる
   */
  onEvents(events: readonly SimEvent[], source: HudSource): void {
    for (const event of events) {
      if (event.type === 'matchEnded') {
        this.#show(championBanner(source, event.champion), source.world);
        return;
      }
    }
    for (const event of events) {
      if (event.type === 'roundEnded') this.#show(roundBanner(source, event.round, event.winner), source.world);
    }
  }

  /** いま出す幕。次のラウンドの盤面に替わっていれば、消して null を返す。 */
  current(world: Readonly<WorldState>): BannerView | null {
    if (this.#view !== null && !this.#view.final && world !== this.#shownOn) {
      this.#view = null;
      this.#shownOn = null;
    }
    return this.#view;
  }

  #show(view: BannerView, world: Readonly<WorldState>): void {
    this.#view = view;
    this.#shownOn = world;
  }
}

/** 延長戦に入っていたときに添える行。 */
const SUDDEN_DEATH_WON = '⚡サドンデス決着';
const SUDDEN_DEATH_DRAWN = '⚡サドンデスでも決まらなかった';

function roundBanner(source: HudSource, round: number, winner: PlayerId | null): BannerView {
  const board = scoreLine(source);
  if (winner === null) {
    const lines = source.world.suddenDeath ? [board, SUDDEN_DEATH_DRAWN] : [board];
    return { emoji: '🤝', title: `ラウンド${round} ひきわけ`, lines, final: false };
  }
  const player = playerOf(source, winner);
  const left = source.config.winsToTake - winsOf(source.match, winner);
  const lines = [`${source.config.winsToTake}勝先取まで あと ${left}勝`, board];
  if (source.world.suddenDeath) lines.push(SUDDEN_DEATH_WON);
  return {
    emoji: lookOf(player.animal).emoji,
    title: `ラウンド${round} ${displayName(source.roster, winner, player.animal)}の かち`,
    lines,
    final: false,
  };
}

function championBanner(source: HudSource, champion: PlayerId | null): BannerView {
  const board = scoreLine(source);
  if (champion === null) return { emoji: '🤝', title: '引き分け', lines: [board], final: true };
  const player = playerOf(source, champion);
  const lines = [`${source.config.winsToTake}勝先取を達成（全${source.match.round}ラウンド）`, board];
  if (source.world.suddenDeath) lines.push(SUDDEN_DEATH_WON);
  return {
    emoji: '🏆',
    title: `${displayName(source.roster, champion, player.animal)} 優勝！`,
    lines,
    final: true,
  };
}

/** 全員の勝ち数を1行に並べる（「🐰2 🐘1」）。 */
function scoreLine(source: HudSource): string {
  return source.world.players
    .map((player) => `${lookOf(player.animal).emoji}${winsOf(source.match, player.id)}`)
    .join('  ');
}

function playerOf(source: HudSource, id: PlayerId): Readonly<WorldState['players'][number]> {
  const player = source.world.players[id];
  if (player === undefined) throw new Error(`プレイヤー ${id} がいない`);
  return player;
}
