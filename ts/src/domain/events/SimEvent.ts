import type { Cell, Direction, Point } from '../core/Coord.js';
import type { PlayerId } from '../state/PlayerState.js';
import type { EffectKind } from '../state/EffectBag.js';
import type { ItemKind } from '../rules/items.js';

/**
 * 技の途中で起きたことの種類（`techniqueMoment` のイベント）。
 *
 * - `tongueCaught` … 舌がアイテムを掴んだ
 * - `digStarted` … 穴を掘り始めた（掘れないマスでとくぎを使ったときは知らせない）
 * - `pitDug` … 穴を掘り終えた
 * - `slimeHopped` … 跳ね回る爆弾が跳ねた（跳べずにその場に留まったときも）
 * - `itemsSpat` … 体当たりで抱えていた悪いアイテムを、止まった所の左右へ撒き散らした
 * - `rammed` … 体当たりが相手に当たった
 * - `chaserCast` … 追いかける炎を放った（盤面に相手がいなくて出さなかったときは知らせない）
 * - `chaserHit` … 追いかける炎が相手に当たった
 *
 * 名前は動物ではなく技の働きで付ける。この型はどの動物も使う共通の型なので、
 * 動物の名前を入れると、動物を足すたびに共通の型の意味が動物に縛られる。
 */
export type TechniqueMoment =
  | 'tongueCaught'
  | 'digStarted'
  | 'pitDug'
  | 'slimeHopped'
  | 'itemsSpat'
  | 'rammed'
  | 'chaserCast'
  | 'chaserHit';

/**
 * 試合の中で起きたイベント。
 *
 * 「爆弾が置かれた」「ブロックが壊れた」「誰かが倒れた」といった、
 * 1 tick の中で実際に起きたことを1件ずつ表す。
 *
 * ## なぜ戻り値なのか
 *
 * 原型では `update()` の中から効果音（53 箇所）・画面の書き換え（17 箇所）・
 * 通知の表示（17 箇所）を直接呼んでいた。そのため、画面を描かずに
 * ルールだけを動かす方法が無かった。CPU の強さを1万試合で測ろうとすると、
 * 音を鳴らしながら実時間で回すことになる。
 *
 * この版では、ルールの層は**起きたイベントを配列で返すだけ**にする。
 * 音を鳴らすか、画面を光らせるか、何もしないかは受け取った側が決める。
 *
 * ```
 * const events = simulation.step(world, playerInputs);
 * presenter.consume(events);   // 画面と音
 * // 検証のときは consume しない。それだけで無音・無描画になる
 * ```
 *
 * 「音を消すフラグ」も「テスト用のモード」も要らない。**呼ばなければ
 * 起きない**、が構造で保証される。
 *
 * ## なぜ判別可能ユニオンなのか
 *
 * `type` の値で分岐すると、型検査が「まだ扱っていない種類」を見つける。
 * イベントを1種類足して対応を書き忘れると、書き忘れた分岐の
 * `assertNever` で型検査が失敗する（`Presenter` を参照）。
 */
export type SimEvent =
  | { readonly type: 'bombPlaced'; readonly cell: Cell; readonly owner: PlayerId }
  | {
      readonly type: 'exploded';
      readonly cell: Cell;
      readonly owner: PlayerId;
      /** 連鎖した爆弾の数。多いほど大きな音を鳴らす。 */
      readonly chained: number;
    }
  | { readonly type: 'blockDestroyed'; readonly cell: Cell }
  | { readonly type: 'itemDropped'; readonly cell: Cell; readonly kind: ItemKind }
  | {
      readonly type: 'itemTaken';
      readonly cell: Cell;
      readonly kind: ItemKind;
      readonly taker: PlayerId;
    }
  | { readonly type: 'itemBurned'; readonly cell: Cell; readonly kind: ItemKind }
  /** 撒かれたアイテムが、残る長さを過ぎて消えた（`Item.expiresAt`）。 */
  | { readonly type: 'itemExpired'; readonly cell: Cell; readonly kind: ItemKind }
  /** 流されて溶けていたアイテムが、溶けきって消えた（`Item.meltingUntil`）。 */
  | { readonly type: 'itemWashed'; readonly cell: Cell; readonly kind: ItemKind }
  /** 爆弾の火が消されて、爆弾ごと消えた。置いたプレイヤーの手持ちは戻る。 */
  | { readonly type: 'bombDoused'; readonly cell: Cell; readonly owner: PlayerId }
  /**
   * 正面のマスへ水を吹きかけた（見た目のための知らせ）。届いたマスを手前から順に運ぶ。
   * 柱の手前で止まったマスは入らない。壊せるブロックのマスは入る（そこで止まる）。
   */
  | {
      readonly type: 'sprayed';
      readonly player: PlayerId;
      readonly cells: readonly Cell[];
      readonly facing: Direction;
    }
  | {
      readonly type: 'effectApplied';
      readonly target: PlayerId;
      readonly effect: EffectKind;
    }
  | {
      readonly type: 'playerHurt';
      readonly target: PlayerId;
      /** 倒した相手。自爆なら自分自身のプレイヤー番号が入る。 */
      readonly by: PlayerId | null;
      /** 減った体力（半分の単位）。 */
      readonly amount: number;
    }
  | {
      readonly type: 'playerDown';
      readonly target: PlayerId;
      readonly by: PlayerId | null;
      /**
       * 倒れた位置。
       *
       * ⚠️ 受け取った側は、プレイヤーのいまの位置を読まずにこちらを使う。同じ tick の
       * うちに延長戦へ入ると、受け取る頃には開始位置へ移っている。
       */
      readonly at: Point;
    }
  | {
      readonly type: 'techniqueUsed';
      readonly player: PlayerId;
      /** 長押しのとくぎか。false なら押して離す通常技。 */
      readonly special: boolean;
    }
  | {
      /**
       * 技の途中で起きたこと。音を鳴らすのに使う（原型は、それぞれの瞬間に専用の音を鳴らしていた）。
       *
       * ⚠️ どのマスかは運ばない。掘り終えた穴の位置を描画の側に渡すと、見えないはずの穴がばれる。
       */
      readonly type: 'techniqueMoment';
      /** 技を使ったプレイヤー。 */
      readonly player: PlayerId;
      readonly moment: TechniqueMoment;
    }
  | {
      readonly type: 'leekThrown';
      /** 撃った葱ボン。 */
      readonly player: PlayerId;
      /** 撃った位置。外周の帯の上なので、盤面の外にある。 */
      readonly from: Point;
      readonly facing: Direction;
    }
  | {
      readonly type: 'leekStopped';
      readonly cell: Cell;
      /** 何で止まったか。柱かブロック・爆風・爆弾・射程切れ。 */
      readonly by: 'wall' | 'blast' | 'bomb' | 'range';
    }
  | {
      readonly type: 'revived';
      /** 葱を当てて盤面へ戻ったプレイヤー。 */
      readonly player: PlayerId;
      /** 葱が当たって外周へ回ったプレイヤー。 */
      readonly replaced: PlayerId;
      /** 入れ替わった位置。戻ったプレイヤーはここに立つ。 */
      readonly at: Point;
    }
  | {
      readonly type: 'lanesClosed';
      /** 外周から退場したプレイヤー。 */
      readonly players: readonly PlayerId[];
    }
  | {
      readonly type: 'suddenDeath';
      /** 延長戦に入ったわけ。全員が同じ tick に倒れたか、時間切れか。 */
      readonly reason: 'allDown' | 'timeUp';
      /** 延長戦に加わるプレイヤー。 */
      readonly players: readonly PlayerId[];
    }
  | {
      readonly type: 'roundEnded';
      readonly round: number;
      /** 引き分けなら null。 */
      readonly winner: PlayerId | null;
    }
  | {
      readonly type: 'matchEnded';
      /** 引き分けで終わった場合は null。 */
      readonly champion: PlayerId | null;
    };

/**
 * 扱い漏れを型検査で見つけるための仕掛け。
 *
 * すべての種類を処理したあとに呼ぶ。新しいイベントを `SimEvent` へ足すと、
 * そこへ到達しうるようになるため `never` に代入できず、
 * コンパイルエラーになる。
 */
export function assertNever(value: never): never {
  throw new Error(`扱っていないイベント: ${JSON.stringify(value)}`);
}
