import { describe, expect, it } from 'vitest';
import {
  sniffImageType,
  validateImageContent,
  validateImageFile,
} from '../../src/opera/validation.js';

const file = (name, type, size = 1000) => ({ name, type, size });

describe('validateImageFile', () => {
  it('accepts jpg, png and webp', () => {
    expect(validateImageFile(file('a.jpg', 'image/jpeg')).ok).toBe(true);
    expect(validateImageFile(file('a.PNG', 'image/png')).ok).toBe(true);
    expect(validateImageFile(file('a.webp', 'image/webp')).ok).toBe(true);
  });
  it('rejects other types', () => {
    const r = validateImageFile(file('a.gif', 'image/gif'));
    expect(r.ok).toBe(false);
    expect(r.error).toMatch(/JPG, PNG or WebP/);
    expect(validateImageFile(file('a.pdf', 'application/pdf')).ok).toBe(false);
  });
  it('rejects oversize and empty files', () => {
    expect(
      validateImageFile(file('a.jpg', 'image/jpeg', 11 * 1024 * 1024)).error,
    ).toMatch(/too large/);
    expect(validateImageFile(file('a.jpg', 'image/jpeg', 0)).error).toMatch(
      /empty/,
    );
    expect(
      validateImageFile(file('a.jpg', 'image/jpeg', 2048), { maxBytes: 1024 })
        .ok,
    ).toBe(false);
  });
  it('rejects an extension that contradicts the type', () => {
    expect(validateImageFile(file('a.png', 'image/jpeg')).error).toMatch(
      /does not match/,
    );
  });
  it('rejects a missing file', () => {
    expect(validateImageFile(null).ok).toBe(false);
  });
});

describe('magic bytes', () => {
  const jpeg = [0xff, 0xd8, 0xff, 0xe0, 0, 0, 0, 0];
  const png = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];
  const webp = [...'RIFF']
    .map((c) => c.charCodeAt(0))
    .concat(
      [0, 0, 0, 0],
      [...'WEBP'].map((c) => c.charCodeAt(0)),
    );
  it('sniffs each supported format', () => {
    expect(sniffImageType(jpeg)).toBe('image/jpeg');
    expect(sniffImageType(png)).toBe('image/png');
    expect(sniffImageType(webp)).toBe('image/webp');
    expect(sniffImageType([1, 2, 3, 4])).toBeNull();
  });
  it('catches a spoofed file', async () => {
    const fake = new File(
      [new Uint8Array([0x25, 0x50, 0x44, 0x46, 0x2d])],
      'x.jpg',
      { type: 'image/jpeg' },
    );
    expect((await validateImageContent(fake)).ok).toBe(false);
    const real = new File([new Uint8Array(jpeg)], 'x.jpg', {
      type: 'image/jpeg',
    });
    expect((await validateImageContent(real)).ok).toBe(true);
    const mismatch = new File([new Uint8Array(png)], 'x.jpg', {
      type: 'image/jpeg',
    });
    expect((await validateImageContent(mismatch)).error).toMatch(
      /do not match/,
    );
  });
});
