import type { Direction, Point } from '../core/Coord.js';
import type { ActiveAction } from '../abilities/ActiveAction.js';
import type { PlayerInput } from '../input/PlayerInput.js';
import type { Tile } from './Board.js';
import type { EffectBag } from './EffectBag.js';
import type { Life } from './Life.js';
import type { Tick } from '../core/Tick.js';
import {
  BASE_SPEED,
  IN_BLOCK_SPEED_RATIO,
  MAX_SPEED,
  MIN_SPEED,
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
 * 偶数丸めなので、小数を丸める処理を加えると言語をまたいで結果が食い違う。
 * 整数で持てばその問題そのものが起きない。
 */
export interface PlayerState {
  readonly id: PlayerId;
  /** 動物の種類。content 層のデータを参照するための鍵。 */
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

  /**
   * とくぎを持っているか（原型の chicken）。チキンを拾うと立ち、回数を使い切るか外周へ回ると外れる。
   * とくぎを出せるかはこちらで見る（原型の doAction L2445・doSpecial L2455 も chicken を見る）。
   *
   * ⚠️ 回数（`specialCharges`）とは別に持つ。外周へ回ると、原型の toNegibon（L2255）と同じく、持っている印だけが
   * 外れて回数は残る。残った回数では出せず、次にチキンを拾うと足される（原型の applyItem L1616-1617）。
   */
  hasSpecial: boolean;

  /**
   * 溜めてあるとくぎの回数（原型の chickenCharges）。チキンを拾うと増え、とくぎを出すと1つ減る。
   * 持っている印（`hasSpecial`）が外れている間も残ることがある（外周へ回ったとき）。
   */
  specialCharges: number;

  /**
   * いまプレイヤーを乗っ取っている振る舞い。無ければ null。
   *
   * 突進や穴掘りのように、始まってから終わるまでそのプレイヤーの操作を
   * 受け付けないもの。各 System はこの中身の種類を見ず、
   * `drivesMovement` などの性質だけを見る。
   */
  action: ActiveAction | null;

  /** 技のボタンを押し続けている長さ。長押しのとくぎの判定に使う。離すと 0 に戻る。 */
  actionHeld: Tick;

  /**
   * いまの押し方で、とくぎを出そうとし終えたか（原型の actFired）。離すと false に戻る。
   *
   * しきい値に届いた tick に立てる。動けなかった・チキンが無かった・技のボタンを受け付けない
   * 振る舞いの最中だった、で何も出なくても立てるので、その押し方のとくぎはそれきりになる
   * （あとからチキンを拾っても出ない）。
   * ラウンドの始まりは true で始まる。押したまま始まった人は、一度離すまでとくぎが出ない。
   */
  actionFired: boolean;

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
  button: 'bomb' | 'action' | 'special',
): boolean {
  return playerInput[button] && !player.previousInput[button];
}

/**
 * そのプレイヤーの、1 tick あたりの移動距離（マス）。原型の getSpeed と同じ順で出す。
 *
 * 1. 足の速さ（動物の倍率）と靴の段数ぶんを足す
 * 2. 「超スロー」の倍率を掛ける
 * 3. 「とまれない」なら下限を敷く
 * 4. 壊せるブロックの中（壁の中も）にいれば、1. を `IN_BLOCK_SPEED_RATIO` 倍したものに
 *    置き換え、「超スロー」だけを掛け直す（「とまれない」は適用されない）
 * 5. 最後に下限（`MIN_SPEED`）と上限（`MAX_SPEED`）で挟む
 *
 * ⚠️ 上限で止めるのは最後。先に止めると、靴で上限を超えるほど速い動物が「超スロー」を
 * 踏んだとき、原型より遅くなる（靴 12 段のうさぎで、原型 4.01・先に止めると 3.95 マス/秒）。
 *
 * @param standingOn 体の中心があるマス。移動を始める前のマスを渡す（原型も移動の前に測る）
 */
export function speedOf(
  player: PlayerState,
  animalMultiplier = 1,
  standingOn: Tile = 'empty',
): number {
  const legs = BASE_SPEED * animalMultiplier + player.shoes * SHOE_STEP;
  const slow = player.effects.has('slow');
  let speed = legs;
  if (slow) speed *= SLOW_FACTOR;

  // ⚠️ 「とまれない」は速度に下限を敷く効果。下限に「超スロー」の倍率を
  // かけないと、超スローを踏んだあとにこれを踏んだ人が速くなるという
  // 逆転が起きる。後から踏んだ悪い状態が前のものを打ち消してしまう。
  if (player.effects.has('runaway')) {
    const floor = MAX_SPEED * RUNAWAY_SPEED_FLOOR_RATIO * (slow ? SLOW_FACTOR : 1);
    speed = Math.max(speed, floor);
  }

  if (standingOn !== 'empty') {
    speed = legs * IN_BLOCK_SPEED_RATIO;
    if (slow) speed *= SLOW_FACTOR;
  }
  return Math.min(MAX_SPEED, Math.max(MIN_SPEED, speed));
}

/** そのプレイヤーがいま置く爆弾の火力。 */
export function powerOf(player: PlayerState): number {
  if (player.effects.has('weak')) return WEAKENED_POWER;
  return player.power;
}

/**
 * 盤面の上で戦っているか。
 *
 * 外周にいるプレイヤーと退場したプレイヤーは、爆風で傷を受けず、拾い物にも関わらない（盤面を離れても止めて
 * 残した振る舞いだけは、爆風に触れると焼ける。`ActiveAction.staysOffBoard`）。
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
 * - 落とし穴にはまっている。⚠️ 泣いている（たまねぎ）だけなら置ける。動けない2つ（泣く・はまる）の
 *   うち、原型の canPlaceBomb が見るのは落とし穴だけで、ここを `isFrozen` にすると、泣いている間に
 *   置けなくなる
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

/**
 * 被弾のあとの無敵（点滅している間）か。爆風・追いかける炎・体当たり・葱のどれも当たらない。
 *
 * 技による「当たらない」は別に2つある（`isBlastProof`・`isUntouchable`）。原型も3つを分けていた。
 */
export function isInvulnerable(player: PlayerState, now: Tick): boolean {
  return now < player.invulnerableUntil;
}

/**
 * 爆風・追いかける炎・体当たりの傷が当たらないか（原型の isBlastProof）。跳び上がっている間（'leap'）だけ。
 *
 * ⚠️ 受ける傷に上限がある振る舞い（`ActiveAction.damageCap`。体当たりの最中）は入れない。その振る舞いは
 * 「止まらないが傷は入る」（上限つき）で、爆風にも追いかける炎にも、ほかの体当たりにも当たる。
 */
export function isBlastProof(player: PlayerState): boolean {
  return player.effects.has('leap');
}

/**
 * 葱が当たらないか（原型の isUntouchable）。跳び上がっている間と、葱が当たらない振る舞いの最中
 * （`ActiveAction.untouchable`）。
 */
export function isUntouchable(player: PlayerState): boolean {
  return player.effects.has('leap') || player.action?.untouchable === true;
}

/** 状態を複製する。試算に使う。 */
export function clonePlayer(player: PlayerState): PlayerState {
  return { ...player, position: { ...player.position }, effects: player.effects.clone() };
}
