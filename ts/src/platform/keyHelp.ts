import { navKeysOf, type KeyBinding } from './Keyboard.js';

/**
 * キー配置の説明。試合の横の板に出す。
 *
 * 説明の文は配置の表（`Keyboard.ts`）から作る。説明を手で書くと、キーを足したときに
 * 説明だけ古いまま残る。
 */
export interface KeyHelp {
  /** 誰の操作か（「1P」など）。 */
  readonly title: string;
  readonly lines: readonly string[];
}

/** キーの呼び方。書いていないキーは `KeyW` → `W` の形で縮める。 */
const KEY_NAMES: Readonly<Record<string, string>> = {
  ArrowUp: '↑',
  ArrowDown: '↓',
  ArrowLeft: '←',
  ArrowRight: '→',
  Slash: '/',
  Period: '.',
  Comma: ',',
  ShiftLeft: '左Shift',
  ShiftRight: '右Shift',
};

/** キーの呼び方（`KeyboardEvent.code` から）。 */
export function keyName(code: string): string {
  const named = KEY_NAMES[code];
  if (named !== undefined) return named;
  if (code.startsWith('Key') || code.startsWith('Digit')) return code.replace(/^(Key|Digit)/, '');
  return code;
}

/** メニューの動かし方の説明。キーはメニューの操作の表（`Keyboard.ts` の `navKeysOf`）から作る。 */
export function menuHelp(): string {
  const names = (keys: readonly string[]): string => keys.map(keyName).join('・');
  const moves = (['up', 'left', 'down', 'right'] as const).flatMap(navKeysOf).map(keyName).join(' ');
  return `${moves} で選び、${names(navKeysOf('confirm'))} で決める。${names(navKeysOf('back'))} で1つ前の画面へ（マウスでも押せる）`;
}

/** ゲームパッドでメニューを動かすときの説明（`GamepadInput.ts` の `PadMenuInput` と同じ）。 */
export const PAD_MENU_HELP = '🎮 十字キーか左スティックで選び、A で決める。B で1つ前の画面へ';

/** ゲームパッドの割り当ての説明（`GamepadInput.ts` の割り当てと同じ）。 */
export const GAMEPAD_HELP: readonly string[] = [
  '🎮 十字キーか左スティックでうごく',
  '🎮 ばくだん A・R1 ／ 技 B・X・Y・L1',
];

/**
 * 1人ぶんの説明を作る。
 *
 * 移動のキーは「上・左・下・右」の順に並べる（W A S D と同じ並び）。
 * 1つの向きに複数のキーがあるときは、組ごとに分けて並べる（W A S D ／ ↑ ← ↓ →）。
 */
export function keyHelpFor(title: string, binding: KeyBinding): KeyHelp {
  const directions = [binding.up, binding.left, binding.down, binding.right];
  const sets = Math.max(...directions.map((keys) => keys.length));
  const moves: string[] = [];
  for (let i = 0; i < sets; i += 1) {
    moves.push(
      directions
        .map((keys) => keys[i])
        .filter((code): code is string => code !== undefined)
        .map(keyName)
        .join(' '),
    );
  }
  return {
    title,
    lines: [
      `うごく ${moves.join(' ／ ')}`,
      `ばくだん ${binding.bomb.map(keyName).join(' ')}`,
      `技 ${binding.action.map(keyName).join(' ')}（長押しでとくぎ）`,
    ],
  };
}
