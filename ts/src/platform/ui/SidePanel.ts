import type { KeyHelpRow, KeyHelpSpan } from '../../presentation/hud/keyHelp.js';
import {
  CLOCK_CAPTION,
  describeClock,
  describePlayers,
  type CardTag,
  type HudSource,
  type PlayerCardView,
} from '../../presentation/hud/scoreboard.js';
import { el, pointerButton } from './dom.js';
import { speedControl } from './SpeedControl.js';

/**
 * その試合で板に出すキーの案内の行を作る（中身は `presentation/hud/keyHelp.ts` の `describeKeyHelp`）。
 *
 * 試合の材料から作る形にしてあるのは、通信対戦では自分のプレイヤー番号が、つないで
 * 番号を受け取るまで分からないため（板を作る時点では渡せない）。
 */
export type KeyHelpFor = (source: HudSource) => readonly KeyHelpRow[];

/** ツールバーの「ポーズ」のボタンの字（原型 L535・L4217）。止めている間は `RESUME_LABEL`。 */
export const PAUSE_LABEL = '⏸ ポーズ';

/** 止めている間の「ポーズ」のボタンの字（原型 L4217）。 */
export const RESUME_LABEL = '▶ 再開';

/** ツールバーの、タイトルへ戻るボタンの字（原型 L536）。確認を出さずにタイトルへ戻る（原型の注記 L3377-3380）。 */
export const QUIT_LABEL = '設定へ';

/** 横の板に置く操作。試合ごとに違う（1台の試合と通信対戦）。 */
export interface SideControls {
  /** ゲームの速さのつまみ（1台の試合だけ。通信対戦は null で、出さない）。いまの倍率と、動かしたときに呼ぶもの。 */
  readonly speed: { readonly rate: number; readonly change: (rate: number) => void } | null;
  /** 「⏸ ポーズ」を押したとき（1台の試合だけ。通信対戦は null で、ボタンを出さない）。 */
  readonly pause: (() => void) | null;
  /** 「設定へ」を押したとき。 */
  readonly quit: () => void;
}

/** 描くたびに渡すもの。 */
export interface SideFrame {
  /** 名札と時計を作り直すか（`presentation/hud/panelRefresh.ts` の `PanelRefresh`）。 */
  readonly refresh: boolean;
  /** 止めている間か（「ポーズ」のボタンの字を「▶ 再開」にする）。 */
  readonly paused: boolean;
}

/**
 * 試合の横に出す板（原型の `#side`。L516-538）。上から、時計・ゲームの速さのつまみ（1台の試合だけ）・名札・
 * キーの案内・ツールバーを並べる。
 *
 * 中身は `presentation/hud/scoreboard.ts` と `presentation/hud/keyHelp.ts` が作る。ここは写すだけ。
 *
 * ## 骨組みは1回だけ作り、中身だけを替える
 *
 * 時計・つまみ・ツールバーは、板を作ったときに1回だけ作る（原型も HTML に固定の要素として置き、字と印だけを
 * 替える）。作り直さないのは、次の理由から。
 *
 * - 時計：残り 30 秒からの数字の明滅は CSS のアニメーション（`.clock.warn .t`）。要素を作り直すと
 *   アニメーションが頭に戻り、1秒に4回作り直すと薄くなる所まで届かない。字と `warn` の印だけを替える
 * - つまみ：作り直すと、マウスで動かしている途中のつまみが消える
 *
 * 名札（`#cards`）とキーの案内（`#keyhelp`）は、中身を丸ごと組み直す（原型と同じ）。中身が前と同じなら要素に
 * 触れない（同じ文を書き直すだけでも、ブラウザは組み直しの手間をかける。描画は1秒に60回呼ばれる）。
 *
 * ## 名札と時計は、渡された時にだけ作り直す
 *
 * 名札と時計は、`SideFrame.refresh` が真のときだけ作り直す（原型は 0.25 秒ごとと、被弾などの場面だけ）。
 * 骨組みを作った直後（時計と名札が空のとき）も同じで、最初の盤面で作り直すのは `PanelRefresh.due` の役
 * （盤面が替わった最初のフレームでは、いつも真を返す）。
 * キーの案内とポーズのボタンの字は、替わったらすぐ替える。原型は案内を、名札の作り直し（0.25 秒ごとと、被弾などの
 * 場面。L5541）とポーズの切り替え（L4218-4221）のときだけ作り直すので、パッドを繋いだ直後・外した直後の 🎮 の段は、
 * この版のほうが最大 0.25 秒早く出る・消える（docs/06 の「原型に合わせない所」）。
 */
export class SidePanel {
  readonly #keyHelp: KeyHelpFor;
  readonly #clock: HTMLElement;
  readonly #round: HTMLElement;
  readonly #time: HTMLElement;
  readonly #cards: HTMLElement;
  readonly #help: HTMLElement;
  readonly #pause: HTMLButtonElement | null;
  #shownClock: string | null = null;
  #shownCards: string | null = null;
  #shownHelp: string | null = null;

  /**
   * 板の骨組みを作り、`root` の中身を置き換える。
   *
   * @param root 板（`index.html` の `#side`）
   */
  constructor(root: HTMLElement, keyHelp: KeyHelpFor, controls: SideControls) {
    this.#keyHelp = keyHelp;
    this.#round = el('div', { className: 'rnd' });
    this.#time = el('div', { className: 't' });
    this.#clock = el('div', { className: 'clock', data: { part: 'clock' } }, [
      this.#round,
      this.#time,
      el('div', { className: 'lbl', text: CLOCK_CAPTION }),
    ]);
    this.#cards = el('div', { data: { part: 'cards' } });
    this.#help = el('div', { className: 'keyhelp' });
    this.#pause =
      controls.pause === null
        ? null
        : pointerButton(PAUSE_LABEL, controls.pause, { className: 'tbtn', data: { action: 'pause' } });
    const quit = pointerButton(QUIT_LABEL, controls.quit, { className: 'tbtn', data: { action: 'quit' } });
    const speed = controls.speed === null ? null : speedControl(controls.speed.rate, controls.speed.change);
    root.replaceChildren(
      this.#clock,
      ...(speed === null ? [] : [speed]),
      this.#cards,
      this.#help,
      el('div', { className: 'toolbar' }, [this.#pause, quit]),
    );
  }

  /** 板を書き換える。試合がまだ無ければ（通信対戦のロビー）、名札とキーの案内を空にする。 */
  update(source: HudSource | null, frame: SideFrame): void {
    if (this.#pause !== null) {
      const label = frame.paused ? RESUME_LABEL : PAUSE_LABEL;
      if (this.#pause.textContent !== label) this.#pause.textContent = label;
    }
    if (source === null) {
      this.#replace('cards', [], () => []);
      this.#replace('help', [], () => []);
      return;
    }
    const help = this.#keyHelp(source);
    this.#replace('help', help, () => helpNodes(help));
    if (!frame.refresh) return;
    const clock = describeClock(source);
    const clockKey = JSON.stringify(clock);
    if (clockKey !== this.#shownClock) {
      this.#shownClock = clockKey;
      this.#round.textContent = clock.heading;
      this.#time.textContent = clock.time;
      this.#clock.classList.toggle('warn', clock.warn);
    }
    const cards = describePlayers(source);
    this.#replace('cards', cards, () => cards.map(cardElement));
  }

  /** 名札かキーの案内を、中身が前と違うときだけ組み直す。 */
  #replace(part: 'cards' | 'help', content: unknown, build: () => readonly Node[]): void {
    const key = JSON.stringify(content);
    const target = part === 'cards' ? this.#cards : this.#help;
    if (part === 'cards') {
      if (key === this.#shownCards) return;
      this.#shownCards = key;
    } else {
      if (key === this.#shownHelp) return;
      this.#shownHelp = key;
    }
    target.replaceChildren(...build());
  }
}

/** 名札の状態に足すクラス（原型の `.pcard.dead`・`.pcard.negi`。L5502）。盤面にいるときは何も足さない。 */
const CARD_STATE_CLASS: Readonly<Record<PlayerCardView['state'], string>> = {
  alive: '',
  negibon: ' negi',
  out: ' dead',
};

/** 札の色のクラス（原型の `.tag`・`.tag.cpu`・`.tag.negi`。L5506-5509）。 */
const TAG_CLASS: Readonly<Record<CardTag['style'], string>> = {
  human: 'tag',
  cpu: 'tag cpu',
  negibon: 'tag negi',
};

/** 名札1枚（原型 L5530-5538 の並び）。 */
function cardElement(card: PlayerCardView): HTMLElement {
  return el('div', { className: `pcard${CARD_STATE_CLASS[card.state]}`, data: { player: String(card.id) } }, [
    el('div', { className: 'pe', text: card.emoji }),
    el('div', { className: 'pi' }, [
      el('div', { className: 'pn' }, [
        document.createTextNode(`${card.name} `),
        ...card.tags.map((tag) => el('span', { className: TAG_CLASS[tag.style], text: tag.text })),
      ]),
      el('div', { className: 'score', text: card.stars }),
      el('div', { className: 'hearts', text: card.condition }),
      el(
        'div',
        { className: 'stats' },
        card.stats.map((stat) => el('span', { text: stat })),
      ),
      el('div', { className: 'fx', text: card.effects.join(' ') }),
    ]),
  ]);
}

/**
 * キーの案内の行を、原型の組み方（`renderKeyHelp`。L5560-5616）で並べる。
 *
 * - 太字だけで、空きも薄さも無い行（「そうさ」・葱ボンの段の頭）は、`b` をそのまま置く（原型は `.r` で包まない）
 * - ほかの行は `div.r`（上の空き 5px）。行に空きか薄さがあれば `style` に書く（原型が行に直に書いた値）
 * - 区切りの行は、破線の `div`（原型 L5582）
 * - 行の中のキーは `span.k`（小さいキーの形）、太字は `b`
 */
function helpNodes(rows: readonly KeyHelpRow[]): Node[] {
  return rows.map((row) => {
    if (row.rule) return ruleElement();
    const [only] = row.spans;
    const plain = row.marginTop === 0 && row.opacity === 1;
    if (plain && row.spans.length === 1 && only?.kind === 'bold') return el('b', { text: only.text });
    const style = [
      ...(row.marginTop === 0 ? [] : [`margin-top:${row.marginTop}px`]),
      ...(row.opacity === 1 ? [] : [`opacity:${row.opacity}`]),
    ].join(';');
    return el('div', { className: 'r', ...(style === '' ? {} : { style }) }, row.spans.map(spanNode));
  });
}

/**
 * 葱ボンの段の下の、破線の区切り（原型 L5582 が直に書いた style のまま）。
 *
 * `style` の属性として書く（ブラウザでは `style.cssText` に書くのと同じ）。テストの代わりの DOM（happy-dom）は、
 * `var()` を含む一括の指定（`border-top`）を `style` の項目に分けるときに読み違えるので、属性の文で確認する。
 */
function ruleElement(): HTMLElement {
  const rule = el('div');
  rule.setAttribute('style', 'border-top:1px dashed var(--line);margin:9px 0');
  return rule;
}

/** 行の中の1区切り。 */
function spanNode(span: KeyHelpSpan): Node {
  switch (span.kind) {
    case 'key':
      return el('span', { className: 'k', text: span.text });
    case 'bold':
      return el('b', { text: span.text });
    case 'text':
      return document.createTextNode(span.text);
  }
}
