/**
 * 起動の入口。**配線だけを行い、判断を持たない。**
 *
 * この層に条件分岐が増えてきたら、それは下の層のどれかに置き場所が
 * 見つかっていないということなので、ここで処理せず置き場所を探す。
 *
 * ⚠️ 現在は骨組みだけ。ゲームのルールを組み立てる部分は、
 * 対応する層ができるたびにここへ繋いでいく。
 */

const CANVAS_ID = 'stage';

function findCanvas(): HTMLCanvasElement {
  const element = document.getElementById(CANVAS_ID);
  if (!(element instanceof HTMLCanvasElement)) {
    throw new Error(`#${CANVAS_ID} が見つからないか、canvas ではない`);
  }
  return element;
}

function main(): void {
  const canvas = findCanvas();
  const context = canvas.getContext('2d');
  if (context === null) {
    throw new Error('2D の描画コンテキストを取得できない');
  }

  context.fillStyle = '#101418';
  context.fillRect(0, 0, canvas.width, canvas.height);
}

main();
