import type { Frame } from '../Frame.js';
import type { PlayerView } from '../PlayerView.js';

/**
 * 動物の絵を描き分けるための型。
 *
 * 体（胴・脚・腕・尻尾）は体型の数字から共通の手順で描き、頭と技の最中の見た目だけを
 * 動物ごとに書く。ここはその2つを差し込む口の形を決める。
 */

/**
 * 頭の向き。
 *
 * 横向きはいつも右向きとして描く。左向きは体ごと左右を反転するので、
 * 頭を描く関数は右向きだけを知っていればよい。
 * 後頭部は目も口も描かない。向きが一目で分かるようにするため。
 */
export type HeadMode = 'front' | 'side' | 'back';

/** 頭を描くのに使う色。動物の見た目のデータから渡す。 */
export interface HeadColors {
  /** 体の色。 */
  readonly color: string;
  /** 影になる部分の色。 */
  readonly shade: string;
  /** 頬やマズルなど明るい部分の色。 */
  readonly fur: string;
}

/**
 * 動物の頭を描く関数。
 *
 * (x, y) は頭の中心、r は頭の半径（ピクセル）。絵文字は使わず手描きにする。
 */
export type HeadPainter = (
  g: CanvasRenderingContext2D,
  x: number,
  y: number,
  r: number,
  mode: HeadMode,
  colors: HeadColors,
) => void;

/** 体の姿勢の崩し方。技の最中に体を震わせるときなどに使う。 */
export interface BodyPose {
  /** 腰を落とす量（マス単位）。 */
  readonly drop: number;
  /** 足元を軸にした傾き（ラジアン）。 */
  readonly tilt: number;
  /** 縦の伸び縮み。1 で元の形。横は逆数で縮め、体の大きさが変わって見えないようにする。 */
  readonly squash: number;
}

/** 崩していない姿勢。 */
export const NEUTRAL_POSE: BodyPose = { drop: 0, tilt: 0, squash: 1 };

/**
 * 乗っ取り中の振る舞い（`ActiveAction`）ごとの見た目。
 *
 * ルールの層の振る舞いは、外へは `kind` の文字列しか見せない。何を描くかは
 * この層の判断なので、振る舞いの種類と見た目の対応はこの層に置く。
 * 書かなかった項目は何も足さない。
 */
export interface ActionLook {
  /** 状態の表示に並べる絵文字。 */
  readonly icon?: string;
  /** 体より先に（下に）描くもの。(x, y) はプレイヤーの位置（ピクセル）。 */
  readonly drawUnder?: (frame: Frame, view: PlayerView, x: number, y: number) => void;
  /** 体より後に（上に）描くもの。 */
  readonly drawOver?: (frame: Frame, view: PlayerView, x: number, y: number) => void;
  /** 体の姿勢。 */
  readonly pose?: (frame: Frame) => BodyPose;
}
