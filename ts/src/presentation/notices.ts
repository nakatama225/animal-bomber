import { TICKS_PER_SECOND, type Tick } from '../domain/core/Tick.js';
import { SUDDEN_DEATH_HP, SUDDEN_DEATH_LENGTH } from '../domain/rules/suddenDeath.js';
import { MAX_BOMBS, MAX_POWER, MAX_SHOES } from '../domain/rules/tuning.js';
import { HOLE } from './hud/effectLabels.js';
import { hitsForHp } from './menu/choices.js';

/**
 * 画面の上に短く出す通知の文（原型の `toast` の 22 種）。
 *
 * 文は Python 版の `presentation/notices.py` と1字ずつ同じにしてある（Python 版は原型の `toast`・`flash` の
 * 呼び出しから写した）。差し込む所は関数の引数にしてある（原型の `${…}`）。
 *
 * 試合の中の 17 種は `Presenter.ts` が出す。
 *
 * - アイテム：バナナ・たまねぎ・チキン・うんこ（L1609・L1613・L1619・L1633）
 * - 葱ボン：外周へ回った・入れ替わった・外周が閉じた（L2269・L2354・L2362）
 * - 舌：焼き切れた・根元まで焼けた舌を出そうとした・1マス戻った（L2488・L2498・L4307）
 * - 穴ととくぎ：穴を掘り終えた・穴にはまった・とくぎを使った（L2575・L2597・L2611）
 * - 体当たりと鼻水：吸い込んだ・押しつけた・鼻水で消した（L2818・L2880・L3036）
 * - 延長戦に入った（L4463）
 *
 * 試合の外の5種（パッドが対応していない・パッドを認識した・中継との接続が切れた・ホストが抜けた・
 * CPU が引き継いだ。L3498・L3527・L3735・L3787・L3793）は、画面の流れを実行する側が出す。
 * ホストが抜けた通知は、ロビーでホストが抜けたときだけ出す（この版の通信対戦は、試合の最中に
 * ホストが抜けても CPU が引き継いで続く）。
 *
 * 呼び方は、L2354 だけが原型の `label`（人間は「1P」、CPU は動物の名前。通信対戦で抜けて CPU に
 * 替わったプレイヤーは、人間だったときの「2P」のまま。`hud/roster.ts` の `labelOf`）で、ほかは動物の
 * 名前（原型の `p.animal.name`）。どちらで呼ぶかは出す側（`Presenter.ts`）が決める。
 */

/** 効果が2倍になる動物の、アイテムの通知の末尾（原型の `bonus`。L1603）。 */
export const DOUBLED = '（2倍！）';

/** 残り時間が短くなって外周が閉じた（原型 L2362）。 */
export const LANES_CLOSED = '🌿 葱ボン 退場！ もう復活できない';

/**
 * 残っていた全員が同じ tick に倒れた、という理由（原型 L4419・L4420）。
 *
 * 延長戦の通知と、ひきわけの幕（`hud/RoundBanner.ts`）で使う。
 */
export const ALL_DOWN = '同時にやられた';

/** 時間切れで2人以上残った、という理由（原型 L4429・L4430）。 */
export const TIME_UP = '時間切れ';

/** パッドを初めて認識した（原型 L3527。1回だけ出す）。 */
export const PAD_FOUND = '🎮 コントローラーを認識しました';

/** 中継との接続が切れた（原型 L3735）。 */
export const SERVER_LOST = 'サーバとの接続が切れました';

/** ホストが抜けた（原型 L3787）。 */
export const HOST_LOST = 'ホストとの接続が切れました';

/** アイテムの通知の末尾。効果の倍率 `times` が 1 より大きければ付ける。 */
export function doubled(times: number): string {
  return times > 1 ? DOUBLED : '';
}

/** バナナで滑り始めた（原型 L1609）。`times` は効果がかかる側の動物の、効果の倍率。 */
export function slipped(name: string, times: number): string {
  return `🍌 ${name} すべる！${doubled(times)}`;
}

/** たまねぎで泣き始めた（原型 L1613）。 */
export function cried(name: string, times: number): string {
  return `🧅 ${name} 涙で動けない！${doubled(times)}`;
}

/**
 * チキンを拾った（原型 L1619）。`special` はとくぎの名前、`times` は1つで溜まる回数。
 *
 * 2回ぶん溜まる動物だけ、空白とかける記号で回数を添える（原型の `` ` ×${M}` ``）。
 */
export function chickenTaken(name: string, special: string, times: number): string {
  return `🍗 ${name} とくぎ「${special}」${times > 1 ? ` ×${times}` : ''}！`;
}

/** うんこを踏んで状態がかかった（原型 L1633）。`label` は状態の名前。 */
export function pooped(name: string, label: string, times: number): string {
  return `💩 ${name} ${label}！${doubled(times)}`;
}

/** 盤面で倒れて外周へ回った（原型 L2269。人間のプレイヤーだけに出す）。 */
export function toLane(name: string): string {
  return `🌿 ${name} は葱ボンへ！ 外周から葱を撃って復活をねらえ`;
}

/** 葱が当たって入れ替わった（原型 L2354）。呼び方は原型の `label`（`hud/roster.ts` の `labelOf`）。 */
export function revived(shooter: string, victim: string): string {
  return `🌿 ${shooter} 復活！ ${victim} が葱ボンへ`;
}

/** 伸ばしていた舌が爆風に触れた（原型 L2488）。`reach` は焼けたあとの長さ。 */
export function tongueBurnt(name: string, reach: number): string {
  return `👅🔥 ${name} の舌が焼き切れた！このラウンドは ${reach}マスまで`;
}

/**
 * 根元まで焼けた舌を出そうとした（原型 L2498）。`wait` は1マス戻るまでの残り。
 *
 * 秒は切り上げる（原型の `Math.ceil(p.tongueRegen)`）。
 */
export function tongueGone(name: string, wait: Tick): string {
  return `👅🔥 ${name} の舌は焼け落ちてる（${ceilSeconds(wait)}秒で1マス戻る）`;
}

/** 焼けた舌が1マス戻った（原型 L4307）。`reach` は戻ったあとの長さ。 */
export function tongueRegrown(name: string, reach: number): string {
  return `👅 ${name} の舌が1マス回復（${reach}マス）`;
}

/** 穴を掘り終えた（原型 L2575）。 */
export function pitDug(name: string): string {
  return `${HOLE} ${name} 落とし穴をしかけた`;
}

/** 穴にはまった（原型 L2597）。`hold` は動けない長さ。秒は切り上げる。 */
export function pitFallen(name: string, hold: Tick): string {
  return `${HOLE} ${name} 落とし穴！ ${ceilSeconds(hold)}秒うごけない`;
}

/** とくぎを使った（原型 L2611）。`emoji` と `special` は、とくぎの絵文字と名前。 */
export function specialUsed(emoji: string, name: string, special: string): string {
  return `${emoji} ${name} ${special}！`;
}

/** 体当たりで進む間に、通り道の良いアイテムを取った（原型 L2818。`emoji`・`label` はアイテムの）。 */
export function swept(emoji: string, name: string, label: string): string {
  return `${emoji} ${name} 突進で ${label} を吸い込んだ！`;
}

/** 体当たりで、抱えていた悪いアイテムを相手に押しつけた（原型 L2880）。 */
export function pushed(name: string, target: string, count: number): string {
  return `💥 ${name} が ${target} に ${count}個 ぶつけた！`;
}

/**
 * 鼻水で何か消した（原型 L3034-3036）。何も消さなければ null（原型も出さない）。
 *
 * @param doused 火を消した爆弾の数
 * @param washed 流したうんこの数
 */
export function sprayed(name: string, doused: number, washed: number): string | null {
  const parts: string[] = [];
  if (doused > 0) parts.push(`爆弾${doused}個の火を消した`);
  if (washed > 0) parts.push(`うんこ${washed}個を流した`);
  if (parts.length === 0) return null;
  return `💧 ${name} 鼻水で ${parts.join('・')}！`;
}

/** 延長戦に入ったわけの呼び方。 */
export function reasonText(reason: 'allDown' | 'timeUp'): string {
  return reason === 'allDown' ? ALL_DOWN : TIME_UP;
}

/**
 * 延長戦に入った（原型 L4463）。
 *
 * 体力・爆弾・火力・靴・長さは、延長戦の決まり（`domain/rules/suddenDeath.ts`・`tuning.ts`）から作る。
 * 原型の文は上限の値を差し込んでいる（`BOMB_MAX` など）ので、値を変えれば文も変わる。体力は爆風何回
 * ぶんかで書く（原型の HP は爆風1回で1減る）。
 */
export function suddenDeath(reason: 'allDown' | 'timeUp'): string {
  return (
    `⚡ サドンデス！（${reasonText(reason)}） 全員HP${hitsForHp(SUDDEN_DEATH_HP)}・` +
    `💣${MAX_BOMBS}・🔥${MAX_POWER}・👟${MAX_SHOES}・${ceilSeconds(SUDDEN_DEATH_LENGTH)}秒`
  );
}

/** ボタンの並びが標準でないパッドをつないだ（原型 L3498。1回だけ出す）。`pad` はパッドの名前（原型の `gp.id`）。 */
export function padUnsupported(pad: string): string {
  return `🎮 このコントローラーには対応していません（${pad}）`;
}

/** 抜けたプレイヤーを CPU が引き継いだ（原型 L3793）。`name` は動物の名前。 */
export function cpuTookOver(name: string): string {
  return `${name} の回線が切れた → CPU が引き継ぐ`;
}

/** tick を秒にする。端数は切り上げる。 */
export function ceilSeconds(ticks: number): number {
  return Math.ceil(ticks / TICKS_PER_SECOND);
}
