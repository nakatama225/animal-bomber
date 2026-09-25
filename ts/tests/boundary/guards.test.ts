import { execFileSync } from 'node:child_process';
import { readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
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

/**
 * 動物を追加しても、共通の処理に手を入れずに済むことの確認。
 *
 * ⚠️ これは「拡張に開いた形」が守られているかを、文字列の有無という
 * 機械的な形で見張るもの。設計を語る文章より、この1本のほうが崩れにくい。
 *
 * 突進は移動・破壊・取得・被弾の4つに同時に割り込むため、いちばん
 * 特別扱いを誘発しやすい。ここが通れば、他の動物は自動的に通る。
 */
describe('動物の追加が閉じていること', () => {
  const ANIMAL_WORDS =
    /rabbit|elephant|mole|fox|frog|charge|うさぎ|ぞう|もぐら|きつね|かえる|突進/;

  it('共通の処理に動物の名前が現れない', () => {
    const dirs = ['src/domain/systems', 'src/domain/mutations'];
    const offenders: string[] = [];
    for (const dir of dirs) {
      for (const name of readdirSync(join(ROOT, dir))) {
        if (!name.endsWith('.ts')) continue;
        const body = readFileSync(join(ROOT, dir, name), 'utf8');
        if (ANIMAL_WORDS.test(body)) offenders.push(`${dir}/${name}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it('見張る言葉が、実際に動物のファイルには現れる', () => {
    // 前の確認が「その言葉がどこにも無いだけ」で通ってしまわないための対照。
    const body = readFileSync(
      join(ROOT, 'src/domain/abilities/elephant/ChargeAction.ts'),
      'utf8',
    );
    expect(ANIMAL_WORDS.test(body)).toBe(true);
  });
});
