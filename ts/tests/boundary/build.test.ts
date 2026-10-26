import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

/**
 * ビルドの出力が、中継サーバの `/ts/` の下で配っても動く形になっていること。
 *
 * 中継サーバ（`server/`）は、この版のビルドの出力を `/ts/` の下で配る。出力の中で
 * スクリプトやスタイルを `/assets/…` と参照すると、`/ts/` の外（原型の HTML の側）を指して
 * 読み込めない。`vite.config.ts` の `base: './'` で相対の道にしてある。
 */

const ROOT = join(import.meta.dirname, '..', '..');
let outDir: string | null = null;

afterEach(() => {
  if (outDir !== null) rmSync(outDir, { recursive: true, force: true });
  outDir = null;
});

describe('ビルドの出力', () => {
  it('スクリプトとスタイルを、相対の道（./assets/…）で参照する', () => {
    outDir = mkdtempSync(join(tmpdir(), 'animal-bomber-build-'));
    execFileSync('npx', ['vite', 'build', '--outDir', outDir, '--emptyOutDir', '--logLevel', 'error'], {
      cwd: ROOT,
      stdio: 'pipe',
    });
    const html = readFileSync(join(outDir, 'index.html'), 'utf8');
    const references = [...html.matchAll(/(?:src|href)="([^"]+)"/g)].map((match) => match[1]);
    // 前提：スクリプトとスタイルの両方を参照している（何も参照していなければ、下の確認が空振りする）。
    expect(references.some((ref) => ref?.endsWith('.js'))).toBe(true);
    expect(references.some((ref) => ref?.endsWith('.css'))).toBe(true);
    expect(references.filter((ref) => !ref?.startsWith('./assets/'))).toEqual([]);
  }, 120_000);
});
