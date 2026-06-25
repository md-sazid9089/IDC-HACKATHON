const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function apiBase() {
  return API_URL.replace(/\/+$/, '');
}

export class HFError extends Error {
  constructor({ status = 500, model = 'backend', message = 'Inference failed' } = {}) {
    super(`[Inference ${status}] ${model}: ${message}`);
    this.name = 'HFError';
    this.status = status;
    this.model = model;
  }
}

async function arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  const chunkSize = 0x8000;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
  }
  return btoa(binary);
}

export async function analyzeExpression(imageBuffer) {
  const image = imageBuffer instanceof ArrayBuffer
    ? await arrayBufferToBase64(imageBuffer)
    : imageBuffer;
  const res = await fetch(`${apiBase()}/analyze-expression`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image }),
  });
  if (!res.ok) {
    throw new HFError({
      status: res.status,
      model: 'expression-analysis',
      message: await res.text().catch(() => res.statusText),
    });
  }
  const data = await res.json();
  return data.emotions || [];
}

export async function query(text) {
  const res = await fetch(`${apiBase()}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: text || '' }),
  });
  if (!res.ok) throw new Error(`Backend query failed: ${res.status}`);
  return res.json();
}

export async function hfInference(_model, payload, taskType) {
  if (taskType === 'image-classification') {
    return analyzeExpression(payload);
  }
  if (taskType === 'feature-extraction') {
    const inputs = Array.isArray(payload?.inputs) ? payload.inputs : [payload?.inputs || ''];
    return inputs.map(() => [0]);
  }
  if (taskType === 'text-classification') {
    const inputs = Array.isArray(payload?.inputs) ? payload.inputs : [];
    return inputs.map(() => [{ label: 'score', score: 0 }]);
  }
  return query(typeof payload === 'string' ? payload : payload?.inputs || payload?.message || '');
}

export const hfClient = null;

export default { query, analyzeExpression, hfInference };
