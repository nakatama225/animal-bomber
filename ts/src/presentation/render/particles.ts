import { centerOf } from '../../domain/core/Coord.js';
import type { Cell, Point } from '../../domain/core/Coord.js';
import { SECONDS_PER_TICK } from '../../domain/core/Tick.js';
import type { CosmeticRng } from '../CosmeticRng.js';
import type { Frame } from './Frame.js';
import { screenX, screenY } from './Layout.js';

/**
 * 粒子1つ。位置と速度はマス単位で持ち、描くときにピクセルへ直す。
 *
 * 大きさだけはピクセルで持つ。原型の既定のマス（44px）のときの値で書いてあり、
 * 描くときにいまのマスの大きさに合わせて伸び縮みさせる。
 */
export interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  /** 消えるまでの残り（秒）。 */
  life: number;
  readonly color: string;
  readonly size: number;
  /** 絵文字を出すなら、その文字。四角い粒なら null。 */
  readonly text: string | null;
  /** 絵文字を回しながら出すか。倒れたときの顔に使う。 */
  readonly spin: boolean;
  /**
   * 光の玉として描くか。追いかける炎の通った跡に使う。
   *
   * 光の玉は動かず、重力も受けず、0.5 秒かけて薄れる。
   */
  readonly glow: boolean;
}

/** 粒子にかかる下向きの加速（マス毎秒毎秒）。舞い上がった粒が弧を描いて落ちる。 */
const GRAVITY = 6;

/** 大きさの基準にしたマスの大きさ（ピクセル）。原型の既定値。 */
const BASE_TILE = 44;

/** 光の玉が消えるまでの長さ（秒）。 */
export const GLOW_LIFE = 0.5;

/**
 * 煙を1つ出す。
 *
 * 真上へ浮かぶ絵文字1つと、まわりへ散る小さな粒6つ。
 */
export function puff(out: Particle[], rng: CosmeticRng, cell: Cell, color: string, text: string): void {
  const { x, y } = centerOf(cell);
  out.push({ x, y, vx: 0, vy: -1.2, life: 0.6, color, size: 20, text, spin: false, glow: false });
  for (let i = 0; i < 6; i += 1) {
    out.push({
      x,
      y,
      vx: rng.jitter(1.3),
      vy: -rng.between(0, 2.2),
      life: rng.between(0.4, 0.7),
      color,
      size: rng.between(3, 6),
      text: null,
      spin: false,
      glow: false,
    });
  }
}

/** 範囲の下限と上限。 */
type Range = readonly [min: number, max: number];

/** 四角い粒の散らし方。速さはマス毎秒、大きさは基準のマスでのピクセル。 */
export interface ScatterSpec {
  readonly count: number;
  readonly color: string;
  /** 出る位置の散らばり（マス）。 */
  readonly spread: number;
  /** 横へ散る速さの幅。この半分まで左右どちらへも散る。 */
  readonly side: number;
  /** 上へ跳ぶ速さ。 */
  readonly rise: Range;
  readonly life: Range;
  readonly size: Range;
}

/** 四角い粒をまとめて上向きに散らす。 */
export function scatter(out: Particle[], rng: CosmeticRng, at: Point, spec: ScatterSpec): void {
  for (let i = 0; i < spec.count; i += 1) {
    out.push({
      x: at.x + rng.jitter(spec.spread / 2),
      y: at.y + rng.jitter(spec.spread / 2),
      vx: rng.jitter(spec.side / 2),
      vy: -rng.between(spec.rise[0], spec.rise[1]),
      life: rng.between(spec.life[0], spec.life[1]),
      color: spec.color,
      size: rng.between(spec.size[0], spec.size[1]),
      text: null,
      spin: false,
      glow: false,
    });
  }
}

/** 光の玉を1つ置く。 */
export function glow(out: Particle[], at: Point): void {
  out.push({ x: at.x, y: at.y, vx: 0, vy: 0, life: GLOW_LIFE, color: '', size: 0, text: null, spin: false, glow: true });
}

/** 1 tick ぶん動かし、消えたものを取り除いた一覧を返す。 */
export function stepParticles(particles: readonly Particle[]): Particle[] {
  const dt = SECONDS_PER_TICK;
  const alive: Particle[] = [];
  for (const particle of particles) {
    particle.life -= dt;
    if (particle.life <= 0) continue;
    if (!particle.glow) {
      particle.x += particle.vx * dt;
      particle.y += particle.vy * dt;
      particle.vy += GRAVITY * dt;
    }
    alive.push(particle);
  }
  return alive;
}

/** 粒子を1つ描く。 */
export function drawParticle(frame: Frame, particle: Particle): void {
  const { g, layout } = frame;
  const x = screenX(layout, particle.x);
  const y = screenY(layout, particle.y);
  g.save();
  if (particle.glow) {
    drawGlow(g, x, y, layout.tile, particle.life / GLOW_LIFE);
  } else {
    // 残り 0.5 秒を切ったら薄れていく。
    g.globalAlpha = Math.max(0, Math.min(1, particle.life * 2));
    const size = (particle.size * layout.tile) / BASE_TILE;
    if (particle.text !== null) {
      g.font = `${Math.round(size)}px system-ui`;
      g.textAlign = 'center';
      g.textBaseline = 'middle';
      if (particle.spin) {
        g.translate(x, y);
        g.rotate(particle.life * 6);
        g.fillText(particle.text, 0, 0);
      } else {
        g.fillText(particle.text, x, y);
      }
    } else {
      g.fillStyle = particle.color;
      g.fillRect(x - size / 2, y - size / 2, size, size);
    }
  }
  g.restore();
}

/** 青白い光の玉。`fade` は 1 で出たて、0 で消える。 */
function drawGlow(g: CanvasRenderingContext2D, x: number, y: number, tile: number, fade: number): void {
  g.globalAlpha = Math.max(0, fade) * 0.8;
  const light = g.createRadialGradient(x, y, 1, x, y, tile * 0.52);
  light.addColorStop(0, '#ffffff');
  light.addColorStop(0.3, '#c8f2ff');
  light.addColorStop(0.62, '#41a8ff');
  light.addColorStop(1, 'rgba(20,50,160,0)');
  g.fillStyle = light;
  g.fillRect(x - tile * 0.6, y - tile * 0.6, tile * 1.2, tile * 1.2);
}
