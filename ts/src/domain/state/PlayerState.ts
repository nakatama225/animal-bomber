import type { Direction, Point } from '../core/Coord.js';
import type { ActiveAction } from '../abilities/ActiveAction.js';
import type { PlayerInput } from '../input/PlayerInput.js';
import type { EffectBag } from './EffectBag.js';
import type { Life } from './Life.js';
import type { Tick } from '../core/Tick.js';
import {
  BASE_SPEED,
  MAX_SPEED,
  RUNAWAY_SPEED_FLOOR_RATIO,
  SHOE_STEP,
  SLOW_FACTOR,
  WEAKENED_POWER,
} from '../rules/tuning.js';

/** プレイヤー番号。0 から 3。 */
export type PlayerId = 0 | 1 | 2 | 3;

/** すべてのプレイヤー番号を、いつも同じ順で並べたもの。 */
export const PLAYER_IDS: readonly PlayerId[] = [0, 1, 2, 3];

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

  /** 盤面で戦っているか・外周にいるか・退場したか。変えるときは丸ごと差し替える。 */
  life: Life;
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
   * 突進や穴掘りのように、始まってから終わるまでそのプレイヤーの操作を
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
   * 「勝手に設置」が次に爆弾を置こうとするまでの残り。間隔は `AUTOBOMB_INTERVAL`。
   *
   * 状態がかかっている間だけ減る。0 に戻すのはラウンドの始まりだけで、延長戦では戻さない
   * （原型と同じ）。
   */
  autobombWait: Tick;

  /**
   * 最後に自分を傷つけた相手。自分の爆弾なら自分のプレイヤー番号が入る。
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
  previousInput: PlayerInput;
}

/** そのボタンをこの tick に押し下げたか（押しっぱなしは含まない）。 */
export function justPressed(
  player: PlayerState,
  playerInput: PlayerInput,
  button: 'bomb' | 'action',
): boolean {
  return playerInput[button] && !player.previousInput[button];
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

/**
 * 盤面の上で戦っているか。
 *
 * 外周にいるプレイヤーと退場したプレイヤーは、爆風にも拾い物にも関わらない。
 * 盤面の処理は、ほぼすべてこの判定から始まる。
 */
export function isAlive(player: PlayerState): boolean {
  return player.life.kind === 'alive';
}

/**
 * 動けない状態か。泣いている（たまねぎ）か、落とし穴にはまっている。
 *
 * 動けない間は、歩けず、技も出せない（原型の isFrozen と同じく2つとも見る）。
 */
export function isFrozen(player: PlayerState): boolean {
  return player.effects.has('stun') || player.effects.has('pitfall');
}

/**
 * いま爆弾を置ける状態か。ボタン・「勝手に設置」・技で並べる爆弾の、どれもがここを通る。
 *
 * 置けないのは3つ。
 *
 * - 落とし穴にはまっている。⚠️ 泣いている（たまねぎ）だけなら置ける。原型の canPlaceBomb が
 *   見るのは落とし穴だけで、ここを `isFrozen` にすると、泣いている間に置けなくなる
 * - 乗っ取り中の振る舞いが置けない形（`ActiveAction.canPlaceBomb`）
 * - 「爆弾おけない」がかかっていて、「勝手に設置」がかかっていない。⚠️ 2つが重なったら
 *   「勝手に設置」が勝つ。どちらが勝つかを決めておかないと、組み合わせで挙動が読めなくなる
 *   （原型では、素直に書くと勝手に設置が完全に死に、2つ踏んでも損をしなかった）
 *
 * 手持ちの数・マスが空いているか・爆弾が既にあるかは、置く場所の話なので `placeBombAt` が見る。
 */
export function canPlaceBomb(player: PlayerState): boolean {
  if (player.effects.has('pitfall')) return false;
  if (player.action !== null && !player.action.canPlaceBomb) return false;
  return !player.effects.has('nobomb') || player.effects.has('autobomb');
}

/** 無敵の最中か。 */
export function isInvulnerable(player: PlayerState, now: Tick): boolean {
  return now < player.invulnerableUntil;
}

/** 状態を複製する。試算に使う。 */
export function clonePlayer(player: PlayerState): PlayerState {
  return { ...player, position: { ...player.position }, effects: player.effects.clone() };
}
