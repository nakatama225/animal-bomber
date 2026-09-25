import {
  lookupTactic,
  PLAIN_TACTIC,
  registerTactic,
  type AnimalTactic,
} from './AnimalTactic.js';
import { ELEPHANT_TACTIC } from './ElephantTactic.js';
import { FOX_TACTIC } from './FoxTactic.js';
import { FROG_TACTIC } from './FrogTactic.js';
import { MOLE_TACTIC } from './MoleTactic.js';
import { RABBIT_TACTIC } from './RabbitTactic.js';

let done = false;

/**
 * 戦い方をすべて登録する。何度呼んでも1回しか登録しない。
 *
 * 動物を追加するときに足すのは、ここの1行と戦い方のファイル1つ。
 * 戦い方を書かなくても、省略時の戦い方でその動物は戦える。
 */
export function registerAllTactics(): void {
  if (done) return;
  done = true;
  registerTactic(RABBIT_TACTIC);
  registerTactic(ELEPHANT_TACTIC);
  registerTactic(MOLE_TACTIC);
  registerTactic(FOX_TACTIC);
  registerTactic(FROG_TACTIC);
}

/** その動物の戦い方。書かれていなければ省略時の戦い方。 */
export function tacticOf(animal: string): AnimalTactic {
  registerAllTactics();
  return lookupTactic(animal) ?? PLAIN_TACTIC;
}
