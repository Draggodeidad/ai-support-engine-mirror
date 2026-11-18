import * as traditional from './traditional/index.js';
import * as generative from './generative/index.js';
import * as ml from './ml/index.js';

const engines = { traditional, generative, ml };

export function getEngine(mode) {
  const engine = engines[mode];
  if (!engine) throw new Error(`Motor desconocido: ${mode}`);
  return engine;
}
