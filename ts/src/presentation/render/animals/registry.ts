import { outline } from '../primitives.js';
import { drawElephantHead } from './elephant.js';
import { drawFoxHead } from './fox.js';
import { drawFrogHead, TONGUE_LOOK } from './frog.js';
import { DIG_LOOK, drawMoleHead } from './mole.js';
import type { ActionLook, HeadPainter } from './painters.js';
import { fillCircle } from './parts.js';
import { drawRabbitHead, SCATTER_LOOK } from './rabbit.js';

/**
 * 動物ごとの頭の描き方と、技の最中の見た目の登録表。
 *
 * 6匹目を足すときは、その動物のファイルを書いてここに1行足す。
 * 体（胴・脚・腕・尻尾）は体型の数字から描くので、動物ごとに書くのは頭だけで済む。
 * 登録を忘れても、実行時は落ちずに丸い頭で描かれる。ただし players.test.ts の
 * 「見た目のある動物にはすべて専用の頭がある」が落ちるので、頭を描くまでは検査を通らない。
 */

/** 動物の鍵ごとの頭の描き方。 */
const HEADS: Readonly<Record<string, HeadPainter>> = {
  rabbit: drawRabbitHead,
  elephant: drawElephantHead,
  mole: drawMoleHead,
  fox: drawFoxHead,
  frog: drawFrogHead,
};

/** 乗っ取り中の振る舞いの `kind` ごとの見た目。 */
const ACTIONS: Readonly<Record<string, ActionLook>> = {
  scatter: SCATTER_LOOK,
  dig: DIG_LOOK,
  tongue: TONGUE_LOOK,
};

/** 頭の描き方が登録されていない動物に使う、体の色の丸い頭。 */
export const plainHead: HeadPainter = (g, x, y, r, _mode, colors) => {
  g.fillStyle = colors.color;
  fillCircle(g, x, y, r);
  outline(g, 2.2);
};

/** その動物の頭の描き方。登録が無ければ丸い頭にする。 */
export function headPainterOf(animal: string): HeadPainter {
  return HEADS[animal] ?? plainHead;
}

/** その振る舞いの最中の見た目。登録が無ければ何も足さない。 */
export function actionLookOf(kind: string): ActionLook | undefined {
  return ACTIONS[kind];
}
