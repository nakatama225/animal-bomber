import type { CosmeticRng } from '../CosmeticRng.js';
import type { Layout } from './Layout.js';

/**
 * 1回の描画で、どの描く関数にも共通して渡すもの。
 *
 * 描く関数はこれと、描く対象（マス・爆弾・プレイヤーなど）だけを受け取る。
 * 盤面全体を受け取らないのは、何を読んで描いているかを引数で分かるようにするため。
 */
export interface Frame {
  readonly g: CanvasRenderingContext2D;
  readonly layout: Layout;
  /**
   * 見た目の時刻（秒）。点滅や揺れの位相に使う。
   *
   * 試合の tick 数から作るので、止めれば止まり、倍速にすれば速くなる。
   * 実時間を読まない。
   */
  readonly time: number;
  /**
   * 見た目だけの乱数。爆風のちらつきなど。
   *
   * ⚠️ ここで `Math.random` を直接呼ばず、これを使う。どこで見た目の乱数を
   * 引いているかを、この名前で探せるようにするため。
   */
  readonly cosmetic: CosmeticRng;
}

/** 円を描くときの角度の終わり。 */
export const FULL_TURN = Math.PI * 2;
