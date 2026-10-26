import type { KeyHelpRow, KeyHelpSpan } from '../../presentation/hud/keyHelp.js';
import {
  CLOCK_CAPTION,
  describeClock,
  describePlayers,
  type ClockView,
  type HudSource,
  type PlayerCardView,
} from '../../presentation/hud/scoreboard.js';
import { el } from './dom.js';

/**
 * その試合で板に出すキーの案内の行を作る（中身は `presentation/hud/keyHelp.ts` の `describeKeyHelp`）。
 *
 * 試合の材料から作る形にしてあるのは、通信対戦では自分のプレイヤー番号が、つないで
 * 番号を受け取るまで分からないため（板を作る時点では渡せない）。
 */
export type KeyHelpFor = (source: HudSource) => readonly KeyHelpRow[];

/**
 * 試合の横に出す板。時計・プレイヤーごとの名札・キーの案内を並べる。
 *
 * 中身は `presentation/hud/scoreboard.ts` と `presentation/hud/keyHelp.ts` が作る。ここは写すだけ。
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
    const key = JSON.stringify([clock, cards, help]);
    if (key === this.#shown) return;
    this.#shown = key;

    this.#root.replaceChildren(
      ...(clock === null ? [] : [clockElement(clock)]),
      el('div', { className: 'cards' }, cards.map(cardElement)),
      el('div', { className: 'keyhelp' }, help.length === 0 ? [] : [helpElement(help)]),
    );
  }
}

function clockElement(clock: ClockView): HTMLElement {
  return el('div', { className: clock.warn ? 'clock warn' : 'clock', data: { part: 'clock' } }, [
    el('div', { className: 'round', text: clock.heading }),
    el('div', { className: 'time', text: clock.time }),
    el('div', { className: 'label', text: CLOCK_CAPTION }),
  ]);
}

function cardElement(card: PlayerCardView): HTMLElement {
  return el('div', { className: `card ${card.state}`, data: { player: String(card.id) } }, [
    el('div', { className: 'emoji', text: card.emoji }),
    el('div', { className: 'info' }, [
      el('div', { className: 'name' }, [
        document.createTextNode(`${card.name} `),
        ...card.tags.map((tag) => el('span', { className: 'tag', text: tag.text })),
      ]),
      el('div', { className: 'stars', text: card.stars }),
      el('div', { className: 'condition', text: card.condition }),
      el('div', { className: 'stats', text: card.stats.join(' ') }),
      el('div', { className: 'effects', text: card.effects.join(' ') }),
    ]),
  ]);
}

/**
 * キーの案内の行を、文のまま並べる。太字だけの行は `b`、ほかの行は `div`（太字の区切りは `b`）。
 *
 * キーは1つずつ空白で区切った文にする（キーの形・行の間・薄さ・区切りの破線はまだ写さない。区切りの行は飛ばす）。
 */
function helpElement(rows: readonly KeyHelpRow[]): HTMLElement {
  return el(
    'div',
    { className: 'help' },
    rows.flatMap((row) => {
      if (row.rule) return [];
      const [only] = row.spans;
      if (row.spans.length === 1 && only?.kind === 'bold') return [el('b', { text: only.text })];
      return [el('div', {}, row.spans.map((span, index) => spanNode(span, row.spans[index - 1]?.kind)))];
    }),
  );
}

/** 行の中の1区切り。キーが続くときは、間に空白を挟む。 */
function spanNode(span: KeyHelpSpan, before: KeyHelpSpan['kind'] | undefined): Node {
  if (span.kind === 'bold') return el('b', { text: span.text });
  return document.createTextNode(span.kind === 'key' && before === 'key' ? ` ${span.text}` : span.text);
}
