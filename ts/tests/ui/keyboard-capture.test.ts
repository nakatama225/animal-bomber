// @vitest-environment happy-dom
import { afterEach, describe, expect, it } from 'vitest';

import { KeyboardInputSource, KeyboardWatcher, PREVENTED_KEYS, SOLO_KEYS } from '../../src/platform/Keyboard.js';

function keydown(code: string, extra: KeyboardEventInit = {}): KeyboardEvent {
  const event = new KeyboardEvent('keydown', { code, cancelable: true, ...extra });
  window.dispatchEvent(event);
  return event;
}

function keyup(code: string): void {
  window.dispatchEvent(new KeyboardEvent('keyup', { code }));
}

const watcher = new KeyboardWatcher();
afterEach(() => watcher.detach());

describe('ブラウザの既定の動きを止めるキー', () => {
  it('Space・矢印・Enter・Slash の7つを、いつも止める（原型と同じ）', () => {
    watcher.attach();
    expect(PREVENTED_KEYS).toEqual(['Space', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Enter', 'Slash']);
    for (const code of PREVENTED_KEYS) expect(keydown(code).defaultPrevented, code).toBe(true);
    // 押し続けたときの繰り返しでも止める（原型は押した瞬間の判定より前で止める。止めないと押し続けている間にページが動く）。
    for (const code of PREVENTED_KEYS) expect(keydown(code, { repeat: true }).defaultPrevented, code).toBe(true);
  });

  it('修飾キー（Command・Ctrl・Option・Shift）と一緒でも止める（原型は修飾キーを見ない）', () => {
    watcher.attach();
    expect(keydown('ArrowDown', { metaKey: true }).defaultPrevented).toBe(true);
    expect(keydown('Space', { ctrlKey: true }).defaultPrevented).toBe(true);
    expect(keydown('ArrowLeft', { altKey: true }).defaultPrevented).toBe(true);
    expect(keydown('Slash', { shiftKey: true }).defaultPrevented).toBe(true);
  });

  it('ほかのキーは止めない（操作のキーでも、ポーズ・戻るのキーでも）', () => {
    watcher.attach();
    for (const code of ['KeyW', 'KeyP', 'KeyE', 'ShiftLeft', 'AltLeft', 'Escape', 'Backspace', 'Period']) {
      expect(keydown(code).defaultPrevented, code).toBe(false);
    }
  });

  it('止めても、押されたことは数える', () => {
    watcher.attach();
    keydown('ArrowUp');
    expect(watcher.anyOf(SOLO_KEYS.up)).toBe(true);
  });
});

describe('押してすぐ離したキー', () => {
  it('押した瞬間を、離したあとも忘れるまで残す（爆弾と技のボタンとしてだけ）', () => {
    watcher.attach();
    keydown('Space');
    keyup('Space');
    expect(watcher.anyOf(['Space'])).toBe(false);
    expect(watcher.buttonAnyOf(['Space'])).toBe(true);
    watcher.forgetTaps();
    expect(watcher.buttonAnyOf(['Space'])).toBe(false);
  });

  it('キーの繰り返しは押した瞬間にしない', () => {
    watcher.attach();
    keydown('Space', { repeat: true });
    keyup('Space');
    expect(watcher.buttonAnyOf(['Space'])).toBe(false);
  });

  it('押したままのキーは、押した瞬間を忘れたあとも押していることにする', () => {
    watcher.attach();
    keydown('KeyE');
    watcher.forgetTaps();
    expect(watcher.buttonAnyOf(['KeyE'])).toBe(true);
  });

  it('押していたキーに、離したことが届かないまま繰り返しでない keydown が来ても、押した瞬間にしない（原型と同じ）', () => {
    // 原型の押した瞬間は「押していなかったキー」で、繰り返しでないもの（L3065）。
    watcher.attach();
    keydown('Space');
    watcher.forgetTaps();
    keydown('Space');
    keyup('Space');
    expect(watcher.buttonAnyOf(['Space'])).toBe(false);
  });
});

describe('Option・Command を離したとき（原型 L3093-3098）', () => {
  /** 右へ歩きながら Space を押したまま、Option を押して離す。押した瞬間は忘れておく。 */
  function holdThenReleaseOption(modifier = 'AltLeft'): void {
    watcher.attach();
    keydown('KeyD');
    keydown('Space');
    keydown(modifier);
    keyup(modifier);
    watcher.forgetTaps();
  }

  it('ほかの押しているキーを捨てる（macOS が離したことを送らないことがあるため）', () => {
    for (const modifier of ['AltLeft', 'AltRight', 'MetaLeft', 'MetaRight']) {
      holdThenReleaseOption(modifier);
      expect(watcher.anyOf(['KeyD']), modifier).toBe(false);
      expect(watcher.buttonAnyOf(['Space']), modifier).toBe(false);
      watcher.detach();
    }
  });

  it('Shift や Ctrl を離しても捨てない', () => {
    watcher.attach();
    keydown('KeyD');
    keydown('ShiftLeft');
    keyup('ShiftLeft');
    keydown('ControlLeft');
    keyup('ControlLeft');
    expect(watcher.anyOf(['KeyD'])).toBe(true);
  });

  it('押したままの Option・Command は捨てない', () => {
    watcher.attach();
    keydown('AltRight');
    keydown('AltLeft');
    keyup('AltLeft');
    expect(watcher.anyOf(['AltRight'])).toBe(true);
  });

  it('捨てたキーは、繰り返しで戻ると向きにだけ数え、爆弾と技には数えない。もう一度押せば数える', () => {
    holdThenReleaseOption();
    keydown('KeyD', { repeat: true });
    keydown('Space', { repeat: true });
    const source = new KeyboardInputSource(0, watcher, SOLO_KEYS);
    // 前の tick に離していた爆弾のキーが押し下がって見えると、勝手に爆弾を置く。
    expect(source.next()).toMatchObject({ right: true, bomb: false });
    keyup('Space');
    keydown('Space');
    expect(source.next()).toMatchObject({ right: true, bomb: true });
  });

  it('捨てたキーを離してもう一度押したときも、ふつうに数える', () => {
    holdThenReleaseOption();
    keyup('Space');
    expect(watcher.buttonAnyOf(['Space'])).toBe(false);
    keydown('Space');
    keyup('Space');
    // 押してすぐ離しても、押した瞬間は残る。
    expect(watcher.buttonAnyOf(['Space'])).toBe(true);
  });
});

describe('画面から離れたとき', () => {
  it('押しているキーを捨てる（原型 L3100）', () => {
    watcher.attach();
    keydown('KeyD');
    window.dispatchEvent(new Event('blur'));
    expect(watcher.anyOf(['KeyD'])).toBe(false);
  });

  it('押した瞬間は残す（原型の blur は押しているキーだけを消す）', () => {
    watcher.attach();
    keydown('Space');
    window.dispatchEvent(new Event('blur'));
    expect(watcher.anyOf(['Space'])).toBe(false);
    expect(watcher.buttonAnyOf(['Space'])).toBe(true);
  });

  it('押したまま戻ってきたキーは、繰り返しで向きにだけ数え、爆弾と技はもう一度押すまで数えない（原型と同じ）', () => {
    // 原型の blur は押しているキーだけを消し、繰り返しは押した瞬間を立てないので、戻ったキーで爆弾を置かない。
    watcher.attach();
    keydown('KeyD');
    keydown('Space');
    watcher.forgetTaps();
    window.dispatchEvent(new Event('blur'));
    keydown('KeyD', { repeat: true });
    keydown('Space', { repeat: true });
    const source = new KeyboardInputSource(0, watcher, SOLO_KEYS);
    expect(source.next()).toMatchObject({ right: true, bomb: false });
    keyup('Space');
    keydown('Space');
    expect(source.next()).toMatchObject({ right: true, bomb: true });
  });

  it('Option を離したときに捨てたキーも、画面から戻ったあと繰り返しでは爆弾と技に数えない', () => {
    watcher.attach();
    keydown('Space');
    keydown('AltLeft');
    keyup('AltLeft');
    watcher.forgetTaps();
    window.dispatchEvent(new Event('blur'));
    keydown('Space', { repeat: true });
    expect(watcher.buttonAnyOf(['Space'])).toBe(false);
  });
});
