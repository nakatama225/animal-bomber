import { FULL_TURN } from '../Frame.js';
import { outline } from '../primitives.js';

/**
 * 頭や体の手描きで繰り返し使う、小さな部品。
 *
 * 目の描き方を1か所で決めておくと、動物ごとの頭で目の形がばらつかない。
 */

/** 楕円を塗る。輪郭は残るので、続けて `outline()` で縁取れる。 */
export function fillEllipse(
  g: CanvasRenderingContext2D,
  x: number,
  y: number,
  radiusX: number,
  radiusY: number,
  rotation = 0,
): void {
  g.beginPath();
  g.ellipse(x, y, radiusX, radiusY, rotation, 0, FULL_TURN);
  g.fill();
}

/** 円を塗る。輪郭は残るので、続けて `outline()` で縁取れる。 */
export function fillCircle(g: CanvasRenderingContext2D, x: number, y: number, r: number): void {
  g.beginPath();
  g.arc(x, y, r, 0, FULL_TURN);
  g.fill();
}

/** 目の描き分け。書かなかった項目は既定の丸い目になる。 */
export interface EyeOptions {
  /** 閉じた目（弧の線1本）にする。 */
  readonly closed?: boolean;
  /** 白目の色。 */
  readonly white?: string;
  /** 黒目の色。 */
  readonly iris?: string;
  /** 白目の縦横比。1 より小さいと細い目になる。 */
  readonly tall?: number;
  /** 黒目を寄せる向き。1 で右（横向きの顔の前）、0 で真ん中。 */
  readonly look?: number;
}

/** 目を描く。白目・黒目・光の3つを重ねる。閉じた目は線1本にする。 */
export function drawEye(
  g: CanvasRenderingContext2D,
  x: number,
  y: number,
  r: number,
  options: EyeOptions = {},
): void {
  if (options.closed === true) {
    g.strokeStyle = 'rgba(20,10,0,.8)';
    g.lineWidth = Math.max(1.4, r * 0.42);
    g.beginPath();
    g.moveTo(x - r, y);
    g.quadraticCurveTo(x, y + r * 0.5, x + r, y);
    g.stroke();
    return;
  }
  g.fillStyle = options.white ?? '#fffdf6';
  fillEllipse(g, x, y, r, r * (options.tall ?? 1.05));
  outline(g, 1.3);
  g.fillStyle = options.iris ?? '#1b1008';
  fillEllipse(g, x + (options.look ?? 0) * r * 0.3, y + r * 0.08, r * 0.52, r * 0.62);
  g.fillStyle = 'rgba(255,255,255,.92)';
  fillCircle(g, x - r * 0.22, y - r * 0.3, r * 0.2);
}

/**
 * 三角の耳。内側に一回り小さい三角を重ねる。
 *
 * @param tilt 耳の傾き（ラジアン）。(x, y) を軸に回す
 */
export function drawTriangleEar(
  g: CanvasRenderingContext2D,
  x: number,
  y: number,
  width: number,
  height: number,
  tilt: number,
  fill: string,
  inner: string,
): void {
  g.save();
  g.translate(x, y);
  g.rotate(tilt);
  g.fillStyle = fill;
  g.beginPath();
  g.moveTo(0, -height);
  g.lineTo(width * 0.62, height * 0.35);
  g.lineTo(-width * 0.62, height * 0.35);
  g.closePath();
  g.fill();
  outline(g, 1.7);
  g.fillStyle = inner;
  g.beginPath();
  g.moveTo(0, -height * 0.55);
  g.lineTo(width * 0.32, height * 0.22);
  g.lineTo(-width * 0.32, height * 0.22);
  g.closePath();
  g.fill();
  g.restore();
}
