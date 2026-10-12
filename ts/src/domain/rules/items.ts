import { secondsToTicks, type Tick } from '../core/Tick.js';
import type { EffectKind } from '../state/EffectBag.js';

/**
 * 盤面に落ちるアイテムと、その効果。
 *
 * 出現の重みと効果の秒数は、遊んだうえで決めた値です。
 * **理由を値の横に残す**ことで、次に読んだ人が根拠のない数字として
 * 書き換えないようにしています。
 */

/** アイテムの種類。 */
export type ItemKind =
  /** 置ける爆弾が1つ増える。 */
  | 'bomb'
  /** 爆風が1マス伸びる。 */
  | 'fire'
  /** 速くなる。 */
  | 'shoe'
  /** 滑る。 */
  | 'banana'
  /** 涙で動けなくなる。 */
  | 'onion'
  /** とくぎが使えるようになる。 */
  | 'chicken'
  /** 悪い状態のどれかがランダムでかかる。 */
  | 'poop';

export interface ItemDefinition {
  readonly kind: ItemKind;
  /** 画面での見た目。ルールの層では使わないが、対応を1か所にまとめておく。 */
  readonly emoji: string;
  readonly label: string;
  /** 抽選の重み。大きいほど出やすい。 */
  readonly weight: number;
  /** 強くなる系か。被弾したときに吐き出す対象を選ぶのに使う。 */
  readonly powerUp: boolean;
  /** 拾うと損をするか。CPU が避ける判断に使う。 */
  readonly harmful: boolean;
}

/**
 * アイテムの一覧。
 *
 * 強くなる系（爆弾・火力・靴）を合わせて 69、損をする系を 23、
 * とくぎを 8 にしてある。強くなる系を厚くしているのは、
 * 序盤に弱いまま撃ち合いになると試合が長引くため。
 */
export const ITEM_DEFINITIONS: readonly ItemDefinition[] = [
  { kind: 'bomb', emoji: '💣', label: '爆弾+1', weight: 26, powerUp: true, harmful: false },
  { kind: 'fire', emoji: '🔥', label: '火力+1', weight: 26, powerUp: true, harmful: false },
  { kind: 'shoe', emoji: '👟', label: 'スピード+', weight: 17, powerUp: true, harmful: false },
  { kind: 'banana', emoji: '🍌', label: 'バナナ', weight: 8, powerUp: false, harmful: true },
  { kind: 'onion', emoji: '🧅', label: 'たまねぎ', weight: 7, powerUp: false, harmful: true },
  { kind: 'chicken', emoji: '🍗', label: 'チキン', weight: 8, powerUp: false, harmful: false },
  { kind: 'poop', emoji: '💩', label: 'うんこ', weight: 8, powerUp: false, harmful: true },
];

/** 種類から定義を引く。 */
export function itemDefinition(kind: ItemKind): ItemDefinition {
  const found = ITEM_DEFINITIONS.find((definition) => definition.kind === kind);
  if (found === undefined) throw new Error(`知らないアイテム: ${kind}`);
  return found;
}

/**
 * 抽選用に、重みのぶんだけ並べた一覧。
 *
 * 重みつきの抽選を「重みぶん複製した配列から1つ選ぶ」形にしているのは、
 * 乱数を引く回数が必ず1回になるため。累積和を走査する形にすると、
 * 実装によって引く回数が変わり、状態の突き合わせがずれる。
 */
export const ITEM_LOTTERY: readonly ItemKind[] = ITEM_DEFINITIONS.flatMap((definition) =>
  Array.from({ length: definition.weight }, () => definition.kind),
);

/** 被弾したときに吐き出す候補。 */
export const POWER_UP_KINDS: readonly ItemKind[] = ITEM_DEFINITIONS.filter(
  (definition) => definition.powerUp,
).map((definition) => definition.kind);

/**
 * 壊せるブロックからアイテムが出る確率。
 *
 * これより低いと、序盤に強くなる速度が落ちて試合が間延びする。
 */
export const DROP_CHANCE = 0.55;

/**
 * うんこを踏んだときにかかる悪い状態と、その秒数。
 *
 * ⚠️ 秒数は「きつい効果ほど短く、軽い効果ほど長く」で置いています。
 *
 * - 逃げる手段を奪うもの（`slow` / `runaway` / `autobomb`）がいちばん重いので短い
 * - 攻撃だけを止めるもの（`nobomb`）は逃げられるぶん軽いので長め
 * - `weak` は火力が落ちるだけで身の安全に関わらないのでいちばん長い
 */
export const POOP_EFFECTS: readonly { kind: EffectKind; label: string; seconds: number }[] = [
  { kind: 'reverse', label: 'そうさ反転', seconds: 5 },
  { kind: 'nobomb', label: '爆弾おけない', seconds: 6 },
  { kind: 'runaway', label: 'とまれない', seconds: 4 },
  { kind: 'weak', label: '爆風1マス', seconds: 8 },
  { kind: 'autobomb', label: '勝手に設置', seconds: 4 },
  { kind: 'slow', label: '超スロー', seconds: 4 },
];

/** 同じ悪い状態を重ねて踏んだときの、積み上げの上限（基本秒数の何倍まで）。 */
export const POOP_STACK_LIMIT = 3;

/**
 * 盤面に落ちたうんこが残る長さ（原型の POOP_LIFE 15 秒。理由の記録は無い）。
 *
 * 置いた tick から数えて、これを過ぎた tick に消える。爆風で吹き飛んだら、吹き飛んだ tick から
 * 数え直す（原型の blowPoop）。ほかのアイテムは消えない。とくぎで撒かれたうんこは別の長さ
 * （`abilities/rabbit/ScatterActor.ts`）。
 *
 * ⚠️ 原型は経過秒を小数で足し続けて「置いてから 15 秒より長い」かを比べるので、足し算の誤差で、
 * 置いた時刻によっては 900 tick 目に消える（測ると 900 と 901 が混ざる）。この版は 15 秒ちょうどを
 * 過ぎた 901 tick 目にそろえる（撒かれたうんこの 60 秒も同じ扱い）。
 */
export const POOP_LIFETIME: Tick = secondsToTicks(15);

/** バナナで滑る時間。 */
export const SLIDE_SECONDS = 3;
/** たまねぎで動けない時間。 */
export const STUN_SECONDS = 3;

/** 秒で書いた設定を tick に直す。 */
export function itemEffectTicks(seconds: number): Tick {
  return secondsToTicks(seconds);
}
