import type { Direction, Point } from '../core/Coord.js';
import type { ActiveAction } from '../abilities/ActiveAction.js';
import type { PlayerIntent } from '../intent/PlayerIntent.js';
import type { EffectBag } from './EffectBag.js';
import type { Tick } from '../core/Tick.js';
import {
  BASE_SPEED,
  MAX_SPEED,
  RUNAWAY_SPEED_FLOOR_RATIO,
  SHOE_STEP,
  SLOW_FACTOR,
  WEAKENED_POWER,
} from '../rules/tuning.js';

/** プレイヤーの席番号。0 から 3。 */
export type PlayerId = 0 | 1 | 2 | 3;

/** すべての席番号を、いつも同じ順で並べたもの。 */
export const PLAYER_IDS: readonly PlayerId[] = [0, 1, 2, 3];

/** プレイヤーの生死。 */
export type LifeState = 'alive' | 'dead';

/**
 * プレイヤー1人ぶんの状態。
 *
 * ⚠️ 体力は**半分の単位を整数で**持つ。`2` が1個ぶんで、`1` が半分。
 * 小数で持たないのは、Python 版と揃えるためでもある。Python の `round` は
 * 偶数丸めなので、小数を丸める処理を入れると言語をまたいで結果が食い違う。
 * 整数で持てばその問題そのものが起きない。
 */
export interface PlayerState {
  readonly id: PlayerId;
  /** 動物の種類。content 層のデータを引くための鍵。 */
  readonly animal: string;

  /** 盤面上の位置（マス単位の連続座標）。 */
  position: Point;
  /** 向いている方向。爆風や技の向きに使う。 */
  facing: Direction;

  life: LifeState;
  /** 体力。半分の単位の整数で持つ。 */
  hp: number;

  /** 靴を取った段数。 */
  shoes: number;
  /** 爆風の届くマス数。 */
  power: number;
  /** 同時に置ける爆弾の数。 */
  maxBombs: number;
  /** いま盤面に出ている自分の爆弾の数。 */
  activeBombs: number;

  /** 無敵が切れる tick。それまでは被弾しない。 */
  invulnerableUntil: Tick;

  /** かかっている一時的な状態。 */
  readonly effects: EffectBag;

  /** 溜めてあるとくぎの回数。チキンを拾うと増える。 */
  specialCharges: number;

  /**
   * いまプレイヤーを乗っ取っている振る舞い。無ければ null。
   *
   * 突進や穴掘りのように、始まってから終わるまで本人の操作を
   * 受け付けないもの。各 System はこの中身の種類を見ず、
   * `drivesMovement` などの性質だけを見る。
   */
  action: ActiveAction | null;

  /** 技のボタンを押し続けている長さ。長押しのとくぎの判定に使う。 */
  actionHeld: Tick;

  /**
   * 通常技が次に使えるようになるまでの残り。
   *
   * 連打で押し切れる技に間隔を設けるためのもの。何の技かは
   * この値からは分からない。間隔の長さは動物ごとの実装が決める。
   */
  abilityCooldown: Tick;

  /**
   * 最後に自分を傷つけた相手。自分の爆弾なら自分の席番号が入る。
   *
   * ⚠️ 倒れた時点で改めて爆風の持ち主を引き直してはいけない。その頃には
   * 爆風が消えていることがあり、原因が分からなくなる。当たった瞬間に控える。
   */
  lastHitBy: PlayerId | null;

  /** 歩いた距離の合計。歩行の見た目にだけ使う。 */
  walked: number;

  /**
   * 前の tick に押していた内容。
   *
   * 「押した瞬間」を判定するために持つ。爆弾は押しっぱなしで連射せず、
   * 押し下げた最初の1回だけ置かれる。
   *
   * ⚠️ これを System 側の変数として持つと、記録から状態を復元したときに
   * 失われる。**状態の一部として持つ**ことで、リプレイと通信対戦で
   * 押した瞬間の判定まで一致する。
   */
  previousIntent: PlayerIntent;
}

/** そのボタンをこの tick に押し下げたか（押しっぱなしは含まない）。 */
export function justPressed(
  player: PlayerState,
  intent: PlayerIntent,
  button: 'bomb' | 'action',
): boolean {
  return intent[button] && !player.previousIntent[button];
}

/**
 * そのプレイヤーの、1 tick あたりの移動距離（マス）。
 *
 * 靴の段数だけ速くなり、上限で頭打ちになる。
 */
export function speedOf(player: PlayerState, animalMultiplier = 1): number {
  let speed = Math.min(MAX_SPEED, BASE_SPEED * animalMultiplier + player.shoes * SHOE_STEP);
  if (player.effects.has('slow')) speed *= SLOW_FACTOR;

  // ⚠️ 「とまれない」は速度に下限を敷く効果。下限に「超スロー」の倍率を
  // かけないと、超スローを踏んだあとにこれを踏んだ人が速くなるという
  // 逆転が起きる。後から踏んだ悪い状態が前のものを打ち消してしまう。
  if (player.effects.has('runaway')) {
    const floor =
      MAX_SPEED * RUNAWAY_SPEED_FLOOR_RATIO * (player.effects.has('slow') ? SLOW_FACTOR : 1);
    speed = Math.max(speed, floor);
  }
  return speed;
}

/** そのプレイヤーがいま置く爆弾の火力。 */
export function powerOf(player: PlayerState): number {
  if (player.effects.has('weak')) return WEAKENED_POWER;
  return player.power;
}

/** 動けない状態か。 */
export function isFrozen(player: PlayerState): boolean {
  return player.effects.has('stun');
}

/** 無敵の最中か。 */
export function isInvulnerable(player: PlayerState, now: Tick): boolean {
  return now < player.invulnerableUntil;
}

/** 状態を複製する。試算に使う。 */
export function clonePlayer(player: PlayerState): PlayerState {
  return { ...player, position: { ...player.position }, effects: player.effects.clone() };
}
