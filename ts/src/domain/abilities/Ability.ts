import type { Cell } from '../core/Coord.js';
import type { Tick } from '../core/Tick.js';
import type { SimEvent } from '../events/SimEvent.js';
import type { PlayerState } from '../state/PlayerState.js';
import type { WorldState } from '../state/WorldState.js';
import type { ActiveAction } from './ActiveAction.js';

/**
 * 動物ごとの違い。
 *
 * ## 拡張に開いた形にしている
 *
 * 6匹目を追加するときに触るのは、**その動物のファイルと登録の1行だけ**。
 * 既存の動物にも、移動・爆弾・被弾の処理にも変更を加えない。
 *
 * 原型では、動物の違いが能力フラグ（`jump` / `tongue` / `lineBomb` など）を
 * 見る `if` として、移動・爆弾・被弾・描画それぞれの中に散っていた。
 * 追加のたびに全部を見つけて修正する必要があり、見落とすとその動物だけ
 * 特定の場面で反応しない。
 *
 * ⚠️ 交換しているもの：**能力の一覧がコード上のどこにも現れない**。
 * 対応漏れは実行するまで分からない。同じ問いに対する Python 版の答え
 * （閉じた union で網羅性を保証する）と読み比べてほしい。
 *
 * ## この抽象が正しいかの判定
 *
 * ぞうの突進で決まる。突進は移動・破壊・取得・被弾の4つに同時に
 * 割り込むため、**これが特別扱いなしで書けたなら他の4匹は自動的に通る**。
 * 書けなければ抽象の引き方が間違っているので、作り直す。
 */
export interface Ability {
  /** 動物の識別子。 */
  readonly key: string;

  /* ---- 数値の違い（既存の計算に倍率や加算を与えるだけのもの） ---- */

  /** 基本速度にかける倍率。 */
  readonly speedMultiplier: number;
  /** 初期の火力への加算。 */
  readonly powerBonus: number;
  /** 初期の体力への加算（半分の単位）。 */
  readonly hpBonus: number;
  /** 初期の爆弾数への加算。 */
  readonly bombBonus: number;
  /** 拾ったアイテムの効果の倍率。良いものにも悪いものにもかかる。 */
  readonly itemMultiplier: number;

  /** とくぎを出すのに必要な長押しの長さ。強い技ほど長くする。 */
  readonly holdTicks: Tick;

  /* ---- 振る舞いの違い（あるものだけ書けばよい） ---- */

  /**
   * そのマスを通り抜けられるか。
   *
   * 書かなければ、通り抜けの特例なし。
   */
  readonly passesThrough?: (world: Readonly<WorldState>, cell: Cell, player: PlayerState) => boolean;

  /**
   * 技のボタンを押した瞬間。通常技。そのまま押し続けてしきい値に届くと、とくぎも出る。
   *
   * 自分の振る舞いの最中にも呼ばれる（技のボタンを受け付けない振る舞いの間は呼ばれない。
   * `ActiveAction.blocksButtons`）。
   *
   * @returns 始まった振る舞い（無ければ null。あれば今の振る舞いと差し替わる）と、起きたイベント。
   *   技が出せない状態だった（届く長さが 0 になっている、など）ときは、`refusal` にその知らせを入れる
   *   （画面の通知と操作の音のため）。`events` には入れない。呼び出し側は `events` が1つでもあれば
   *   技が出たとみなして `techniqueUsed` を前に付けるので、入れると技を出した音まで鳴る
   */
  readonly onTap?: (
    world: WorldState,
    player: PlayerState,
  ) => {
    action: ActiveAction | null;
    events: SimEvent[];
    refusal?: Extract<SimEvent, { type: 'techniqueRefused' }>;
  };

  /**
   * 技のボタンを長押ししてしきい値に届いた瞬間。とくぎ。onTap を書かない動物では、押した瞬間にも
   * チキンがあればこちらを呼ぶ（原型の doAction）。
   *
   * とくぎはチキンを拾って溜めた回数ぶんだけ使える。回数の管理は
   * 呼び出し側が行うので、ここでは効果だけを書く。自分の振る舞いの最中にも呼ばれるので、
   * 最中にどうするか（やり直す・何もしない）もここで決める。
   */
  readonly onHold?: (
    world: WorldState,
    player: PlayerState,
  ) => { action: ActiveAction | null; events: SimEvent[] };
}

/**
 * 動物の登録表。
 *
 * 追加は1行。既存のどのファイルも触らない。
 */
const REGISTRY = new Map<string, Ability>();

/** 動物を登録する。同じ識別子で2度登録すると止まる。 */
export function registerAbility(ability: Ability): void {
  if (REGISTRY.has(ability.key)) {
    throw new Error(`${ability.key} はすでに登録されている`);
  }
  REGISTRY.set(ability.key, ability);
}

/** 登録された能力を取得する。未登録なら undefined。 */
export function lookupAbility(key: string): Ability | undefined {
  return REGISTRY.get(key);
}

/** 登録されている動物の識別子を、登録した順で返す。 */
export function registeredAnimals(): string[] {
  return [...REGISTRY.keys()];
}

/** 既定の数値。書かなかった項目はこの値になる。 */
export const NEUTRAL_ABILITY = {
  speedMultiplier: 1,
  powerBonus: 0,
  hpBonus: 0,
  bombBonus: 0,
  itemMultiplier: 1,
} as const;
