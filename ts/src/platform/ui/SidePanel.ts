import type { PlayerId } from '../../domain/state/PlayerState.js';
import {
  describeClock,
  describePlayers,
  type ClockView,
  type HudSource,
  type PlayerCardView,
} from '../../presentation/hud/scoreboard.js';
import type { KeyHelp } from '../keyHelp.js';
import { el } from './dom.js';

/** 板に出すキー配置の説明と、それが誰の操作か。 */
export interface KeyHelpEntry {
  readonly playerId: PlayerId;
  readonly help: KeyHelp;
}

/**
 * その試合で板に出すキー配置の説明を選ぶ。
 *
 * 試合の材料から選ぶ形にしてあるのは、通信対戦では自分のプレイヤー番号が、つないで
 * 番号を受け取るまで分からないため（板を作る時点では渡せない）。
 */
export type KeyHelpFor = (source: HudSource) => readonly KeyHelpEntry[];

/** 葱ボンになっている人に出す操作の説明。移動と爆弾のキーのまま使える。 */
const NEGIBON_HELP = '🌿 葱ボンのあいだは、外周をうごいて爆弾のキーで葱を撃つ。盤面の人に当てると入れ替わって戻れる';

/**
 * 試合の横に出す板。時計・プレイヤーごとの名札・キー配置の説明を並べる。
 *
 * 中身は `presentation/hud/scoreboard.ts` が作る。ここは写すだけ。
 *
 * 毎回描き直さない。中身が前と同じなら要素に触れない。触れると、同じ文を
 * 書き直すだけでもブラウザは組み直しの手間をかける（描画は1秒に60回呼ばれる）。
 */
export class SidePanel {
  readonly #root: HTMLElement;
  readonly #keyHelp: KeyHelpFor;
  #shown: string | null = null;

  constructor(root: HTMLElement, keyHelp: KeyHelpFor) {
    this.#root = root;
    this.#keyHelp = keyHelp;
  }

  /** 板を書き換える。試合が無ければ空にする。 */
  update(source: HudSource | null): void {
    const clock = source === null ? null : describeClock(source);
    const cards = source === null ? [] : describePlayers(source);
    const help = source === null ? [] : this.#keyHelp(source);
    const negibon = help.filter((entry) => cards[entry.playerId]?.state === 'negibon');
    const key = JSON.stringify([clock, cards, help.map((entry) => entry.playerId), negibon.map((entry) => entry.playerId)]);
    if (key === this.#shown) return;
    this.#shown = key;

    this.#root.replaceChildren(
      ...(clock === null ? [] : [clockElement(clock)]),
      el('div', { className: 'cards' }, cards.map(cardElement)),
      el(
        'div',
        { className: 'keyhelp' },
        help.map((entry) =>
          helpElement(entry.help, negibon.includes(entry) ? NEGIBON_HELP : null),
        ),
      ),
    );
  }
}

function clockElement(clock: ClockView): HTMLElement {
  const classes = ['clock', clock.warn ? 'warn' : '', clock.suddenDeath ? 'sudden' : ''].filter(Boolean);
  return el('div', { className: classes.join(' '), data: { part: 'clock' } }, [
    el('div', { className: 'round', text: `ROUND ${clock.round} ・ ${clock.winsToTake}勝先取` }),
    el('div', { className: 'time', text: clock.time }),
    el('div', { className: 'label', text: clock.suddenDeath ? '⚡ サドンデス' : 'TIME' }),
  ]);
}

function cardElement(card: PlayerCardView): HTMLElement {
  return el('div', { className: `card ${card.state}`, data: { player: String(card.id) } }, [
    el('div', { className: 'emoji', text: card.emoji }),
    el('div', { className: 'info' }, [
      el('div', { className: 'name' }, [
        document.createTextNode(`${card.name} `),
        el('span', { className: 'tag', text: card.tag }),
      ]),
      el('div', { className: 'stars', text: card.stars }),
      el('div', { className: 'condition', text: card.condition }),
      el('div', { className: 'stats', text: card.stats }),
      el('div', { className: 'effects', text: card.effects.join(' ') }),
    ]),
  ]);
}

function helpElement(help: KeyHelp, note: string | null): HTMLElement {
  return el('div', { className: 'help' }, [
    el('b', { text: help.title }),
    ...help.lines.map((line) => el('div', { text: line })),
    note === null ? null : el('div', { className: 'note', text: note }),
  ]);
}
