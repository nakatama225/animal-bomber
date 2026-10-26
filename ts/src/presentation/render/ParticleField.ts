import { lookOf } from '../../content/animals.js';
import { cellKey, cellOf, centerOf, sameCell, step, type Point } from '../../domain/core/Coord.js';
import { SECONDS_PER_TICK } from '../../domain/core/Tick.js';
import { assertNever, type SimEvent } from '../../domain/events/SimEvent.js';
import { itemDefinition } from '../../domain/rules/items.js';
import type { WorldState } from '../../domain/state/WorldState.js';
import type { CosmeticRng } from '../CosmeticRng.js';
import type { Frame } from './Frame.js';
import { ActorEffects } from './ActorEffects.js';
import { drawParticle, puff, scatter, spray, stepParticles, type Particle } from './particles.js';

/** 画面の揺れが収まる速さ（ピクセル毎秒）。 */
const SHAKE_DECAY = 38;

/** 爆発の揺れの上限（ピクセル）。原型と同じ値。 */
const SHAKE_MAX = 10;

/**
 * 通常技を使ったときに、足元に土ぼこりを立てる動物。
 *
 * ぞうは入れない。鼻水は吹いた先のマスに水しぶきを出すので（`sprayed`）、足元には何も出さない（原型と同じ）。
 * 表に無い動物は土ぼこりを立てない。
 */
const TAP_DUST: ReadonlySet<string> = new Set(['rabbit', 'fox', 'frog']);

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
        // 爆風で壊れたときは爆発の揺れのほうが大きいので、この揺れが画面に出るのは
        // 爆風以外（体当たりなど）で壊れたときだけになる。
        this.#addShake(4);
        return;
      case 'itemDropped': {
        if (brokenCells.has(cellKey(event.cell))) return;
        const definition = itemDefinition(event.kind);
        // とくぎで撒かれたものは桃色にする（原型と同じ）。
        const scattered = world.items.some((item) => sameCell(item.cell, event.cell) && item.scatteredBy !== undefined);
        const color = scattered ? '#f7a8c4' : definition.harmful ? '#c98a8a' : '#ffd23f';
        puff(out, rng, event.cell, color, definition.emoji);
        return;
      }
      case 'itemExpired':
        // 撒かれたものは桃色、ふつうのうんこは茶色（原型と同じ）。
        puff(out, rng, event.cell, event.scattered ? '#f7a8c4' : '#8a6a3a', '💨');
        return;
      case 'itemBlown':
        puff(out, rng, event.to, '#8a6a3a', '💩');
        return;
      case 'itemWashed':
      case 'bombDoused':
        // 鼻水で消えた。水のしずく。
        puff(out, rng, event.cell, '#9fd8ff', '💧');
        return;
      case 'sprayed': {
        const toward = step({ col: 0, row: 0 }, event.facing);
        for (const cell of event.cells) spray(out, rng, cell, toward);
        return;
      }
      case 'itemTaken': {
        // 引き寄せて手元で適用されたもの（マスが無い）は煙を出さない（原型も出さない）。
        if (event.cell === null) return;
        const definition = itemDefinition(event.kind);
        puff(out, rng, event.cell, definition.harmful ? '#b98a5a' : '#ffd23f', definition.emoji);
        return;
      }
      case 'itemBurned':
        puff(out, rng, event.cell, '#6b5443', '🌑');
        return;
      case 'burntOff':
        // 焼き切れた舌（原型の tongueBurnCheck の puff）。
        puff(out, rng, event.cell, '#ff7a5a', '👅');
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
      case 'leekStopped':
        // 焼けた葱は炎の色、弾かれた葱は盾の顔。
        puff(out, rng, event.cell, event.by === 'blast' ? '#ffd23f' : '#a6e06a', event.by === 'bomb' ? '🛡️' : '🌿');
        return;
      case 'revived':
        puff(out, rng, cellOf(event.at), '#a6e06a', '🌿');
        this.#addShake(9);
        return;
      case 'suddenDeath':
        // 延長戦に入るとき、自律物はまとめて片付けられる。踏まれたのでも寿命でもないので、
        // 消えたときの煙を出さないよう、見えている顔ぶれをいまの盤面で取り直す。
        this.#actors.reset(world);
        return;
      case 'techniqueUsed': {
        // とくぎは、出したもの（炎・爆弾・撒いたうんこ）がそのまま見えるので足さない。
        // 落とし穴のように、見せてはいけないものもある。
        if (event.special) return;
        const player = world.players[event.player];
        if (player === undefined || !TAP_DUST.has(player.animal)) return;
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
      case 'leekThrown':
      case 'lanesClosed':
      case 'roundEnded':
      case 'matchEnded':
      case 'techniqueMoment':
      case 'techniqueRefused':
      case 'reachRestored':
        // 原型でも、置いた瞬間・状態がかかった瞬間には粒子を出していない。かかったきっかけ
        // （拾った・踏んだ）の側で煙を出す。ラウンドの区切りは盤面の作り直しで片づける。
        // 技の途中で起きたことは音だけ（掘り終えた穴の位置は見せない）。技を出せなかった・焼けた
        // 舌が戻ったことは、通知（と操作の音）だけ（原型 L2498・L4307 も粒子を出さない）。
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

