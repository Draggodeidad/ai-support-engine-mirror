// Motor ML: clasifica con el microservicio Python (ml-service/, TF-IDF + regresión logística).
// El servicio solo devuelve categoría, prioridad y confianza; la respuesta se toma de la tabla
// predeterminada del motor tradicional y la revisión humana se pide cuando el modelo duda.
import { z } from 'zod';
import { CATEGORIES, PRIORITIES } from '../../contract.js';
import { AppError } from '../../errors.js';
import { RESPONSES } from '../traditional/index.js';

const PredictionSchema = z.object({
  category: z.enum(CATEGORIES),
  priority: z.enum(PRIORITIES),
  categoryConfidence: z.number().min(0).max(1),
  priorityConfidence: z.number().min(0).max(1),
});

export function createMlEngine({
  baseUrl = process.env.ML_SERVICE_URL || 'http://localhost:8000',
  timeoutMs = Number(process.env.ML_TIMEOUT_MS) || 5000,
  minConfidence = Number(process.env.ML_MIN_CONFIDENCE ?? 0.5),
  fetchFn = fetch,
} = {}) {
  async function analyze(message) {
    const prediction = await requestPrediction(message);
    const { category, priority } = prediction;
    const lowConfidence = Math.min(prediction.categoryConfidence, prediction.priorityConfidence) < minConfidence;
    return {
      category,
      priority,
      response: RESPONSES[category][priority],
      // La política de seguridad del pipeline además fuerza revisión en SECURITY e incidentes.
      requiresHumanReview: category === 'SECURITY' || lowConfidence,
    };
  }

  async function requestPrediction(message) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    let res;
    try {
      res = await fetchFn(new URL('/predict', baseUrl), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message }),
        signal: controller.signal,
      });
    } catch {
      if (controller.signal.aborted) {
        throw new AppError('ML_TIMEOUT', 'El servicio de Machine Learning no respondió a tiempo', 504);
      }
      console.error('[ml] no se pudo conectar con el servicio');
      throw new AppError('ML_SERVICE_UNAVAILABLE', 'El servicio de Machine Learning no está disponible', 503);
    } finally {
      clearTimeout(timer);
    }

    if (!res.ok) {
      console.error(`[ml] el servicio respondió status=${res.status}`);
      if (res.status === 503) {
        throw new AppError('ML_SERVICE_UNAVAILABLE', 'El servicio de Machine Learning no está disponible', 503);
      }
      throw new AppError('ML_SERVICE_ERROR', 'Error en el servicio de Machine Learning', 502);
    }

    const parsed = PredictionSchema.safeParse(await res.json().catch(() => null));
    if (!parsed.success) {
      throw new AppError('ML_INVALID_OUTPUT', 'El servicio de Machine Learning devolvió un formato inválido', 502);
    }
    return parsed.data;
  }

  return { analyze };
}

const defaultEngine = createMlEngine();
export const analyze = defaultEngine.analyze;
