import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

/**
 * 起動の入口（`main.ts`）が探す要素が、`index.html` にあるか。
 *
 * 入口は読み込んだ時点で画面を組み立て始めるので、テストから読み込めない。
 * 要素の名前だけを文字列で突き合わせる。名前を変えて片方を修正し忘れると、
 * ブラウザで開いた瞬間に「#… が見つからない」で止まる。
 */
function read(path: string): string {
  return readFileSync(new URL(path, import.meta.url), 'utf8');
}

describe('画面の要素', () => {
  it('入口が探す要素は、すべて index.html にある', () => {
    const html = read('../../index.html');
    const main = read('../../src/app/main.ts');
    const ids = new Set([...html.matchAll(/\sid="([^"]+)"/g)].map((match) => match[1]));
    const wanted = [...main.matchAll(/findElement\('([^']+)'/g)].map((match) => match[1]);

    expect(wanted.length).toBeGreaterThan(5);
    expect(wanted.filter((id) => !ids.has(id))).toEqual([]);
  });

  it('見た目の指定を読み込んでいる', () => {
    expect(read('../../index.html')).toContain('href="/src/style.css"');
  });
});
