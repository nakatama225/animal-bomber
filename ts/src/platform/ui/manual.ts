import { ANIMAL_LOOKS } from '../../content/animals.js';
import { abilityOf } from '../../domain/abilities/registry.js';
import { TICKS_PER_SECOND } from '../../domain/core/Tick.js';
import { ITEM_DEFINITIONS } from '../../domain/rules/items.js';
import { KEY_HINT_P1, KEY_HINT_P2, KEY_HINT_SOLO } from '../../presentation/menu/keyHints.js';
import { menuHelp, PAD_MENU_HELP } from '../keyHelp.js';

/** 遊び方の説明の1節。 */
export interface ManualSection {
  readonly title: string;
  readonly lines: readonly string[];
}

/**
 * 遊び方の説明。
 *
 * 長押しの長さ・アイテムの一覧・メニューのキーは、それぞれの表（動物の能力・アイテムの定義・メニューの操作）から作る。
 * 手で書き写すと、値を変えたときに説明だけ古いまま残る。試合のキーは、キャラ選びと同じ原型の固定の文
 * （`presentation/menu/keyHints.ts`。原型の案内は割り当てた全部のキーを書かない）。
 */
export function describeManual(): ManualSection[] {
  return [
    {
      title: 'そうさ（1人で遊ぶとき・通信対戦）',
      lines: [KEY_HINT_SOLO],
    },
    {
      title: 'そうさ（1台で2人のとき）',
      lines: [`1P ${KEY_HINT_P1}`, `2P ${KEY_HINT_P2}`, 'ゲームパッドは1人で遊ぶときだけ使える（1台に1人ぶん）'],
    },
    {
      title: 'メニュー',
      lines: [menuHelp(), PAD_MENU_HELP, '通信対戦のロビーでは、戻るは効かない（ぬけるときは「← ぬける」を押す）'],
    },
    {
      title: '技ととくぎ',
      lines: [
        '技のボタンを押すと通常技、そのまま長押しで🍗とくぎ（チキンを拾うと使える。押した瞬間の通常技も出る）',
        ...ANIMAL_LOOKS.map((look) => {
          const ability = abilityOf(look.key);
          // 通常技の無い動物は、押した瞬間にとくぎが出る（ゲームの側の決まり。ActionSystem）。
          const tap = ability.onTap === undefined ? '（通常技は無く、押すとすぐとくぎが出る）' : '';
          return `${look.emoji}${look.name}：とくぎ「${look.special.name}」は ${seconds(ability.holdTicks)} 秒の長押し${tap}`;
        }),
        'P キーか「ポーズ」ボタンで止める（1台で遊ぶときだけ）',
      ],
    },
    {
      title: 'アイテム',
      lines: [
        ITEM_DEFINITIONS.map((item) => `${item.emoji}${item.label}`).join(' ／ '),
        'ブロックを壊すと出る。爆風に当たると焦げて消える',
        '爆風に当たると、パワーアップを1つ近くに吐き出す（誰でも拾える）',
      ],
    },
    {
      title: '🌿 葱ボン',
      lines: [
        '倒れると盤面の外周に出る。外周を動いて葱を撃ち、盤面の人に当てると入れ替わって戻れる',
        '残り1分で葱ボンは退場する。盤面に1人だけ残った時点で、そのラウンドは決まる',
        '葱は爆風で焼け、爆弾に当たると弾かれる（爆弾が盾になる）',
      ],
    },
    {
      title: '⚡ サドンデス',
      lines: [
        '時間切れで2人以上残ったとき、または全員が同時に倒れたとき、1回だけ延長する（ルールの画面で切れる）',
        'ブロックが全部消え、全員が体力1つ・爆弾と火力と靴が最大になる',
      ],
    },
  ];
}

/** tick を秒にする（1.5 など）。 */
function seconds(ticks: number): string {
  return String(ticks / TICKS_PER_SECOND);
}
