/**
 * 描画で繰り返し使う小さな関数（角の丸い四角形の輪郭を作る・縁取りの線を引く）。
 *
 * `roundRect` は輪郭（パス）を作るだけで、塗るか線を引くかは呼ぶ側が決める。
 * `outline` は、呼ぶ側が作った輪郭に黒い縁取りの線を引く。
 */

/** 角の丸い四角形の輪郭を作る。 */
export function roundRect(
  g: CanvasRenderingContext2D,
  x: number,
  y: number,
  width: number,
  height: number,
  radius: number,
): void {
  const r = Math.max(0, Math.min(radius, width / 2, height / 2));
  g.beginPath();
  g.moveTo(x + r, y);
  g.lineTo(x + width - r, y);
  g.quadraticCurveTo(x + width, y, x + width, y + r);
  g.lineTo(x + width, y + height - r);
  g.quadraticCurveTo(x + width, y + height, x + width - r, y + height);
  g.lineTo(x + r, y + height);
  g.quadraticCurveTo(x, y + height, x, y + height - r);
  g.lineTo(x, y + r);
  g.quadraticCurveTo(x, y, x + r, y);
  g.closePath();
}

/** 黒い縁取りの線を引く。手描きの絵の輪郭に使う。 */
export function outline(g: CanvasRenderingContext2D, width: number): void {
  g.strokeStyle = 'rgba(0,0,0,.62)';
  g.lineWidth = width;
  g.stroke();
}
