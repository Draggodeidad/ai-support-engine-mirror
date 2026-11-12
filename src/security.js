// Capa de seguridad compartida por ambos motores.
// 1) Redacta secretos antes de enviarlos a un proveedor externo o devolverlos.
// 2) Detecta indicios de incidentes de seguridad e intentos de prompt injection.
// 3) Aplica la política final: revisión humana y prioridad mínima para SECURITY.

export function normalize(text) {
  return text.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase();
}

// Patrones de secretos que un usuario podría pegar en su solicitud.
const SECRET_PATTERNS = [
  [/AIza[0-9A-Za-z_-]{35}/g, '[API_KEY]'], // Google
  [/\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{16,}/g, '[API_KEY]'], // OpenAI / Anthropic
  [/\bgh[pousr]_[A-Za-z0-9]{30,}/g, '[TOKEN]'], // GitHub
  [/\bAKIA[0-9A-Z]{16}\b/g, '[AWS_KEY]'],
  [/\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}/g, '[JWT]'],
  [/\bBearer\s+[A-Za-z0-9._~+/-]{16,}=*/gi, 'Bearer [TOKEN]'],
  [/\b(?:\d[ -]?){13,19}\b/g, '[NUMERO_TARJETA]'],
  // "contraseña: xxx", "password=xxx", "token: xxx"
  [/\b(contrase(?:ñ|n)a|password|passwd|clave|pin|token|api[_ -]?key|secret)(\s*[:=]\s*)(\S+)/gi, '$1$2[REDACTADO]'],
  // "mi contraseña es Abc123!" (solo si el valor parece un secreto: >=6 chars con dígito o símbolo,
  // para no redactar frases como "mi contraseña es incorrecta")
  [/\b(contrase(?:ñ|n)a|password|clave|pin)(\s+es\s+)(?=\S*[\d!@#$%^&*_.-])(\S{6,})/gi, '$1$2[REDACTADO]'],
];

export function redactSecrets(text) {
  return SECRET_PATTERNS.reduce((acc, [re, repl]) => acc.replace(re, repl), text);
}

// Indicios de un posible incidente de seguridad (texto normalizado, sin acentos).
const SECURITY_INDICATORS = [
  /vulnerab/, /inyeccion/, /injection/, /\bxss\b/, /\bcsrf\b/, /exploit/, /\brce\b/,
  /hacke/, /hackea/, /\bhack/, /ataque/, /malware/, /ransomware/, /phishing/, /\bvirus\b/, /troyano/,
  /filtra(?:cion|do|da|ron)/, /fuga de (?:datos|informacion)/, /brecha/, /datos expuestos/, /expuest[oa]s? (?:publicamente|en internet)/,
  /acceso no autorizado/, /sin autorizacion/, /suplant/, /robo de (?:cuenta|datos|credenciales)/, /robaron/, /me (?:hackearon|robaron)/,
  /credenciales (?:expuestas|filtradas|comprometidas)/, /comprometid[oa]/, /ddos/, /fuerza bruta/, /escalada de privilegios/,
  /alguien (?:entro|accedio|inicio sesion) (?:a|en) mi cuenta/, /actividad sospechosa/,
];

// Intentos de manipular al clasificador (prompt injection / jailbreak).
const INJECTION_PATTERNS = [
  /ignora(?:r)? (?:todas? )?(?:las |tus )?(?:instrucciones|reglas|indicaciones)/,
  /olvida(?:r)? (?:todas? )?(?:las |tus )?(?:instrucciones|reglas)/,
  /ignore (?:all |any )?(?:previous|prior|above) (?:instructions|rules)/,
  /disregard (?:all |the )?(?:previous|prior|above)/,
  /(?:clasifica|marca|categoriza|asigna)(?:la|lo|le)?\b[^.]{0,40}?\b(?:como|con) (?:prioridad|categoria|low|medium|high|critical|access|bug|feature|security|baja|media|alta)/,
  /olvida(?:r)? (?:todo|lo anterior)/,
  /\b(?:prioridad|priority|categoria|category)\s*[:=]?\s*(?:low|medium|high|critical|access|bug|feature|security)\b/,
  /\bsin revision(?: humana)?\b/,
  /(?:prioridad|priority) (?:baja|low)(?: por favor)?[,.]? (?:aunque|aun si|even if)/,
  /\b(?:system prompt|prompt del sistema|instrucciones del sistema)\b/,
  /(?:actua|actuar|act) (?:como|as) (?:si|if|un|una|an?)\b/,
  /responde (?:solo|unicamente) con/,
  /requireshumanreview\s*[:=]?\s*false/,
  /<\/?\s*(?:solicitud|system|instructions?)\s*>/,
  /"(?:category|priority)"\s*:/,
];

export function detectSecurityIndicators(message) {
  const n = normalize(message);
  return SECURITY_INDICATORS.some((re) => re.test(n));
}

export function detectPromptInjection(message) {
  const n = normalize(message);
  return INJECTION_PATTERNS.some((re) => re.test(n));
}

// Respuestas que piden al usuario una contraseña, token o código (nunca deben enviarse).
// Se ignoran las frases negadas ("no comparta su contraseña", "sin compartir su clave").
const CREDENTIAL_REQUEST =
  /\b(proporciona(?:nos)?|proporcione(?:nos)?|envia(?:nos)?|envie(?:nos)?|enviar|comparte|comparta|compartir|indica(?:nos)?|indique(?:nos)?|escribe|escriba|facilita|facilite|dame|danos|confirma|confirme|ingresa|ingrese)\b[^.,;:?!]{0,40}?\b(contrasena|password|clave|codigo de verificacion|token|pin)\b/g;
const NEGATION_BEFORE = /\b(no|nunca|jamas|sin|ni)\s+(?:\w+\s+)?$/;

export function detectCredentialRequest(response) {
  const n = normalize(response);
  for (const m of n.matchAll(CREDENTIAL_REQUEST)) {
    const negated = NEGATION_BEFORE.test(n.slice(Math.max(0, m.index - 20), m.index)) || /\b(no|nunca|jamas|sin)\b/.test(m[0]);
    if (!negated) return true;
  }
  return false;
}

// Textos fijos que sustituyen una respuesta comprometida. No dependen del modelo.
export const SAFE_RESPONSES = {
  promptInjection:
    'Hemos recibido su solicitud y la escalamos a un agente para revisión humana. La clasificación no puede modificarse desde el mensaje y nunca le pediremos su contraseña.',
  credentialRequest:
    'Un agente revisará su caso y le indicará los siguientes pasos. Por su seguridad, nunca comparta su contraseña, tokens ni códigos de verificación con nadie, incluido nuestro equipo.',
};

const PRIORITY_ORDER = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'];
const atLeast = (priority, min) =>
  PRIORITY_ORDER.indexOf(priority) >= PRIORITY_ORDER.indexOf(min) ? priority : min;

/**
 * Política final aplicada a la salida de cualquier motor.
 * No cambia la categoría (eso es decisión del motor); endurece revisión y prioridad y
 * sustituye el texto de la respuesta si pudo ser manipulado o pide credenciales.
 * Devuelve { result, flags } donde flags explica qué ajustó la política.
 */
export function applySecurityPolicy(message, engineResult) {
  const flags = {
    securityIndicators: detectSecurityIndicators(message),
    promptInjection: detectPromptInjection(message),
    adjusted: [],
  };
  const result = { ...engineResult, response: redactSecrets(engineResult.response) };

  if (result.category === 'SECURITY') {
    const p = atLeast(result.priority, 'HIGH');
    if (p !== result.priority) flags.adjusted.push(`priority ${result.priority}->${p}`);
    result.priority = p;
  }

  const mustReview = result.category === 'SECURITY' || flags.securityIndicators || flags.promptInjection;
  if (mustReview && !result.requiresHumanReview) {
    flags.adjusted.push('requiresHumanReview false->true');
    result.requiresHumanReview = true;
  }

  // Si hubo intento de manipulación, el texto del modelo puede reflejarla
  // (p. ej. "se clasificará con prioridad baja"): se usa una respuesta fija.
  if (flags.promptInjection) {
    if (result.response !== SAFE_RESPONSES.promptInjection) flags.adjusted.push('response replaced (prompt injection)');
    result.response = SAFE_RESPONSES.promptInjection;
  } else if (detectCredentialRequest(result.response)) {
    // Nunca se pide al usuario una contraseña, token o código.
    flags.adjusted.push('response replaced (credential request)');
    result.response = SAFE_RESPONSES.credentialRequest;
    result.requiresHumanReview = true;
  }

  return { result, flags };
}
