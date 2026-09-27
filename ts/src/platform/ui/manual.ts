import { ANIMAL_LOOKS } from '../../content/animals.js';
import { abilityOf } from '../../domain/abilities/registry.js';
import { TICKS_PER_SECOND } from '../../domain/core/Tick.js';
import { ITEM_DEFINITIONS } from '../../domain/rules/items.js';
import { GAMEPAD_HELP, keyHelpFor, menuHelp } from '../keyHelp.js';
import { PLAYER1_KEYS, PLAYER2_KEYS, SOLO_KEYS } from '../Keyboard.js';

/** 遊び方の説明の1節。 */
export interface ManualSection {
  readonly title: string;
  readonly lines: readonly string[];
}

/**
 * 遊び方の説明。
 *
 * キー・長押しの長さ・アイテムの一覧は、それぞれの表（キー配置・動物の能力・アイテムの定義）から作る。
 * 手で書き写すと、値を変えたときに説明だけ古いまま残る。
 */
export function describeManual(): ManualSection[] {
  return [
    {
      title: 'そうさ（1人で遊ぶとき・通信対戦）',
      lines: [...keyHelpFor('', SOLO_KEYS).lines, ...GAMEPAD_HELP],
    },
    {
      title: 'そうさ（1台で2人のとき）',
      lines: [
        ...keyHelpFor('', PLAYER1_KEYS).lines.map((line) => `1P ${line}`),
        ...keyHelpFor('', PLAYER2_KEYS).lines.map((line) => `2P ${line}`),
        'ゲームパッドは1人で遊ぶときだけ使える（1台に1人ぶん）',
      ],
    },
    {
      title: 'メニュー',
      lines: [menuHelp()],
    },
    {
      title: '技ととくぎ',
      lines: [
        '技のボタンをポンと押すと通常技、長押しで🍗とくぎ（チキンを拾うと使える）',
        ...ANIMAL_LOOKS.map((look) => {
          const ability = abilityOf(look.key);
          const tap = ability.onTap === undefined ? '（ポン押しの通常技は無い）' : '';
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
