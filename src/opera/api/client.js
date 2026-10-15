import { readOperaConfig } from '../config.js';
import {
  buildMockAnalysis,
  buildMockPlay,
  hashBytes,
  mockBenchmarkDatasets,
  mockBenchmarkRounds,
} from './mockFixtures.js';
import { gameScore, haversineKm } from '../benchmark/geo.js';

export class OperaApiError extends Error {
  constructor(message, { status = 0, detail = null } = {}) {
    super(message);
    this.name = 'OperaApiError';
    this.status = status;
    this.detail = detail;
  }
}

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * REST client for the OPERA backend. With `mock: true` (VITE_OPERA_MOCK=1) it
 * serves deterministic MOCK fixtures and never touches the network.
 */
export function createOperaClient({
  config = readOperaConfig(),
  fetchImpl = (...args) => globalThis.fetch(...args),
  mockDelayMs = 350,
  now = () => new Date(),
} = {}) {
  const mockStore = new Map();

  async function request(
    path,
    { method = 'GET', body, headers = {}, signal } = {},
  ) {
    let response;
    try {
      response = await fetchImpl(`${config.apiUrl}${path}`, {
        method,
        body,
        signal,
        headers: { 'X-OPERA-Key': config.apiKey, ...headers },
      });
    } catch (error) {
      if (error?.name === 'AbortError') throw error;
      throw new OperaApiError('Could not reach the OPERA backend.', {
        detail: String(error),
      });
    }
    if (response.status === 204) return null;
    let payload = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
    if (!response.ok) {
      const detail = payload?.detail;
      throw new OperaApiError(
        typeof detail === 'string'
          ? detail
          : `Request failed (${response.status}).`,
        { status: response.status, detail },
      );
    }
    return payload;
  }

  return {
    mock: config.mock,

    async analyze(
      file,
      { model = 'geoclip-v1', useVlmClues = true, signal } = {},
    ) {
      if (config.mock) {
        await delay(mockDelayMs);
        if (signal?.aborted) throw new DOMException('Aborted', 'AbortError');
        const bytes = new Uint8Array(await file.slice(0, 65536).arrayBuffer());
        const analysis = buildMockAnalysis({
          seed: hashBytes(bytes, file.size),
          name: file.name,
          now: now(),
        });
        mockStore.set(analysis.id, analysis);
        return analysis;
      }
      const form = new FormData();
      form.append('image', file, file.name);
      form.append('model', model);
      form.append('use_vlm_clues', String(useVlmClues));
      form.append('metadata_free', 'true');
      form.append('rights_attested', 'true');
      const result = await request('/api/v1/analyze', {
        method: 'POST',
        body: form,
        signal,
      });
      if (result?.candidates || result?.status === 'abstained') return result;
      return request(
        `/api/v1/analyses/${encodeURIComponent(result.analysis_id)}`,
        { signal },
      );
    },

    async getAnalysis(id, { signal } = {}) {
      if (config.mock) {
        const found = mockStore.get(id);
        if (!found)
          throw new OperaApiError('Analysis not found.', { status: 404 });
        return found;
      }
      return request(`/api/v1/analyses/${encodeURIComponent(id)}`, { signal });
    },

    async deleteAnalysis(id) {
      if (config.mock) {
        mockStore.delete(id);
        return null;
      }
      return request(`/api/v1/analyses/${encodeURIComponent(id)}`, {
        method: 'DELETE',
      });
    },

    listBenchmarkDatasets: () =>
      config.mock
        ? Promise.resolve(mockBenchmarkDatasets())
        : request('/api/v1/benchmark/datasets'),

    async benchmarkRounds({ dataset, split = 'heldout', n = 5, seed = 0 }) {
      if (config.mock) return mockBenchmarkRounds({ n });
      const query = new URLSearchParams({
        dataset,
        split,
        n: String(n),
        seed: String(seed),
      });
      return request(`/api/v1/benchmark/rounds?${query}`);
    },

    /** Resolves to an object URL (or data URL in mock mode); the caller revokes it with `revokeImage`. */
    async benchmarkImage(imageUrl, { signal } = {}) {
      if (config.mock) return imageUrl;
      let response;
      try {
        response = await fetchImpl(`${config.apiUrl}${imageUrl}`, {
          signal,
          headers: { 'X-OPERA-Key': config.apiKey },
        });
      } catch (error) {
        if (error?.name === 'AbortError') throw error;
        throw new OperaApiError('Could not load the benchmark image.');
      }
      if (!response.ok)
        throw new OperaApiError(
          `Could not load the benchmark image (${response.status}).`,
          { status: response.status },
        );
      return URL.createObjectURL(await response.blob());
    },
    revokeImage(url) {
      if (typeof url === 'string' && url.startsWith('blob:'))
        URL.revokeObjectURL(url);
    },

    async benchmarkPlay({ dataset, imageId, model, guess }, { signal } = {}) {
      if (config.mock) {
        await delay(mockDelayMs);
        return buildMockPlay({ imageId, guess, haversineKm, gameScore });
      }
      return request('/api/v1/benchmark/play', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          dataset,
          image_id: imageId,
          model,
          guess: guess ?? null,
        }),
        signal,
      });
    },

    health: () =>
      config.mock
        ? Promise.resolve({ status: 'mock', adapters: { mock: 'ready' } })
        : request('/api/health'),
    listModels: () =>
      config.mock ? Promise.resolve([]) : request('/api/v1/models'),
    listDatasets: () =>
      config.mock ? Promise.resolve([]) : request('/api/v1/datasets'),
  };
}
