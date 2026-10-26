import { lookOf } from '../../content/animals.js';
import type { PlayerState } from '../../domain/state/PlayerState.js';
import type { WorldState } from '../../domain/state/WorldState.js';
import type { Controller, Roster } from './roster.js';

/**
 * 横の板のキーの案内の中身（原型の `renderKeyHelp`。L5560-5616）。
 *
 * **文と値を返すだけで、画面に書かない。** 行は「文」「キー」「太字」の区切りの並びで返す。キーは
 * 描く側が小さいキーの形（原型の `.k`）で描く。キーの文は原型の文を逐語で写した（原型の案内は、割り当てた
 * 全部のキーを書かない。J・K・Option などは書かない。原型の食い違いのまま）。
 *
 * 並び（上から）：
 *
 * 1. 葱ボンの段。外周にいる人間のプレイヤーごとに、移動と発射のキーと注記（操作がまるごと変わるので、
 *    いちばん上に出す）
 * 2. 操作の段。人間が1なら「そうさ」の形、2以上なら「1P」「2P」の形。技の行の頭は技の呼び方（動物ごと）
 * 3. パッドの段。パッドを認識していて、パッドを試合に繋ぐ遊び方のとき
 * 4. ポーズの行と、Select の行
 *
 * ## 通信対戦は、この端末のプレイヤーだけを出す
 *
 * 原型は人間のプレイヤーの数で形を分けるので、通信対戦で人間が2以上いると「1P WASD／2P ↑←↓→」の形になる。
 * 原型の通信対戦の人間はどれも1人用の操作（`CONTROLS.solo`。L1263-1265）なので、出す形と実際の操作が
 * 合わない。この版は、この端末で操作するプレイヤー（名札の一覧で `local` のもの）だけを人間として数え、
 * 1人の形で出す（葱ボンの段も、この端末のプレイヤーのぶんだけ）。
 *
 * ## ポーズの行は、ポーズできる端末にだけ出す
 *
 * 原型は「P ポーズ」の行を役割を見ずに出すので、ポーズできないゲストにも出る。この版の通信対戦はだれも
 * ポーズできない（止めたことを全員へ同じ tick で配る約束が無い）ので、ポーズできない端末には出さない。
 * Select の行の条件は原型と同じく「ポーズ中か、ポーズできない端末」（原型はゲスト）。
 */

/** 行の中の1区切り。 */
export interface KeyHelpSpan {
  /** `text`：ふつうの文。`key`：キー1つ（原型の `<span class="k">`）。`bold`：太字（原型の `<b>`）。 */
  readonly kind: 'text' | 'key' | 'bold';
  readonly text: string;
}

/** 案内の1行。`marginTop` と `opacity` は原型の行に付けた style の値（px と不透明度）。 */
export interface KeyHelpRow {
  readonly spans: readonly KeyHelpSpan[];
  readonly marginTop: number;
  readonly opacity: number;
  /** 区切りの破線の行か（原型 L5582。`spans` は空）。 */
  readonly rule: boolean;
}

/** キーの案内を作るのに要るもの。 */
export interface KeyHelpSource {
  readonly world: Readonly<WorldState>;
  readonly roster: Roster;
  /** パッドを認識しているか（原型の `PAD.on`）。 */
  readonly padConnected: boolean;
  /** パッドを試合に繋ぐ遊び方か（1人で CPU と遊ぶときと通信対戦。原型 L3570）。 */
  readonly padInMatch: boolean;
  /** ポーズ中か。 */
  readonly paused: boolean;
  /** この端末でポーズできるか（1台の試合だけ）。 */
  readonly canPause: boolean;
}

/** 技の行の末尾（原型 L5589 ほか）。 */
const LONG_PRESS = '（長押しでとくぎ🍗）';

/** 技を使うプレイヤーがいないときの、技の行の頭（原型の `skillLabelOf(undefined)`）。 */
const NO_PLAYER_SKILL_LABEL = '技';

/** 矢印キーの並び（原型の案内の順。上・左・下・右）。 */
const ARROWS = ['↑', '←', '↓', '→'] as const;

/** 左手で動かすキーの並び。 */
const WASD = ['W', 'A', 'S', 'D'] as const;

const text = (value: string): KeyHelpSpan => ({ kind: 'text', text: value });
const bold = (value: string): KeyHelpSpan => ({ kind: 'bold', text: value });
const keys = (...names: readonly string[]): KeyHelpSpan[] => names.map((name) => ({ kind: 'key', text: name }));

function row(spans: readonly KeyHelpSpan[], options: { marginTop?: number; opacity?: number } = {}): KeyHelpRow {
  return { spans, marginTop: options.marginTop ?? 0, opacity: options.opacity ?? 1, rule: false };
}

const RULE: KeyHelpRow = { spans: [], marginTop: 0, opacity: 1, rule: true };

/** キーの案内の行を、上から順に。 */
export function describeKeyHelp(source: KeyHelpSource): KeyHelpRow[] {
  const humans = shownHumans(source.world, source.roster);
  const two = humans.length > 1;
  const rows: KeyHelpRow[] = [];
  humans.forEach((player, index) => {
    if (player.life.kind === 'negibon') {
      rows.push(...laneRows(source.roster, player, two, two && index === 1));
    }
  });
  const only = humans.length === 1 ? humans[0] : undefined;
  rows.push(...(only === undefined ? pairRows(humans) : soloRows(only)));
  if (source.padConnected && source.padInMatch) rows.push(...padRows(source.world, source.roster));
  if (source.canPause) {
    const pad = source.padConnected ? keys('Start') : [];
    rows.push(row([...keys('P'), ...pad, text(' ポーズ')], { marginTop: 7, opacity: 0.8 }));
  }
  if (source.padConnected && (source.paused || !source.canPause) && source.padInMatch) {
    rows.push(row([...keys('Select'), text(' 設定へもどる')], { opacity: 0.8 }));
  }
  return rows;
}

/** キーを [] で囲んで1つの文にしたもの（テストで読むため）。区切りの行は `---`。 */
export function keyHelpText(helpRow: KeyHelpRow): string {
  if (helpRow.rule) return '---';
  return helpRow.spans.map((span) => (span.kind === 'key' ? `[${span.text}]` : span.text)).join('');
}

/**
 * 案内に出す人間のプレイヤー（プレイヤー番号の順）。
 *
 * この端末で操作するプレイヤーが名札の一覧にいれば（通信対戦）、そのプレイヤーだけ。
 * いなければ（1台の試合）、人間のプレイヤー全員（モジュールの説明）。
 */
function shownHumans(world: Readonly<WorldState>, roster: Roster): PlayerState[] {
  const humans = world.players.filter((player) => roster[player.id]?.kind === 'human');
  const local = humans.filter((player) => isLocal(roster[player.id]));
  return local.length > 0 ? local : humans;
}

function isLocal(controller: Controller | undefined): boolean {
  return controller?.kind === 'human' && controller.local;
}

/**
 * 葱ボンの段（原型 L5568-5583）。
 *
 * 外周は回る向きに関係なく、上下左右そのままの向きに動く（原型の注記）。2人のときはそれぞれのキーだけ、
 * 1人のときは両方の組を出す。`right` は2人のうちの 2P（右側のキーで操作する。原型の `CONTROLS.p2`）。
 */
function laneRows(roster: Roster, player: PlayerState, two: boolean, right: boolean): KeyHelpRow[] {
  let move: KeyHelpSpan[];
  let fire: KeyHelpSpan[];
  if (right) {
    move = keys(...ARROWS);
    fire = [...keys('Enter'), text(' か '), ...keys('/')];
  } else if (two) {
    move = keys(...WASD);
    fire = [...keys('Space'), text(' か '), ...keys('Z')];
  } else {
    move = [...keys(...WASD), text(' / '), ...keys(...ARROWS)];
    fire = [...keys('Space'), text(' か '), ...keys('Enter')];
  }
  const controller = roster[player.id];
  const label = two && controller?.kind === 'human' ? `（${controller.label}）` : '';
  return [
    row([bold(`🌿 ${lookOf(player.animal).name}${label} は葱ボン＝場外`)]),
    row([text('外周を移動 '), ...move]),
    row([text('葱を発射 '), ...fire]),
    row([text('生きてるヤツに当てると'), bold('交代して復活'), text('（HP1・パワーアップは維持）。残り1分で退場')], {
      marginTop: 5,
      opacity: 0.85,
    }),
    RULE,
  ];
}

/** 人間が1のときの操作の段（原型 L5586-5589）。 */
function soloRows(player: PlayerState): KeyHelpRow[] {
  return [
    row([bold('そうさ')]),
    row([text('うごく '), ...keys(...WASD), text(' / '), ...keys(...ARROWS)]),
    row([text('ばくだん '), ...keys('Space', 'Enter', 'Z', '/')]),
    row([text(`${skillLabel(player)} `), ...keys('E', 'Q', 'X', 'C', 'R', 'Shift'), text(LONG_PRESS)]),
  ];
}

/**
 * 人間が2以上（または0）のときの操作の段（原型 L5591-5596）。
 *
 * 原型は1人目と2人目だけを書く。いなければ絵文字を空に、技の呼び方を「技」にする
 * （原型の `humans[0]?…:''` と `skillLabelOf(undefined)`）。
 */
function pairRows(humans: readonly PlayerState[]): KeyHelpRow[] {
  const [first, second] = humans;
  return [
    row([bold(`1P ${emojiOf(first)}`)]),
    row([...keys(...WASD), text(' ／ ばくだん '), ...keys('Space', 'Z')]),
    row([text(`${skillLabel(first)} `), ...keys('E', 'Q', 'X', 'C', 'R', '左Shift'), text(LONG_PRESS)]),
    row([bold(`2P ${emojiOf(second)}`)], { marginTop: 7 }),
    row([...keys(...ARROWS), text(' ／ ばくだん '), ...keys('Enter', '/')]),
    row([text(`${skillLabel(second)} `), ...keys('右Shift', '.', ',', 'M', 'N'), text(LONG_PRESS)]),
  ];
}

/**
 * パッドの段（原型 L5602-5607）。
 *
 * 技の呼び方は、パッドで操作するプレイヤーのもの。通信対戦はこの端末のプレイヤー
 * （原型の `players[CFG.lanLocal]`）、1台はプレイヤー番号 0（原型の `players[0]`）。
 */
function padRows(world: Readonly<WorldState>, roster: Roster): KeyHelpRow[] {
  const me = world.players.find((player) => isLocal(roster[player.id])) ?? world.players[0];
  const rows = [
    row([text('🎮 '), ...keys('十字', 'スティック'), text(' うごく ／ ばくだん '), ...keys('A', 'R1')], { marginTop: 7 }),
  ];
  if (me !== undefined) {
    rows.push(row([text(`${skillLabel(me)} `), ...keys('B', 'X', 'Y', 'L1'), text(LONG_PRESS)]));
  }
  return rows;
}

function skillLabel(player: PlayerState | undefined): string {
  return player === undefined ? NO_PLAYER_SKILL_LABEL : lookOf(player.animal).skillLabel;
}

function emojiOf(player: PlayerState | undefined): string {
  return player === undefined ? '' : lookOf(player.animal).emoji;
}
