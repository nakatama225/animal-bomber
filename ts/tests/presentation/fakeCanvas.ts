/**
 * 描画の検査に使う、何も描かない canvas の代役。
 *
 * node にはブラウザの canvas が無い。描く関数が例外を出さずに最後まで
 * 走ることと、どの命令を何回呼んだかだけを確認するために使う。
 *
 * ⚠️ 原型では、描画の中の参照の誤り（存在しない変数を読む、など）が
 * ルールのテストからは見えず、実際に遊ぶと画面が固まる、という形で出た。
 * 描く関数を一通り呼ぶ検査は、それを画面を開かずに検出するためのもの。
 */
export interface FakeCanvas {
  readonly context: CanvasRenderingContext2D;
  /** 呼ばれた命令の名前と回数。 */
  readonly calls: Map<string, number>;
  /** 呼ばれた命令と引数を、呼ばれた順に。 */
  readonly log: { readonly name: string; readonly args: readonly unknown[] }[];
}

/**
 * 本物の canvas が例外を出す呼び方を、ここでも例外にする。
 *
 * ブラウザは半径が負の円や、0〜1 の外の色の区切りを受け付けず、描画の途中で
 * 例外を投げる。画面では「ある瞬間だけ固まる」形で現れ、原因が分かりにくい。
 * 偽物が何でも受け付けると、この種の誤りを検査で拾えない。
 */
function rejectInvalid(property: string, args: readonly unknown[]): void {
  const n = (index: number): number => Number(args[index]);
  const negative = (...indexes: number[]): boolean => indexes.some((i) => n(i) < 0);
  if (property === 'arc' && negative(2)) throw new RangeError(`arc の半径が負: ${n(2)}`);
  if (property === 'ellipse' && negative(2, 3)) {
    throw new RangeError(`ellipse の半径が負: ${n(2)}, ${n(3)}`);
  }
  if (property === 'createRadialGradient' && negative(2, 5)) {
    throw new RangeError(`createRadialGradient の半径が負: ${n(2)}, ${n(5)}`);
  }
}

/**
 * @param keepLog 呼ばれた命令と引数を残すか。試合を通して描く検査では、残すと
 *   数千万件になってメモリが尽きるので切る。回数（`calls`）は切っても数える。
 */
export function fakeCanvas({ keepLog = true }: { readonly keepLog?: boolean } = {}): FakeCanvas {
  const calls = new Map<string, number>();
  const log: { name: string; args: readonly unknown[] }[] = [];
  const gradient = {
    addColorStop: (offset: number) => {
      if (!(offset >= 0 && offset <= 1)) throw new RangeError(`addColorStop の位置が範囲外: ${offset}`);
    },
  };
  const state: Record<string, unknown> = {};
  const handler: ProxyHandler<Record<string, unknown>> = {
    get(_target, property) {
      if (typeof property !== 'string') return undefined;
      if (property in state) return state[property];
      return (...args: unknown[]) => {
        rejectInvalid(property, args);
        calls.set(property, (calls.get(property) ?? 0) + 1);
        if (keepLog) log.push({ name: property, args });
        if (property === 'createLinearGradient' || property === 'createRadialGradient') return gradient;
        if (property === 'measureText') return { width: String(args[0] ?? '').length * 8 };
        if (property === 'getTransform') return { a: 1, b: 0, c: 0, d: 1, e: 0, f: 0 };
        return undefined;
      };
    },
    set(_target, property, value) {
      if (typeof property === 'string') state[property] = value;
      return true;
    },
  };
  const context = new Proxy({}, handler) as unknown as CanvasRenderingContext2D;
  return { context, calls, log };
}
