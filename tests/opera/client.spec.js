import { describe, expect, it, vi } from 'vitest';
import {
  createOperaClient,
  OperaApiError,
} from '../../src/opera/api/client.js';
import { readOperaConfig } from '../../src/opera/config.js';

const jpegFile = (extra = 0, name = 'photo.jpg') =>
  new File([new Uint8Array([0xff, 0xd8, 0xff, 0xe0, extra, 1, 2, 3])], name, {
    type: 'image/jpeg',
  });

const mockClient = (fetchImpl = vi.fn()) =>
  createOperaClient({
    config: readOperaConfig({ VITE_OPERA_MOCK: '1' }),
    mockDelayMs: 0,
    fetchImpl,
    now: () => new Date('2026-01-01T00:00:00Z'),
  });

describe('mock mode', () => {
  it('is on only with VITE_OPERA_MOCK=1', () => {
    expect(readOperaConfig({}).mock).toBe(false);
    expect(readOperaConfig({ VITE_OPERA_MOCK: '1' }).mock).toBe(true);
  });
  it('returns a labelled, schema-shaped analysis without touching the network', async () => {
    const fetchImpl = vi.fn();
    const a = await mockClient(fetchImpl).analyze(jpegFile());
    expect(fetchImpl).not.toHaveBeenCalled();
    expect(a.model_kind).toBe('mock');
    expect(a.status).toBe('complete');
    expect(a.candidates).toHaveLength(5);
    expect(a.candidates.map((c) => c.rank)).toEqual([1, 2, 3, 4, 5]);
    expect(
      a.candidates.every(
        (c) =>
          c.uncalibrated &&
          c.source_model === 'mock-v1' &&
          c.label.startsWith('MOCK'),
      ),
    ).toBe(true);
    expect(
      a.candidates.every((c) =>
        ['low', 'medium', 'high'].includes(c.confidence_band),
      ),
    ).toBe(true);
    expect(a.clues.length).toBeGreaterThan(0);
    expect(a.provenance[0].kind).toBe('mock');
  });
  it('is deterministic per image content and differs between images', async () => {
    const c = mockClient();
    const [x, y, z] = [
      await c.analyze(jpegFile(1)),
      await c.analyze(jpegFile(1)),
      await c.analyze(jpegFile(9)),
    ];
    expect(x).toEqual(y);
    expect(x.id).not.toBe(z.id);
  });
  it('abstains for the demo file name', async () => {
    const a = await mockClient().analyze(jpegFile(0, 'indoor-abstain.jpg'));
    expect(a.status).toBe('abstained');
    expect(a.candidates).toEqual([]);
    expect(a.abstain_reason).toMatch(/MOCK/);
  });
  it('supports get and delete lifecycle', async () => {
    const c = mockClient();
    const a = await c.analyze(jpegFile());
    expect((await c.getAnalysis(a.id)).id).toBe(a.id);
    await c.deleteAnalysis(a.id);
    await expect(c.getAnalysis(a.id)).rejects.toMatchObject({ status: 404 });
  });
});

describe('real mode request shaping', () => {
  const config = readOperaConfig({
    VITE_OPERA_API_URL: 'http://api.test/',
    VITE_OPERA_API_KEY: 'k',
  });
  it('sends multipart with auth header and attestation', async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 202,
        json: async () => ({ analysis_id: 'abc' }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ id: 'abc', candidates: [] }),
      });
    const result = await createOperaClient({ config, fetchImpl }).analyze(
      jpegFile(),
    );
    expect(result.id).toBe('abc');
    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe('http://api.test/api/v1/analyze');
    expect(init.headers['X-OPERA-Key']).toBe('k');
    expect(init.body.get('rights_attested')).toBe('true');
    expect(init.body.get('metadata_free')).toBe('true');
  });
  it('maps network and http errors to OperaApiError', async () => {
    const down = createOperaClient({
      config,
      fetchImpl: vi.fn().mockRejectedValue(new TypeError('x')),
    });
    await expect(down.getAnalysis('a')).rejects.toBeInstanceOf(OperaApiError);
    const bad = createOperaClient({
      config,
      fetchImpl: vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: async () => ({ detail: 'bad key' }),
      }),
    });
    await expect(bad.getAnalysis('a')).rejects.toMatchObject({
      status: 401,
      message: 'bad key',
    });
  });
});
