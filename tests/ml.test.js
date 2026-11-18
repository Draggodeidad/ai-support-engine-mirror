// Tests del motor ML con un fetch falso (el servicio Python se prueba aparte con pytest).
import { describe, it, expect, vi } from 'vitest';
import { createMlEngine } from '../src/engines/ml/index.js';
import { RESPONSES } from '../src/engines/traditional/index.js';
import { analyzeMessage } from '../src/pipeline.js';

const prediction = { category: 'ACCESS', priority: 'MEDIUM', categoryConfidence: 0.9, priorityConfidence: 0.8 };

function jsonResponse(body, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

function engineWith(response, options = {}) {
  const fetchFn = vi.fn().mockResolvedValue(response);
  return { fetchFn, engine: createMlEngine({ baseUrl: 'http://ml.test', fetchFn, ...options }) };
}

describe('motor ml', () => {
  it('arma el contrato con la respuesta predeterminada', async () => {
    const { engine, fetchFn } = engineWith(jsonResponse(prediction));
    await expect(engine.analyze('No puedo iniciar sesión')).resolves.toEqual({
      category: 'ACCESS',
      priority: 'MEDIUM',
      response: RESPONSES.ACCESS.MEDIUM,
      requiresHumanReview: false,
    });
    const [url, init] = fetchFn.mock.calls[0];
    expect(String(url)).toBe('http://ml.test/predict');
    expect(JSON.parse(init.body)).toEqual({ message: 'No puedo iniciar sesión' });
  });

  it('pide revisión humana si la confianza es baja', async () => {
    const { engine } = engineWith(jsonResponse({ ...prediction, priorityConfidence: 0.3 }), { minConfidence: 0.5 });
    await expect(engine.analyze('algo raro')).resolves.toMatchObject({ requiresHumanReview: true });
  });

  it('pide revisión humana en SECURITY', async () => {
    const { engine } = engineWith(jsonResponse({ ...prediction, category: 'SECURITY', priority: 'HIGH' }));
    await expect(engine.analyze('correo sospechoso')).resolves.toMatchObject({ requiresHumanReview: true });
  });

  it('ML_SERVICE_UNAVAILABLE si no hay conexión', async () => {
    const engine = createMlEngine({ fetchFn: vi.fn().mockRejectedValue(new TypeError('fetch failed')) });
    await expect(engine.analyze('hola mundo')).rejects.toMatchObject({ code: 'ML_SERVICE_UNAVAILABLE', status: 503 });
  });

  it('ML_SERVICE_UNAVAILABLE si el modelo no está cargado (503)', async () => {
    const { engine } = engineWith(jsonResponse({ error: { code: 'MODEL_NOT_LOADED' } }, 503));
    await expect(engine.analyze('hola mundo')).rejects.toMatchObject({ code: 'ML_SERVICE_UNAVAILABLE', status: 503 });
  });

  it('ML_SERVICE_ERROR ante otros errores del servicio', async () => {
    const { engine } = engineWith(jsonResponse({}, 500));
    await expect(engine.analyze('hola mundo')).rejects.toMatchObject({ code: 'ML_SERVICE_ERROR', status: 502 });
  });

  it('ML_INVALID_OUTPUT si la predicción no cumple el formato', async () => {
    const { engine } = engineWith(jsonResponse({ category: 'OTHER', priority: 'LOW' }));
    await expect(engine.analyze('hola mundo')).rejects.toMatchObject({ code: 'ML_INVALID_OUTPUT', status: 502 });
  });

  it('ML_TIMEOUT si el servicio no responde a tiempo', async () => {
    const fetchFn = (_url, { signal }) =>
      new Promise((_, reject) => signal.addEventListener('abort', () => reject(new Error('aborted'))));
    const engine = createMlEngine({ fetchFn, timeoutMs: 20 });
    await expect(engine.analyze('hola mundo')).rejects.toMatchObject({ code: 'ML_TIMEOUT', status: 504 });
  });

  it('la política de seguridad del pipeline también se aplica al motor ml', async () => {
    const { engine } = engineWith(jsonResponse({ ...prediction, category: 'SECURITY', priority: 'LOW' }));
    const { result } = await analyzeMessage('hackearon mi cuenta', 'ml', { getEngine: () => engine });
    expect(result).toMatchObject({ mode: 'ml', category: 'SECURITY', requiresHumanReview: true });
    expect(['HIGH', 'CRITICAL']).toContain(result.priority);
  });
});
