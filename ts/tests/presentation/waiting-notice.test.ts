import { describe, expect, it } from 'vitest';

import { WaitingNotice } from '../../src/presentation/hud/lanStatus.js';

describe('待ちの案内', () => {
  it('一瞬の待ちでは出さず、続いたら出す', () => {
    const notice = new WaitingNotice();
    for (let frame = 0; frame < 29; frame += 1) expect(notice.observe([2])).toEqual([]);
    expect(notice.observe([2])).toEqual([2]);
  });

  it('待ちが途切れたら数え直す', () => {
    const notice = new WaitingNotice();
    for (let frame = 0; frame < 29; frame += 1) notice.observe([1]);
    expect(notice.observe([])).toEqual([]);
    expect(notice.observe([1])).toEqual([]);
  });
});
