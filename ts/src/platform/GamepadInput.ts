import type { InputSource } from '../domain/input/InputSource.js';
import type { PlayerInput } from '../domain/input/PlayerInput.js';
import { IDLE_INPUT } from '../domain/input/PlayerInput.js';
import type { PlayerId } from '../domain/state/PlayerState.js';
import type { NavCommand } from '../presentation/menu/MenuCursor.js';

/**
 * ゲームパッドの入力。
 *
 * ボタンの並びは、ブラウザが `mapping: "standard"` として正規化した
 * ものを前提にする。製品ごとの対応表を持たずに済む。
 *
 * 以下は実機（Xbox 互換モードを持つ製品）で確認した割り当て。
 *
 * | 番号 | ボタン |
 * |---|---|
 * | 0-3 | A / B / X / Y |
 * | 4-5 | L1 / R1 |
 * | 6-7 | L2 / R2 |
 * | 8-9 | Select / Start |
 * | 10-11 | L3 / R3 |
 * | 12-15 | 十字（上 / 下 / 左 / 右） |
 *
 * ⚠️ 十字キーは軸ではなくボタンとして届く。軸（0,1）は左スティック。
 * ⚠️ HOME は macOS がシステム側で握っていて届かない。
 */
const BUTTON = {
  a: 0,
  b: 1,
  x: 2,
  y: 3,
  l1: 4,
  r1: 5,
  start: 9,
  up: 12,
  down: 13,
  left: 14,
  right: 15,
} as const;

/**
 * スティックを倒したと判定するしきい値と、戻ったと判定するしきい値。
 *
 * 2つに分けてあるのは、境目でちらつくのを防ぐため。
 */
const STICK_ON = 0.5;
const STICK_OFF = 0.35;

/**
 * ⚠️ トリガ（L2 / R2）は割り当てていない。
 *
 * 技のボタンは複数を OR で見るため、トリガに指を乗せているだけで
 * 押しっぱなしと判定され、長押しのとくぎが暴発しうる。
 * `pressed` が立つしきい値はブラウザの実装によって違うので、
 * 実機で測るまで使わない。
 */

/** 読み取ったパッドの状態。テストから差し替えられるよう、配列で受け取る。 */
export type PadSnapshot = {
  readonly mapping: string;
  readonly connected: boolean;
  readonly index: number;
  readonly buttons: readonly { readonly pressed: boolean }[];
  readonly axes: readonly number[];
};

/**
 * どのパッドをつかんでいるか。メニューの操作と試合の操作が、1つを分け合う。
 *
 * ⚠️ 読む側ごとに持たない。メニューで1番をつかんだあと、試合の側が先頭から探し直すと、
 * あとから点いた0番（家族が電源を入れた、寝ていたパッドが起きた）をつかみ、手元の1番では
 * 操作できなくなる。原型も、つかんだ番号を1つだけ持っていた。
 */
export class PadChoice {
  /** 一度つかんだパッドの番号。途中で別のパッドへ移らないようにする。 */
  #index: number | null = null;

  constructor(private readonly read: () => readonly (PadSnapshot | null)[]) {}

  /**
   * 使うパッドを選ぶ。
   *
   * ⚠️ 先頭が繋がっているとは限らない。実機では2番目に入っていた。
   * `mapping` が標準のものを探し、一度見つけたらその番号を覚える。
   */
  pick(): PadSnapshot | null {
    const pads = this.read();
    if (this.#index !== null) {
      const remembered = pads.find((pad) => pad?.index === this.#index);
      if (remembered != null && remembered.connected) return remembered;
      this.#index = null;
    }
    for (const pad of pads) {
      if (pad == null || !pad.connected) continue;
      if (pad.mapping !== 'standard') continue;
      this.#index = pad.index;
      return pad;
    }
    return null;
  }
}

/**
 * スティックの読み方。試合の操作とメニューの操作が同じ規則で読む。
 *
 * スティックの向きには前回の状態（戻りのしきい値）があるので、読む側ごとに1つずつ持つ。
 * どのパッドを読むかは、分け合う `PadChoice` が決める。
 */
class PadReader {
  /** 前回スティックが倒れていた向き。戻りのしきい値に使う。 */
  #stick = { x: 0, y: 0 };

  constructor(private readonly choice: PadChoice) {}

  /** 使うパッド。`PadChoice.pick` を参照。 */
  pick(): PadSnapshot | null {
    return this.choice.pick();
  }

  /** 押している向き。十字キーとスティックの OR。 */
  directions(pad: PadSnapshot): { up: boolean; down: boolean; left: boolean; right: boolean } {
    const stick = this.#readStick(pad);
    return {
      up: held(pad, BUTTON.up) || stick.y < 0,
      down: held(pad, BUTTON.down) || stick.y > 0,
      left: held(pad, BUTTON.left) || stick.x < 0,
      right: held(pad, BUTTON.right) || stick.x > 0,
    };
  }

  /**
   * スティックの傾きを、上下左右のどれか1方向に落とす。
   *
   * ⚠️ 軸ごとに独立してしきい値を当てると、真上から少し倒しただけで
   * 縦横の両方がしきい値を超える。そのとき移動の側が横を優先するため、
   * 全周のうち3分の1ほどが「押した向きと違う方向」になる。
   * 傾きの大きいほうの軸だけを採る。
   */
  #readStick(pad: PadSnapshot): { x: number; y: number } {
    const rawX = pad.axes[0] ?? 0;
    const rawY = pad.axes[1] ?? 0;
    const horizontal = Math.abs(rawX) >= Math.abs(rawY);
    const value = horizontal ? rawX : rawY;

    // いま倒れている向きは弱いしきい値で保ち、新しく倒すときは強いほうで判定する。
    const active = this.#stick.x !== 0 || this.#stick.y !== 0;
    const threshold = active ? STICK_OFF : STICK_ON;
    if (Math.abs(value) < threshold) {
      this.#stick = { x: 0, y: 0 };
      return this.#stick;
    }
    this.#stick = horizontal
      ? { x: Math.sign(value), y: 0 }
      : { x: 0, y: Math.sign(value) };
    return this.#stick;
  }
}

function held(pad: PadSnapshot, index: number): boolean {
  return pad.buttons[index]?.pressed === true;
}

/**
 * パッドのボタンとスティックを、1 tick ぶんの入力に変える窓口。
 *
 * ⚠️ 読み取りに使う関数を（`PadChoice` を通して）引数で受け取るのは、ブラウザの
 * `navigator.getGamepads` に直接触らずにテストできるようにするため。
 * Node には `navigator` が存在するが `getGamepads` は無いので、
 * 素直に書くと実行時に例外になる。
 *
 * @param choice つかむパッド。メニューの操作（`PadMenuInput`）と同じものを渡す
 */
export class GamepadInputSource implements InputSource {
  readonly #reader: PadReader;

  constructor(
    readonly playerId: PlayerId,
    choice: PadChoice,
  ) {
    this.#reader = new PadReader(choice);
  }

  next(): PlayerInput {
    const pad = this.#reader.pick();
    if (pad === null) return IDLE_INPUT;
    return {
      ...this.#reader.directions(pad),
      bomb: held(pad, BUTTON.a) || held(pad, BUTTON.r1),
      action: held(pad, BUTTON.b) || held(pad, BUTTON.x) || held(pad, BUTTON.y) || held(pad, BUTTON.l1),
    };
  }
}

/**
 * ゲームパッドでメニューを動かす。十字キーかスティックで動かし、A で決め、B で戻る（原型と同じ）。
 *
 * 押した瞬間は、前回読んだときの状態との差分だけで作る。
 *
 * ⚠️ 前回の状態を、画面が替わったときに消さない。消すと、A で「つぎへ」を押して次の画面へ
 * 移ったとき、押したままの A が新しい押下に見えて、次の画面の項目まで押してしまう。原型も
 * 同じ理由で前回の状態を消さないことを決まりにしていた（`legacy/test/README.md` の 11 と同じ形の事故）。
 */
export class PadMenuInput {
  readonly #reader: PadReader;
  #previous: ReadonlySet<NavCommand> = new Set();

  /** @param choice つかむパッド。試合の操作（`GamepadInputSource`）と同じものを渡す */
  constructor(choice: PadChoice) {
    this.#reader = new PadReader(choice);
  }

  /** パッドを読み、この回に押し始めた操作を返す。描くたびに1回呼ぶ。 */
  poll(): NavCommand[] {
    const pad = this.#reader.pick();
    const now = new Set<NavCommand>();
    if (pad !== null) {
      const directions = this.#reader.directions(pad);
      for (const direction of ['up', 'down', 'left', 'right'] as const) {
        if (directions[direction]) now.add(direction);
      }
      if (held(pad, BUTTON.a)) now.add('confirm');
      if (held(pad, BUTTON.b)) now.add('back');
    }
    const started = [...now].filter((command) => !this.#previous.has(command));
    this.#previous = now;
    return started;
  }
}

/**
 * ブラウザからパッドを読む。
 *
 * ⚠️ `navigator` の有無だけで判定しない。Node にも `navigator` は
 * 存在し、`getGamepads` だけが無い。関数があるかまで確かめる。
 *
 * ⚠️ 読み取りの例外は握りつぶし、パッドは無いものとして扱う。gamepad を許していない別オリジンの
 * iframe などでは `getGamepads` が SecurityError を投げる。描くたびに読むので、投げたままにすると
 * 描画のループが最初の1枚で止まり、どの画面も動かなくなる（原型も握りつぶしていた）。
 */
export function readBrowserGamepads(): readonly (PadSnapshot | null)[] {
  const nav = globalThis.navigator as { getGamepads?: () => readonly (Gamepad | null)[] };
  if (typeof nav?.getGamepads !== 'function') return [];
  let pads: readonly (Gamepad | null)[];
  try {
    pads = nav.getGamepads();
  } catch {
    return [];
  }
  return pads.map((pad) =>
    pad === null
      ? null
      : {
          mapping: pad.mapping,
          connected: pad.connected,
          index: pad.index,
          buttons: pad.buttons.map((button) => ({ pressed: button.pressed })),
          axes: [...pad.axes],
        },
  );
}
