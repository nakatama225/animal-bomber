import type { Cell } from '../../domain/core/Coord.js';
import type { Tile } from '../../domain/state/Board.js';
import type { Frame } from './Frame.js';
import { screenX, screenY } from './Layout.js';

/**
 * 1マスの床・壁・ブロックを描く。
 *
 * 壊せない壁は上面を明るく、下端を暗くして積み石に見せる。壊せるブロックは
 * レンガの目地を引く。床は市松に塗り分ける。
 */
export function drawTile(frame: Frame, tile: Tile, cell: Cell): void {
  const x = screenX(frame.layout, cell.col);
  const y = screenY(frame.layout, cell.row);
  if (tile === 'hard') drawHard(frame.g, x, y, frame.layout.tile);
  else if (tile === 'soft') drawSoft(frame.g, x, y, frame.layout.tile);
  else drawFloor(frame.g, x, y, frame.layout.tile, (cell.col + cell.row) % 2 === 0);
}

function drawHard(g: CanvasRenderingContext2D, x: number, y: number, size: number): void {
  g.fillStyle = '#6d5a4c';
  g.fillRect(x, y, size, size);
  g.fillStyle = '#8a7565';
  g.fillRect(x + 2, y + 2, size - 4, size - 8);
  g.fillStyle = '#5a4a3d';
  g.fillRect(x + 2, y + size - 8, size - 4, 6);
  g.strokeStyle = '#453830';
  g.lineWidth = 1;
  g.strokeRect(x + 0.5, y + 0.5, size - 1, size - 1);
}

function drawSoft(g: CanvasRenderingContext2D, x: number, y: number, size: number): void {
  g.fillStyle = '#8f5f34';
  g.fillRect(x, y, size, size);
  g.fillStyle = '#a97544';
  g.fillRect(x + 2, y + 2, size - 4, size - 6);

  // レンガの目地。上段は中央で1本、下段は4分の1と4分の3で2本、とずらして積む。
  g.strokeStyle = '#6d4626';
  g.lineWidth = 1.4;
  g.beginPath();
  g.moveTo(x + 2, y + size / 2);
  g.lineTo(x + size - 2, y + size / 2);
  g.moveTo(x + size / 2, y + 2);
  g.lineTo(x + size / 2, y + size / 2);
  g.moveTo(x + size / 4, y + size / 2);
  g.lineTo(x + size / 4, y + size - 2);
  g.moveTo(x + (size * 3) / 4, y + size / 2);
  g.lineTo(x + (size * 3) / 4, y + size - 2);
  g.stroke();
}

function drawFloor(g: CanvasRenderingContext2D, x: number, y: number, size: number, dark: boolean): void {
  g.fillStyle = dark ? '#3f6b3a' : '#457a3d';
  g.fillRect(x, y, size, size);
  // 上端だけ薄く明るくして、マスの区切りを見せる。
  g.fillStyle = 'rgba(255,255,255,.04)';
  g.fillRect(x, y, size, 2);
}
