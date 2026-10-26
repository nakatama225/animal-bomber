import type { InputSource } from '../domain/input/InputSource.js';
import type { PlayerInput } from '../domain/input/PlayerInput.js';
import type { PlayerId } from '../domain/state/PlayerState.js';
import type { NavCommand } from '../presentation/menu/MenuCursor.js';

/**
 * どのキーがどの操作に当たるか（原型の `CONTROLS`。L1119-1150）。
 *
 * 1台のキーボードで2人が同時に触るため、1P は左側、2P は右側に
 * 固めてある。加えて、移動をどちらの手でやっても反対の手で爆弾を
 * 押せるよう、爆弾のキーを左右に1つずつ持たせている。
 *
 * - ⛔ Option（Alt）を主のキーにしない。macOS は修飾キーを押している間、ほかのキーを離したことを
 *   送らないことがあり、「たまに反応しない」が起きる（原型の注記）。原型と同じく、技のキーの1つ
 *   （従のキー）としては割り当ててある。ほかの技のキーでも出せる
 * - ⛔ Command（Meta）はどのプレイヤーの操作にも使えない。ブラウザが予約していて
 *   `preventDefault` も無効なため、cmd+W でタブが閉じる
 * - ⛔ 1P を右側・2P を左側へ動かす作り替えはしない。1つのキーボードで手がぶつかる
 *
 * 画面のキーの案内（キャラ選びの1行と横の板）は、原型と同じく割り当てた全部のキーを書かない
 * （J と Option は書かない）。案内の文は固定の文（`presentation/menu/keyHints.ts`・`presentation/hud/keyHelp.ts`）。
 */
export interface KeyBinding {
  readonly up: readonly string[];
  readonly down: readonly string[];
  readonly left: readonly string[];
  readonly right: readonly string[];
  readonly bomb: readonly string[];
  readonly action: readonly string[];
}

/**
 * 1人で遊ぶときの配置（原型の `CONTROLS.solo`）。WASD と矢印の両方を受ける。
 *
 * 爆弾の J と技の K は1人のときだけ（2人の組には無い。2P の技の M・N は逆に2人のときだけ）。
 */
export const SOLO_KEYS: KeyBinding = {
  up: ['KeyW', 'ArrowUp'],
  down: ['KeyS', 'ArrowDown'],
  left: ['KeyA', 'ArrowLeft'],
  right: ['KeyD', 'ArrowRight'],
  bomb: ['Space', 'Enter', 'KeyZ', 'Slash', 'KeyJ'],
  action: [
    'KeyE',
    'KeyQ',
    'KeyX',
    'KeyC',
    'KeyR',
    'KeyK',
    'ShiftLeft',
    'ShiftRight',
    'Period',
    'Comma',
    'AltLeft',
    'AltRight',
  ],
};

/** 2人で遊ぶときの、キーボードの左側を使うプレイヤー（原型の `CONTROLS.p1`）。 */
export const PLAYER1_KEYS: KeyBinding = {
  up: ['KeyW'],
  down: ['KeyS'],
  left: ['KeyA'],
  right: ['KeyD'],
  bomb: ['Space', 'KeyZ'],
  action: ['KeyE', 'KeyQ', 'KeyX', 'KeyC', 'KeyR', 'ShiftLeft', 'AltLeft'],
};

/** 2人で遊ぶときの、キーボードの右側を使うプレイヤー（原型の `CONTROLS.p2`）。 */
export const PLAYER2_KEYS: KeyBinding = {
  up: ['ArrowUp'],
  down: ['ArrowDown'],
  left: ['ArrowLeft'],
  right: ['ArrowRight'],
  bomb: ['Enter', 'Slash'],
  action: ['ShiftRight', 'Period', 'Comma', 'KeyM', 'KeyN', 'AltRight'],
};

/**
 * ブラウザの既定の動きを止めるキー（原型と同じ7つ。L3063）。
 *
 * 画面も修飾キーも見ず、いつも止める（原型と同じ）。矢印と Space は、画面が縦に収まらないときに
 * ページを動かす。
 */
export const PREVENTED_KEYS: readonly string[] = [
  'Space',
  'ArrowUp',
  'ArrowDown',
  'ArrowLeft',
  'ArrowRight',
  'Enter',
  'Slash',
];

/**
 * メニューを動かすキーと、その操作（原型の `KEY_TO_PAD`。L3186-3189）。
 *
 * 決定は Enter と Space。どちらも爆弾のキーなので、決定で「はじめる」を押すと、押したまま
 * 試合が始まる。ルールの層が、ラウンドの始まりに押していた爆弾のボタンを離すまで無効にして
 * いるので、開始位置に爆弾は置かれない（`WorldState.ts` の `HELD_AT_ROUND_START`）。
 */
const NAV_COMMANDS: Readonly<Record<string, NavCommand>> = {
  ArrowUp: 'up',
  ArrowDown: 'down',
  ArrowLeft: 'left',
  ArrowRight: 'right',
  Enter: 'confirm',
  Space: 'confirm',
  Escape: 'back',
  Backspace: 'back',
};

/** その操作に当たるキー（表の順）。遊び方の説明に使う。 */
export function navKeysOf(command: NavCommand): string[] {
  return Object.entries(NAV_COMMANDS)
    .filter(([, bound]) => bound === command)
    .map(([code]) => code);
}

/**
 * キーを押したことを、メニューの操作に翻訳する。メニューの操作に使わないキーなら null。
 *
 * 押し続けたときの繰り返し（`repeat`）は数えない。修飾キー（Command・Ctrl・Option）は見ない
 * （原型と同じ。L3062-3068）。
 */
export function navCommandOf(event: Pick<KeyboardEvent, 'code' | 'repeat'>): NavCommand | null {
  if (event.repeat) return null;
  return NAV_COMMANDS[event.code] ?? null;
}

/**
 * 押されているキーを答えるもの。
 *
 * `KeyboardInputSource` がこの形だけに依存するので、テストでは
 * ブラウザのイベントを起こさずに好きな状態を渡せる。
 */
export interface KeyStateReader {
  /** そのキーのどれかが、いま押されているか。向きに使う。 */
  readonly anyOf: (codes: readonly string[]) => boolean;
  /**
   * そのキーのどれかを、爆弾と技のボタンとして押しているか。
   *
   * 押しているキーと、押した瞬間を残したキー（もう離していても）の両方を数える。ただし Option・Command を
   * 離したときに捨てたキーは、キーの繰り返しで戻っても、もう一度押すまで数えない（`KeyboardWatcher` の説明）。
   */
  readonly buttonAnyOf: (codes: readonly string[]) => boolean;
}

/**
 * `KeyStateReader` に、押した瞬間を忘れる口を足したもの。
 *
 * いつ忘れるかは画面の流れ（`Shell`）が決める。入力を tick へ取り込んだあと（通信対戦では送ったあと）と、
 * 1台の試合を止めている間・試合の外の毎フレーム。
 */
export interface KeyboardState extends KeyStateReader {
  readonly forgetTaps: () => void;
}

/** 離すと、ほかの押しているキーを捨てる修飾キー（原型 L3096）。 */
const DROPPING_MODIFIERS: readonly string[] = ['AltLeft', 'AltRight', 'MetaLeft', 'MetaRight'];

/**
 * いま押されているキーと、押した瞬間を持つ。
 *
 * ブラウザの入力を受けるのはこのクラスだけで、ルールの層には
 * 「どのキーか」も「いつ押したか」も届かない。
 *
 * ## 押してすぐ離した爆弾と技のキーも、1 tick は押したことにする
 *
 * 押してから離すまでが 1 tick より短いと、tick の間に押したことと離したことが両方届き、押されているキーの
 * 集まりだけを見ると、押したこと自体が消える。そこで、押した瞬間（繰り返しでない keydown で、押していなかった
 * キー。原型の `pressed`。L3061-3067）を別に覚えておき、爆弾と技は、離していても押していたことにする
 * （`buttonAnyOf`）。向きは押されているキーだけで見る（原型も、押してすぐ離した向きのキーでは動かない）。
 * 覚えたものは `forgetTaps` で忘れる。
 *
 * ## Option・Command を離したら、ほかの押しているキーを捨てる
 *
 * macOS は Option・Command を押している間、ほかのキーを離したことを送らないことがある。原型は、Option か
 * Command を離した時点でほかの押しているキーを捨て、押したままのキーはブラウザのキーの繰り返しで戻す
 * （L3093-3098）。原型の繰り返しは押した瞬間を立てないので、戻ったキーで爆弾も技も出ない。
 *
 * この版は、押した瞬間を試合の側が前の tick と比べて作る。戻ったキーをそのまま押していることにすると、
 * 前の tick に離していた爆弾のキーが押し下がって見え、爆弾を置く。そこで、捨てたキーは繰り返しで戻っても、
 * 繰り返しでない keydown でもう一度押すまで、爆弾と技には数えない。向きは繰り返しで戻す（原型の注記の2つの
 * 狙い：押したままの向きは戻す・勝手に技や爆弾を出さない）。
 */
export class KeyboardWatcher implements KeyboardState {
  readonly #held = new Set<string>();
  /** 押した瞬間を覚えたキー（もう離していても）。 */
  readonly #tapped = new Set<string>();
  /** Option・Command を離したときに捨てて、まだもう一度押していないキー。 */
  readonly #dropped = new Set<string>();
  #attached = false;

  readonly #onDown = (event: KeyboardEvent): void => {
    if (PREVENTED_KEYS.includes(event.code)) event.preventDefault();
    const edge = !this.#held.has(event.code) && !event.repeat;
    this.#held.add(event.code);
    if (event.repeat) return;
    this.#dropped.delete(event.code);
    if (edge) this.#tapped.add(event.code);
  };

  readonly #onUp = (event: KeyboardEvent): void => {
    this.#held.delete(event.code);
    this.#dropped.delete(event.code);
    if (!DROPPING_MODIFIERS.includes(event.code)) return;
    for (const code of [...this.#held]) {
      // 押したままの Option・Command は捨てない（原型の `/^(Alt|Meta)/`）。
      if (/^(Alt|Meta)/.test(code)) continue;
      this.#held.delete(code);
      this.#dropped.add(code);
    }
  };

  /**
   * 画面から離れたときに、押しっぱなしの状態を消す（原型 L3100）。
   *
   * これが無いと、キーを押したままタブを切り替えて戻ったときに
   * 壁へ向かって歩き続ける。離したことがブラウザから通知されないため。
   *
   * 押していたキーは、Option・Command を離したときと同じく捨てた印へ移す。押したまま戻ってきたキーは、
   * キーの繰り返しで向きにだけ戻り、爆弾と技にはもう一度押すまで数えない（原型の blur は押しているキーだけを
   * 消し、繰り返しは押した瞬間を立てないので、戻ったキーで爆弾も技も出ない）。押した瞬間は消さない（原型と同じ）。
   */
  readonly #onBlur = (): void => {
    for (const code of this.#held) this.#dropped.add(code);
    this.#held.clear();
  };

  attach(target: Window = window): void {
    if (this.#attached) return;
    target.addEventListener('keydown', this.#onDown);
    target.addEventListener('keyup', this.#onUp);
    target.addEventListener('blur', this.#onBlur);
    this.#attached = true;
  }

  detach(target: Window = window): void {
    if (!this.#attached) return;
    target.removeEventListener('keydown', this.#onDown);
    target.removeEventListener('keyup', this.#onUp);
    target.removeEventListener('blur', this.#onBlur);
    this.#held.clear();
    this.#tapped.clear();
    this.#dropped.clear();
    this.#attached = false;
  }

  /** そのキーのどれかが押されているか。 */
  anyOf(codes: readonly string[]): boolean {
    return codes.some((code) => this.#held.has(code));
  }

  /** 爆弾と技のボタンとして、そのキーのどれかを押しているか（`KeyStateReader.buttonAnyOf`）。 */
  buttonAnyOf(codes: readonly string[]): boolean {
    return codes.some((code) => this.#tapped.has(code) || (this.#held.has(code) && !this.#dropped.has(code)));
  }

  /** 押した瞬間を忘れる。 */
  forgetTaps(): void {
    this.#tapped.clear();
  }
}

/**
 * 押しているキーを、1 tick ぶんの入力に変える窓口。
 *
 * CPU や通信から届く窓口と同じ資格で `Simulation` に繋がる。
 * ゲーム本体はこれがキーボードだと知らない。
 */
export class KeyboardInputSource implements InputSource {
  constructor(
    readonly playerId: PlayerId,
    private readonly watcher: KeyStateReader,
    private readonly binding: KeyBinding,
  ) {}

  next(): PlayerInput {
    return {
      up: this.watcher.anyOf(this.binding.up),
      down: this.watcher.anyOf(this.binding.down),
      left: this.watcher.anyOf(this.binding.left),
      right: this.watcher.anyOf(this.binding.right),
      bomb: this.watcher.buttonAnyOf(this.binding.bomb),
      action: this.watcher.buttonAnyOf(this.binding.action),
      // とくぎを直に出すキーは割り当てない（原型の人間は長押しでしか出せない。`PlayerInput.special`）。
      special: false,
    };
  }
}
