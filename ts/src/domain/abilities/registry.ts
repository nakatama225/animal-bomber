/**
 * 動物の登録をまとめる。
 *
 * 追加するときに触るのは**このファイルの1行と、その動物のフォルダだけ**。
 * 移動・爆弾・被弾の処理にも、既存の動物にも手を入れない。
 *
 * 登録は import の副作用ではなく、ここで明示的に行う。副作用に頼ると、
 * どのファイルが読み込まれたかで登録の有無が変わり、束ね方によって
 * 動いたり動かなかったりする。
 */
import { lookupAbility, registerAbility, type Ability } from './Ability.js';
import { ELEPHANT } from './elephant/ElephantAbility.js';
import { FOX } from './fox/FoxAbility.js';
import { FROG } from './frog/FrogAbility.js';
import { MOLE } from './mole/MoleAbility.js';
import { RABBIT } from './rabbit/RabbitAbility.js';

let done = false;

/**
 * 識別子から能力を引く。
 *
 * まだ登録されていなければ、その場で登録する。呼び出し側に
 * 「先に登録しておく」という手順を強いると、忘れた場所だけが
 * 実行時に落ちる。冪等な操作なので、引くたびに確かめてよい。
 */
export function abilityOf(key: string): Ability {
  registerAllAnimals();
  const found = lookupAbility(key);
  if (found === undefined) throw new Error(`登録されていない動物: ${key}`);
  return found;
}

/** すべての動物を登録する。二度呼んでも安全。 */
export function registerAllAnimals(): void {
  if (done) return;
  done = true;
  registerAbility(RABBIT);
  registerAbility(ELEPHANT);
  registerAbility(MOLE);
  registerAbility(FOX);
  registerAbility(FROG);
}
