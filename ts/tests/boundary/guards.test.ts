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
 * 何も守っていない。** そのためここでは、テストごとに次を行う。
 *
 * 1. 禁じた書き方を1行だけ含む使い捨てのファイルを `src/` の下に書き出す
 * 2. 本物の検査コマンド（tsc / eslint / depcruise）を子プロセスで実行する
 * 3. コマンドがエラーで終わり、出力に違反した規則の名前が出ることを確かめる
 * 4. 書き出したファイルを消す（`afterEach`）
 *
 * この確認は、検査の設定を変えたときに意味を持つ。設定を緩めると、
 * ここが落ちる。
 */

const ROOT = join(import.meta.dirname, '..', '..');

/** そのフォルダの下にある .ts ファイルを、下のフォルダまで含めて ROOT からの相対パスで返す。 */
function listTs(dir: string): string[] {
  const entries = readdirSync(join(ROOT, dir), { recursive: true, encoding: 'utf8' });
  return entries
    .filter((entry) => entry.endsWith('.ts'))
    .map((entry) => `${dir}/${entry.split('\\').join('/')}`)
    .sort();
}
const VIOLATION = join(ROOT, 'src', 'domain', 'core', '__boundary_probe__.ts');
const AI_VIOLATION = join(ROOT, 'src', 'ai', '__boundary_probe__.ts');

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
  rmSync(AI_VIOLATION, { force: true });
});

describe('境界を守る仕組み', () => {
  it('違反が無ければ、3つの検査はいずれも通る', () => {
    // 使い捨てのファイルを書き出す前に、同じコマンドがエラーなく終わることを確かめる。
    // ここが赤いと、下のテストが落ちたときに、原因が書き出したファイルなのか
    // もともとあった別の違反なのかが区別できなくなる。
    expect(run('npx', ['tsc', '-p', 'tsconfig.domain.json']).failed).toBe(false);
    expect(run('npx', ['eslint', 'src/domain', 'src/ai']).failed).toBe(false);
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

  it('CPU の思考の層で Math.random を呼ぶと lint が落ちる', () => {
    // CPU の判断も種から決まる必要がある。通信対戦では各端末が同じ CPU を
    // 動かすので、1台だけ違う乱数を引くと、その端末でだけ別の手を指す。
    writeFileSync(AI_VIOLATION, 'export const roll = (): number => Math.random();\n');
    const result = run('npx', ['eslint', AI_VIOLATION]);
    expect(result.failed).toBe(true);
    expect(result.output).toContain('no-restricted-properties');
  }, 60_000);

  it('CPU の思考の層でブラウザ API を使うと型検査が落ちる', () => {
    writeFileSync(AI_VIOLATION, 'export const width = window.innerWidth;\n');
    const result = run('npx', ['tsc', '-p', 'tsconfig.domain.json']);
    expect(result.failed).toBe(true);
    expect(result.output).toContain('window');
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

  it('CPU の思考の層から上の層を import すると依存の検査が落ちる', () => {
    writeFileSync(
      AI_VIOLATION,
      "import '../presentation/Presenter.js';\nexport const broken = true;\n",
    );
    const result = run('npx', ['depcruise', 'src', '--config', '.dependency-cruiser.cjs']);
    expect(result.failed).toBe(true);
    expect(result.output).toContain('ai-は-上の層を使わない');
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
 *
 * CPU も同じ形にしてある。共通の判断は動物を知らず、動物ごとの違いは
 * 戦い方（`ai/tactics/`）として差し込む。
 *
 * ⚠️ この検査はファイルの文字列をそのまま見ていて、コードとコメントを区別しない。
 * コメントに動物の名前を書くだけでも落ちる。原型の逸話を書くときも動物の名前は出さず、
 * 「一列に並べる動物」「ブロックを通り抜ける動物」のように能力で書く。
 */
describe('動物の追加が閉じていること', () => {
  const ANIMAL_WORDS =
    /rabbit|elephant|mole|fox|frog|charge|うさぎ|ぞう|もぐら|きつね|かえる|突進/;

  it('共通の処理に動物の名前が現れない', () => {
    // CPU の思考（ai/）は下のフォルダまで全部見る。動物ごとの戦い方は ai/tactics/ に
    // 分けてあり、そこだけは動物の名前が出てよい。
    const files = [
      ...listTs('src/domain/systems'),
      ...listTs('src/domain/mutations'),
      ...listTs('src/domain/query'),
      ...listTs('src/domain/negibon'),
      ...listTs('src/ai').filter((file) => !file.startsWith('src/ai/tactics/')),
    ];
    const offenders = files.filter((file) => ANIMAL_WORDS.test(readFileSync(join(ROOT, file), 'utf8')));
    expect(offenders).toEqual([]);
  });

  it('見張る対象に、CPU の共通の判断と葱ボンが入っている', () => {
    // 見張るファイルの一覧が空だと、上の確認は何も見ずに通る。
    expect(listTs('src/ai')).toContain('src/ai/behaviors/Flee.ts');
    expect(listTs('src/ai')).toContain('src/ai/CpuIntentSource.ts');
    expect(listTs('src/domain/negibon')).toContain('src/domain/negibon/LeekActor.ts');
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
