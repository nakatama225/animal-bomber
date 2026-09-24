import { execFileSync } from 'node:child_process';
import { rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

/**
 * 境界を守る仕組みが、実際に違反を落とすことの確認。
 *
 * この実装には「ルールの層でブラウザ API を使わない」「依存を逆流させない」
 * 「決定性を壊す呼び出しをしない」という3つの約束があり、それぞれを
 * 検査の設定として書いてある。
 *
 * ⚠️ 設定を書いただけでは、それが効いているかは分からない。設定の書き方を
 * 間違えていても、違反が無ければ検査は緑のまま通る。**緑のまま通る検査は
 * 何も守っていない。** そのためここでは、わざと違反したファイルを置いて
 * 検査が落ちることを確かめ、そのうえで片付ける。
 *
 * この確認は、検査の設定を変えたときに意味を持つ。設定を緩めると、
 * ここが落ちる。
 */

const ROOT = join(import.meta.dirname, '..', '..');
const VIOLATION = join(ROOT, 'src', 'domain', 'core', '__boundary_probe__.ts');

/** 検査を1つ走らせ、落ちたかどうかと出力を返す。 */
function run(command: string, args: readonly string[]): { failed: boolean; output: string } {
  try {
    const stdout = execFileSync(command, args, { cwd: ROOT, encoding: 'utf8', stdio: 'pipe' });
    return { failed: false, output: stdout };
  } catch (error) {
    const e = error as { stdout?: string; stderr?: string };
    return { failed: true, output: `${e.stdout ?? ''}${e.stderr ?? ''}` };
  }
}

afterEach(() => {
  rmSync(VIOLATION, { force: true });
});

describe('境界を守る仕組み', () => {
  it('違反が無ければ、3つの検査はいずれも通る', () => {
    // 逆向きの確認の前提。ここが赤いと「壊したから落ちた」のか
    // 「もともと落ちていた」のかが区別できなくなる。
    expect(run('npx', ['tsc', '-p', 'tsconfig.domain.json']).failed).toBe(false);
    expect(run('npx', ['eslint', 'src/domain']).failed).toBe(false);
    expect(
      run('npx', ['depcruise', 'src', '--config', '.dependency-cruiser.cjs']).failed,
    ).toBe(false);
  }, 120_000);

  it('ルールの層でブラウザ API を使うと型検査が落ちる', () => {
    writeFileSync(VIOLATION, 'export const width = document.body.clientWidth;\n');
    const result = run('npx', ['tsc', '-p', 'tsconfig.domain.json']);
    expect(result.failed).toBe(true);
    expect(result.output).toContain('document');
  }, 60_000);

  it('ルールの層で Math.random を呼ぶと lint が落ちる', () => {
    writeFileSync(VIOLATION, 'export const roll = (): number => Math.random();\n');
    const result = run('npx', ['eslint', VIOLATION]);
    expect(result.failed).toBe(true);
    expect(result.output).toContain('no-restricted-properties');
  }, 60_000);

  it('ルールの層から上の層を import すると依存の検査が落ちる', () => {
    writeFileSync(
      VIOLATION,
      "import '../../presentation/CosmeticRng.js';\nexport const broken = true;\n",
    );
    const result = run('npx', ['depcruise', 'src', '--config', '.dependency-cruiser.cjs']);
    expect(result.failed).toBe(true);
    expect(result.output).toContain('domain-は-上の層を使わない');
  }, 60_000);
});
