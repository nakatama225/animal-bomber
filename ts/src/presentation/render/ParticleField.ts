import { lookOf } from '../../content/animals.js';
import { cellKey, centerOf, type Point } from '../../domain/core/Coord.js';
import { SECONDS_PER_TICK } from '../../domain/core/Tick.js';
import { assertNever, type SimEvent } from '../../domain/events/SimEvent.js';
import { itemDefinition } from '../../domain/rules/items.js';
import type { WorldState } from '../../domain/state/WorldState.js';
import type { CosmeticRng } from '../CosmeticRng.js';
import type { Frame } from './Frame.js';
import { ActorEffects } from './ActorEffects.js';
import { drawParticle, puff, scatter, stepParticles, type Particle } from './particles.js';

/** 画面の揺れが収まる速さ（ピクセル毎秒）。 */
const SHAKE_DECAY = 38;

/** 爆発の揺れの上限（ピクセル）。原型と同じ値。 */
const SHAKE_MAX = 10;

/**
 * 粒子と画面の揺れ。
 *
 * ルールの層が返したイベントを受け取って、ブロックの破片・アイテムの煙・倒れたときの顔などの
 * 粒子を出し、爆発や被弾では画面を揺らす。
 * 試合の状態には何も書き込まない。
 */
export class ParticleField {
  #particles: Particle[] = [];
  #shake = 0;
  #world: Readonly<WorldState> | null = null;
  readonly #actors = new ActorEffects();

  constructor(private readonly cosmetic: CosmeticRng) {}

  /**
   * 1 tick ぶんのイベントを受け取る。
   *
   * @param world イベントが起きた盤面。倒れた人の位置や自律物の顔ぶれを読む
   */
  onEvents(events: readonly SimEvent[], world: Readonly<WorldState>): void {
    // 盤面が作り直されたら、前のラウンドの粒子と揺れを持ち越さない。
    if (world !== this.#world) {
      this.#world = world;
      this.#particles = [];
      this.#shake = 0;
      this.#actors.reset(world);
    }

    // 壊れたブロックから出たアイテムには煙を出さない。原型でも破片だけを出していた。
    const brokenCells = new Set<string>();
    for (const event of events) if (event.type === 'blockDestroyed') brokenCells.add(cellKey(event.cell));

    for (const event of events) this.#handle(event, world, brokenCells);
    this.#addShake(this.#actors.observe(world, this.#particles, this.cosmetic));
  }

  /** 1 tick ぶん進める。 */
  step(): void {
    this.#particles = stepParticles(this.#particles);
    this.#shake = Math.max(0, this.#shake - SHAKE_DECAY * SECONDS_PER_TICK);
  }

  /** 画面の揺れの大きさ（ピクセル）。0 なら揺らさない。 */
  get shake(): number {
    return this.#shake;
  }

  /** 粒子を描く。 */
  draw(frame: Frame): void {
    for (const particle of this.#particles) drawParticle(frame, particle);
  }

  /** 揺れは足し合わせず、大きいほうを取る。続けて爆発しても揺れが際限なく育たない。 */
  #addShake(amount: number): void {
    this.#shake = Math.max(this.#shake, amount);
  }

  #handle(event: SimEvent, world: Readonly<WorldState>, brokenCells: ReadonlySet<string>): void {
    const out = this.#particles;
    const rng = this.cosmetic;
    switch (event.type) {
      case 'exploded':
        // 連鎖した数だけ強く揺らす。
        this.#addShake(Math.min(SHAKE_MAX, 3 + event.chained * 1.6));
        return;
      case 'blockDestroyed':
        scatter(out, rng, centerOf(event.cell), {
          count: 7,
          color: '#a2703f',
          spread: 0.6,
          side: 2.4,
          rise: [0.5, 2.9],
          life: [0.5, 0.8],
          size: [4, 8],
        });
        // 爆風で壊れたときは爆発の揺れのほうが大きいので、これが効くのは
        // 爆風以外（体当たりなど）で壊れたときだけになる。
        this.#addShake(4);
        return;
      case 'itemDropped': {
        if (brokenCells.has(cellKey(event.cell))) return;
        const definition = itemDefinition(event.kind);
        puff(out, rng, event.cell, definition.harmful ? '#c98a8a' : '#ffd23f', definition.emoji);
        return;
      }
      case 'itemTaken': {
        const definition = itemDefinition(event.kind);
        puff(out, rng, event.cell, definition.harmful ? '#b98a5a' : '#ffd23f', definition.emoji);
        return;
      }
      case 'itemBurned':
        puff(out, rng, event.cell, '#6b5443', '🌑');
        return;
      case 'playerHurt':
        this.#addShake(6);
        return;
      case 'playerDown': {
        // 位置はイベントが運んだものを使う。同じ tick に延長戦へ入ると、
        // プレイヤーはもう開始位置へ移っている。
        const player = world.players[event.target];
        if (player !== undefined) this.#knockedOut(event.at, lookOf(player.animal));
        return;
      }
      case 'suddenDeath':
        // 延長戦に入るとき、自律物はまとめて片付けられる。踏まれたのでも寿命でもないので、
        // 消えたときの煙を出さないよう、見えている顔ぶれをいまの盤面で取り直す。
        this.#actors.reset(world);
        return;
      case 'techniqueUsed': {
        // とくぎは、出したもの（炎・爆弾・障害物）がそのまま見えるので足さない。
        // 落とし穴のように、見せてはいけないものもある。
        if (event.special) return;
        const player = world.players[event.player];
        if (player === undefined) return;
        // 足元に土ぼこりを立てる。
        scatter(out, rng, { x: player.position.x, y: player.position.y + 0.3 }, {
          count: 6,
          color: '#a6e06a',
          spread: 0,
          side: 2,
          rise: [0, 1.6],
          life: [0.35, 0.35],
          size: [3, 6],
        });
        return;
      }
      case 'bombPlaced':
      case 'effectApplied':
      case 'roundEnded':
      case 'matchEnded':
        // 原型でも、置いた瞬間・効いた瞬間には粒子を出していない。効いたきっかけ
        // （拾った・踏んだ）の側で煙を出す。ラウンドの区切りは盤面の作り直しで片づける。
        return;
      default:
        assertNever(event);
    }
  }

  /** 倒れたときの、体の色の粒と、回りながら浮かぶ顔。 */
  #knockedOut(at: Point, look: { readonly color: string; readonly emoji: string }): void {
    scatter(this.#particles, this.cosmetic, at, {
      count: 16,
      color: look.color,
      spread: 0,
      side: 4,
      rise: [0.6, 4.2],
      life: [0.7, 1.2],
      size: [4, 9],
    });
    this.#particles.push({
      x: at.x,
      y: at.y - 0.2,
      vx: 0,
      vy: -0.7,
      life: 1.1,
      color: '#fff',
      size: 26,
      text: look.emoji,
      spin: true,
      glow: false,
    });
  }
}

