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

  it('入口は P キーを Shell.pressPauseKey へ渡す（togglePause に直に渡すと、確認の画面を開いている間も止まる）', () => {
    // 入口は読み込めないので、P キーの行を文字列で見る。確認の画面の間に P を止めるのは pressPauseKey（原型 L3074-3081）。
    const lines = read('../../src/app/main.ts')
      .split('\n')
      .filter((line) => line.includes('PAUSE_KEY') && line.includes('shell.'));
    expect(lines).toHaveLength(1);
    expect(lines[0]).toContain('shell.pressPauseKey()');
    expect(lines[0]).not.toContain('togglePause');
  });

  it('見た目の指定を読み込んでいる', () => {
    expect(read('../../index.html')).toContain('href="/src/style.css"');
  });

  it('試合の画面は、盤面と横の板を .stage に横に並べ、幕・確認の画面・通知は #app の外に置く（原型 L513-567）', () => {
    // body の中身だけを template に読む（ページとして読むと、見た目の指定とスクリプトを取りに行く）。
    const body = read('../../index.html').match(/<body>([\s\S]*)<\/body>/)?.[1] ?? '';
    const template = document.createElement('template');
    template.innerHTML = body;
    const page = template.content;
    const stage = page.querySelector('#play > .stage');
    expect([...(stage?.children ?? [])].map((child) => child.className || `#${child.id}`)).toEqual(['board', '#side']);
    // 盤面に重ねる通信対戦の案内の帯は、canvas と同じ包みに入れる。幕は入れない（窓の全体を覆う）。
    expect([...(stage?.querySelector('.board')?.children ?? [])].map((child) => child.id)).toEqual(['stage', 'lan-status']);
    // 幕・起動の幕・確認の画面・通知は body の直下（#app の外）に、原型と同じ順で置く。
    expect([...page.children].filter((child) => child.tagName !== 'SCRIPT').map((child) => child.id)).toEqual([
      'app',
      'banner',
      'splash',
      'cfmWrap',
      'toast',
    ]);
    expect(page.querySelectorAll('.toast')).toHaveLength(1);
    // ポーズの表示は盤面に描く（DOM に置かない）。通知を積む箱も無い。
    expect(page.querySelector('#pause')).toBeNull();
    expect(page.querySelector('#toasts')).toBeNull();
  });

  it('重なりの順は原型と同じ（幕 20・通知 30・確認の画面 40・起動の幕 50）。通信対戦の案内の帯は幕より上、通知より下', () => {
    const css = read('../../src/style.css');
    const ruleOf = (selector: string): string =>
      css.match(new RegExp(`(?:^|\\n)${selector.replace('.', '\\.')}\\s*\\{([^}]*)\\}`))?.[1] ?? '';
    const zIndexOf = (selector: string): number => Number(ruleOf(selector).match(/z-index:\s*(\d+)/)?.[1]);
    expect([zIndexOf('#banner'), zIndexOf('.toast'), zIndexOf('.cfm'), zIndexOf('#splash')]).toEqual([20, 30, 40, 50]);
    expect(zIndexOf('.lan-status')).toBeGreaterThan(20);
    expect(zIndexOf('.lan-status')).toBeLessThan(30);
    // 帯の包みに z-index を付けない（付けると包みが重なりの文脈を作り、帯が幕と比べられなくなって幕の下に隠れる）。
    expect(ruleOf('.board')).not.toBe('');
    expect(ruleOf('.board')).not.toMatch(/z-index/);
    // 帯が幕のボタンにかかっても、押したときは下のボタンに届ける。
    expect(ruleOf('.lan-status')).toMatch(/pointer-events:\s*none/);
  });

  it('幕と確認の画面は、出すまで隠してある（index.html の hidden と、それを見た目に反映する CSS の両方）', () => {
    // どちらも窓の全体を覆う要素で、出しているときの display（flex）は [hidden] に勝つ。片方が欠けると、空の暗い面が
    // 窓を覆ったまま消えない。
    const html = read('../../index.html');
    const css = read('../../src/style.css');
    for (const [id, selector] of [
      ['banner', '#banner'],
      ['cfmWrap', '\\.cfm'],
    ] as const) {
      expect(html.match(new RegExp(`<div id="${id}"[^>]*>`))?.[0], id).toMatch(/\shidden[\s>]/);
      expect(css, id).toMatch(new RegExp(`(?:^|\\n)${selector}\\[hidden\\]\\s*\\{[^}]*display:\\s*none`));
      expect(css, id).toMatch(new RegExp(`(?:^|\\n)${selector}\\s*\\{[^}]*display:\\s*flex`));
    }
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
