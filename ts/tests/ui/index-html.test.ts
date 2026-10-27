// @vitest-environment happy-dom
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

  it('試合の画面は、盤面と横の板を .stage に横に並べ、通知は #app の外に1つだけ置く（原型 L513-540・L567）', () => {
    // body の中身だけを template に読む（ページとして読むと、見た目の指定とスクリプトを取りに行く）。
    const body = read('../../index.html').match(/<body>([\s\S]*)<\/body>/)?.[1] ?? '';
    const template = document.createElement('template');
    template.innerHTML = body;
    const page = template.content;
    const stage = page.querySelector('#play > .stage');
    expect([...(stage?.children ?? [])].map((child) => child.className || `#${child.id}`)).toEqual(['board', '#side']);
    // 盤面に重ねるもの（幕・通信対戦の案内の帯）は、canvas と同じ包みに入れる。
    expect([...(stage?.querySelector('.board')?.children ?? [])].map((child) => child.id)).toEqual(['stage', 'banner', 'lan-status']);
    // 通知は body の直下（#app の外）。
    expect(page.querySelector('#toast')?.parentNode).toBe(page);
    expect(page.querySelectorAll('.toast')).toHaveLength(1);
    // ポーズの表示は盤面に描く（DOM に置かない）。通知を積む箱も無い。
    expect(page.querySelector('#pause')).toBeNull();
    expect(page.querySelector('#toasts')).toBeNull();
  });

  it('通信対戦の案内の帯は、幕（原型の z-index 20）より上、通知（30）より下に重ねる', () => {
    const css = read('../../src/style.css');
    const zIndexOf = (selector: string): number => {
      const body = css.match(new RegExp(`(?:^|\\n)${selector.replace('.', '\\.')}\\s*\\{([^}]*)\\}`))?.[1] ?? '';
      return Number(body.match(/z-index:\s*(\d+)/)?.[1]);
    };
    expect(zIndexOf('.toast')).toBe(30);
    expect(zIndexOf('.lan-status')).toBeGreaterThan(20);
    expect(zIndexOf('.lan-status')).toBeLessThan(30);
  });

  it('起動の幕は、出すまで隠してある（index.html の hidden と、それを見た目に反映する CSS の両方）', () => {
    // `?relay` で開いたページは幕を出さない（`Splash.show` を呼ばない）。`#splash { display: flex }` は id の決まりなので
    // ブラウザの `[hidden] { display: none }` に勝つ。どちらか一方が欠けると、空の幕が全面を覆ったまま消えない。
    const splash = read('../../index.html').match(/<div id="splash"[^>]*>/)?.[0];
    expect(splash).toBeDefined();
    expect(splash).toMatch(/\shidden[\s>]/);
    const css = read('../../src/style.css');
    expect(css).toMatch(/#splash\[hidden\]\s*\{[^}]*display:\s*none/);
    expect(css).toMatch(/#splash\s*\{[^}]*display:\s*flex/);
  });
});
