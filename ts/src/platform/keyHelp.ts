import { navKeysOf } from './Keyboard.js';

/**
 * メニューの動かし方の説明。遊び方の説明（`ui/manual.ts`）に出す。
 *
 * キーはメニューの操作の表（`Keyboard.ts` の `navKeysOf`）から作る。手で書くと、キーを足したときに
 * 説明だけ古いまま残る。
 *
 * 試合のキーの案内（キャラ選びの1行と横の板）は、原型と同じ固定の文（`presentation/menu/keyHints.ts`・
 * `presentation/hud/keyHelp.ts`）。原型の案内は割り当てた全部のキーを書かないので、割り当ての表からは作らない。
 */

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
