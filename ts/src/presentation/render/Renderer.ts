import { TICKS_PER_SECOND } from '../../domain/core/Tick.js';
import type { SimEvent } from '../../domain/events/SimEvent.js';
import { isAlive, isInvulnerable } from '../../domain/state/PlayerState.js';
import type { WorldState } from '../../domain/state/WorldState.js';
import { CosmeticRng } from '../CosmeticRng.js';
import { drawAirActor } from './actors.js';
import { drawTile } from './board.js';
import { drawBlast, drawBomb } from './bombs.js';
import { ParticleField } from './ParticleField.js';
import type { Frame } from './Frame.js';
import { drawItem } from './items.js';
import type { Layout } from './Layout.js';
import { drawNegibon } from './negibon.js';
import { drawPlayer } from './players.js';
import type { PlayerView } from './PlayerView.js';
import { PositionHistory } from './PositionHistory.js';

/**
 * 試合の状態を canvas に描く。
 *
 * **状態を読むだけで、書き換えない。** 描かなくても試合は進み、描き方を
 * どう変えても試合の結果は変わらない。
 *
 * ## 描く順序
 *
 * 後に描いたものが手前に来るので、順序がそのまま重なり方になる。
 *
 * 1. 床・壁・ブロック
 * 2. アイテム（とくぎで撒かれたうんこもアイテムとして描く）
 * 3. 爆弾
 * 4. 爆風
 * 5. プレイヤー（画面の奥＝上にいる者から）
 * 6. 外周の葱ボン
 * 7. 宙を飛ぶ自律物（追いかける炎・跳ね回る爆弾・葱）
 * 8. 粒子
 * 9. ポーズの幕（止めている間だけ）
 */
export class Renderer {
  readonly #g: CanvasRenderingContext2D;
  #layout: Layout;
  readonly #cosmetic = new CosmeticRng();
  readonly #history = new PositionHistory();
  readonly #effects: ParticleField;

  /** @param layout 盤面の寸法（`layoutFor`・`boardLayoutFor`） */
  constructor(g: CanvasRenderingContext2D, layout: Layout) {
    this.#g = g;
    this.#layout = layout;
    this.#effects = new ParticleField(this.#cosmetic);
  }

  /**
   * 盤面の寸法を替える（窓の大きさが替わったとき。原型の `resize` の `fitBoard`）。
   *
   * 粒子と位置の控えは残す（作り直すと、試合の途中で粒子が消える）。
   */
  resize(layout: Layout): void {
    this.#layout = layout;
  }

  /** tick を進める直前に呼ぶ。位置の間を埋めるための控えを取る。 */
  beforeTick(world: Readonly<WorldState>): void {
    this.#history.capture(world);
  }

  /** tick を進めた直後に、起きたイベントを渡す。粒子を出す。 */
  afterTick(events: readonly SimEvent[], world: Readonly<WorldState>): void {
    this.#history.onEvents(events, world);
    this.#effects.onEvents(events, world);
    this.#effects.step();
  }

  /**
   * 1枚描く。
   *
   * @param alpha 前の tick から次の tick までの進み具合（0 以上 1 以下）。1 になるのは、倍率を掛けた
   *   1台の試合で、次の tick の位置まで埋め終えたとき（`GameSpeed.progress`）
   * @param paused 止めている間か。止めている間は、盤面の上にポーズの幕を描く（`drawPause`）
   */
  draw(world: Readonly<WorldState>, alpha: number, paused = false): void {
    const g = this.#g;
    const layout = this.#layout;
    const frame: Frame = {
      g,
      layout,
      time: (world.now + alpha) / TICKS_PER_SECOND,
      cosmetic: this.#cosmetic,
    };

    // ⚠️ 背景を塗るのは揺れ（平行移動）より前。揺らしてから塗ると、ずれたぶん
    // 端が塗り残され、前の画面の絵が残る。原型で実際に起きた。
    g.setTransform(1, 0, 0, 1, 0, 0);
    const background = g.createLinearGradient(0, 0, 0, layout.height);
    background.addColorStop(0, '#231810');
    background.addColorStop(1, '#170f0a');
    g.fillStyle = background;
    g.fillRect(0, 0, layout.width, layout.height);

    g.save();
    const shake = this.#effects.shake;
    if (shake > 0.2) g.translate(this.#cosmetic.jitter(shake / 2), this.#cosmetic.jitter(shake / 2));

    for (const { cell, tile } of world.board.cells()) drawTile(frame, tile, cell);
    for (const item of world.items) drawItem(frame, item, world.now);
    for (const bomb of world.bombs) drawBomb(frame, bomb);
    for (const blast of world.blasts) drawBlast(frame, blast);

    const views = world.players
      .filter((player) => isAlive(player))
      .map((player) => this.#viewOf(world, player.id, alpha))
      .sort((a, b) => a.y - b.y);
    for (const view of views) drawPlayer(frame, view);

    // 葱ボンは宙を飛ぶ自律物より下に描く。撃った葱は葱ボンの位置から飛び出すので、
    // 逆にすると、出たばかりの葱が葱ボンの絵に隠れる。
    for (const player of world.players) {
      if (player.life.kind === 'negibon') drawNegibon(frame, player.animal, player.life, world.now);
    }
    for (const actor of world.actors) drawAirActor(frame, actor);
    this.#effects.draw(frame);
    if (paused) drawPause(g, layout);
    g.restore();
  }

  #viewOf(world: Readonly<WorldState>, id: WorldState['players'][number]['id'], alpha: number): PlayerView {
    const player = world.players[id];
    if (player === undefined) throw new Error(`プレイヤー ${id} がいない`);
    const before = this.#history.before(world, id);
    const x = before === undefined ? player.position.x : before.x + (player.position.x - before.x) * alpha;
    const y = before === undefined ? player.position.y : before.y + (player.position.y - before.y) * alpha;
    return {
      player,
      x,
      y,
      moving: before !== undefined && before.walked !== player.walked,
      invulnerable: isInvulnerable(player, world.now),
    };
  }
}

/** ポーズの幕の真ん中の字（原型 L4570）。 */
export const PAUSE_TITLE = 'PAUSE';

/** ポーズの幕の下の字（原型 L4572）。 */
export const PAUSE_HINT = 'P で再開';

/**
 * ポーズの幕（原型の `draw` の最後。L4566-4573）。盤面全体を暗くし、真ん中に「PAUSE」、その 30px 下に
 * 「P で再開」を出す。
 *
 * 原型と同じく、画面の揺れ（平行移動）の内側で描く。止めている間は揺れが減らない（tick を進めないため）ので、
 * 揺れが残ったまま止めると、盤面と一緒に幕と字も揺れ、ずれた側の端の帯は暗くならない（原型も同じ）。
 */
function drawPause(g: CanvasRenderingContext2D, layout: Layout): void {
  const centerX = layout.width / 2;
  const centerY = layout.height / 2;
  g.fillStyle = 'rgba(10,6,4,.6)';
  g.fillRect(0, 0, layout.width, layout.height);
  g.fillStyle = '#ffd23f';
  g.font = '900 34px system-ui';
  g.textAlign = 'center';
  g.textBaseline = 'middle';
  g.fillText(PAUSE_TITLE, centerX, centerY);
  g.font = '600 14px system-ui';
  g.fillStyle = '#c9ab97';
  g.fillText(PAUSE_HINT, centerX, centerY + 30);
}
