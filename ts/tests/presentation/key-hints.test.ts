import { describe, expect, it } from 'vitest';

import { KEY_HINT_P1, KEY_HINT_P2, KEY_HINT_SOLO, keyHintsFor } from '../../src/presentation/menu/keyHints.js';

/**
 * キャラ選びのキーの案内（原型の `KEYHINT`。L1151-1158）。
 *
 * 期待する文は、Python 版の `presentation/menu/screens.py` の `KEYHINT_SOLO`・`KEYHINT_P1`・`KEYHINT_P2`
 * （原型の文を写したもの）を写した。
 */
describe('キャラ選びのキーの案内', () => {
  it('原型の文のまま（割り当てた J と Option は書かない）', () => {
    expect(KEY_HINT_SOLO).toBe(
      'WASD か 矢印キー ／ 爆弾 Space・Enter・Z・/ ／ 技 E・Q・X・C・R・K・Shift・.・,（長押しでとくぎ）' +
        ' ／ 🎮パッド: 十字かスティック・爆弾 A/R1・技 B/X/Y/L1（長押しでとくぎ）',
    );
    expect(KEY_HINT_P1).toBe('WASD ／ 爆弾 Space か Z ／ 技 E・Q・X・C・R・左Shift（長押しでとくぎ）');
    expect(KEY_HINT_P2).toBe('矢印キー ／ 爆弾 Enter か /(め) ／ 技 右Shift・.・,・M・N（長押しでとくぎ）');
  });

  it('1人なら1人用の1つ、2人なら 1P と 2P の2つ', () => {
    expect(keyHintsFor(1)).toEqual([KEY_HINT_SOLO]);
    expect(keyHintsFor(2)).toEqual([KEY_HINT_P1, KEY_HINT_P2]);
  });
});
