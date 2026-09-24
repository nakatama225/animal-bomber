import { describe, expect, it } from 'vitest';

import { Rng } from '../../src/domain/core/Rng.js';

/**
 * 乱数が決定的であることの確認。
 *
 * ここが崩れると、リプレイも通信対戦もバランス検証も同時に成立しなくなる。
 * この実装でいちばん下にある前提なので、最初に検査を置く。
 */
describe('Rng', () => {
  it('同じ種からは同じ並びが出る', () => {
    const a = new Rng(12345);
    const b = new Rng(12345);
    const left = Array.from({ length: 100 }, () => a.next());
    const right = Array.from({ length: 100 }, () => b.next());
    expect(left).toEqual(right);
  });

  it('違う種からは違う並びが出る', () => {
    const a = new Rng(1);
    const b = new Rng(2);
    const left = Array.from({ length: 20 }, () => a.next());
    const right = Array.from({ length: 20 }, () => b.next());
    expect(left).not.toEqual(right);
  });

  it('0 以上 1 未満に収まる', () => {
    const rng = new Rng(777);
    for (let i = 0; i < 10_000; i += 1) {
      const value = rng.next();
      expect(value).toBeGreaterThanOrEqual(0);
      expect(value).toBeLessThan(1);
    }
  });

  it('引いた回数を数えている', () => {
    const rng = new Rng(1);
    expect(rng.calls).toBe(0);
    rng.next();
    rng.int(10);
    rng.chance(0.5);
    expect(rng.calls).toBe(3);
  });

  it('int は上限を超えない', () => {
    const rng = new Rng(42);
    for (let i = 0; i < 1000; i += 1) {
      const value = rng.int(7);
      expect(value).toBeGreaterThanOrEqual(0);
      expect(value).toBeLessThan(7);
      expect(Number.isInteger(value)).toBe(true);
    }
  });

  it('range は指定した範囲に収まる', () => {
    const rng = new Rng(9);
    for (let i = 0; i < 1000; i += 1) {
      const value = rng.range(5, 9);
      expect(value).toBeGreaterThanOrEqual(5);
      expect(value).toBeLessThan(9);
    }
  });

  it('混ぜた結果が種ごとに決まる', () => {
    const source = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
    const a = [...source];
    const b = [...source];
    new Rng(2024).shuffle(a);
    new Rng(2024).shuffle(b);
    expect(a).toEqual(b);
    // 混ざっていること自体も確かめる。そのまま返していたら意味がない。
    expect(a).not.toEqual(source);
    // 要素が失われていないこと。
    expect([...a].sort((x, y) => x - y)).toEqual(source);
  });

  it('空の配列から選ぼうとしたら止まる', () => {
    expect(() => new Rng(1).pick([])).toThrow();
  });

  it('clone は元を進めずに同じ先を見られる', () => {
    const rng = new Rng(555);
    rng.next();
    const before = rng.state;

    const branch = rng.clone();
    const predicted = Array.from({ length: 5 }, () => branch.next());

    expect(rng.state).toBe(before); // 元は進んでいない
    const actual = Array.from({ length: 5 }, () => rng.next());
    expect(actual).toEqual(predicted);
  });

  it('clone は引いた回数を引き継がない', () => {
    const rng = new Rng(1);
    rng.next();
    rng.next();
    expect(rng.clone().calls).toBe(0);
  });
});
