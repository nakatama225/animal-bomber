/**
 * キャラ選びの画面に出すキーの案内（原型の `KEYHINT`。L1151-1158）。
 *
 * 原型の文を写した固定の文。キーの割り当ての表（`platform/Keyboard.ts`）からは作らない。原型の案内は、
 * 割り当てた全部のキーを書かない（J と Option は書かない）。
 */

/**
 * 1人で遊ぶとき（原型の `KEYHINT.solo`。L1154-1155）。
 *
 * 🎮 の部分はパッドが無くても出す（原型の注記 L1152-1153。消えると、このゲームがパッドに
 * 対応しているのかを知る場所が無くなる）。
 */
export const KEY_HINT_SOLO =
  'WASD か 矢印キー ／ 爆弾 Space・Enter・Z・/ ／ 技 E・Q・X・C・R・K・Shift・.・,（長押しでとくぎ）' +
  ' ／ 🎮パッド: 十字かスティック・爆弾 A/R1・技 B/X/Y/L1（長押しでとくぎ）';

/** 2人で遊ぶときの 1P（原型の `KEYHINT.p1`。L1156）。 */
export const KEY_HINT_P1 = 'WASD ／ 爆弾 Space か Z ／ 技 E・Q・X・C・R・左Shift（長押しでとくぎ）';

/** 2人で遊ぶときの 2P（原型の `KEYHINT.p2`。L1157）。 */
export const KEY_HINT_P2 = '矢印キー ／ 爆弾 Enter か /(め) ／ 技 右Shift・.・,・M・N（長押しでとくぎ）';

/**
 * 動物を選ぶ人間ごとの案内（1P から順）。1人なら1人用の1つ、2人なら 1P と 2P の2つ
 * （原型 L5998-6000）。
 */
export function keyHintsFor(humans: number): readonly string[] {
  return humans === 1 ? [KEY_HINT_SOLO] : [KEY_HINT_P1, KEY_HINT_P2];
}
