import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, request, setToken } from './api'

const mockFetch = (res: Partial<Response> & { json?: () => Promise<unknown> }) =>
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200, ...res }))

afterEach(() => { vi.unstubAllGlobals(); setToken(null) })

describe('api client', () => {
  it('sends the bearer token and JSON body', async () => {
    setToken('tok')
    mockFetch({ json: async () => ({ ok: 1 }) })
    await request('POST', '/x', { a: 1 })
    const [url, init] = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(url).toBe('/api/x')
    expect(init.headers.Authorization).toBe('Bearer tok')
    expect(init.body).toBe('{"a":1}')
  })

  it('turns FastAPI validation errors into readable messages', async () => {
    mockFetch({ ok: false, status: 422, json: async () => ({ detail: [{ loc: ['body', 'budget'], msg: 'Input should be greater than or equal to 0' }] }) })
    await expect(request('POST', '/trips', {})).rejects.toMatchObject({ status: 422, message: 'budget: Input should be greater than or equal to 0' })
  })

  it('keeps structured 409 details for the confirm flow', async () => {
    mockFetch({ ok: false, status: 409, json: async () => ({ detail: { message: 'needs confirmation', manual_stops: ['A'] } }) })
    const err = (await request('POST', '/trips/1/optimize', {}).catch((e: unknown) => e)) as ApiError & { detail: { manual_stops: string[] } }
    expect(err).toBeInstanceOf(ApiError)
    expect(err.detail.manual_stops).toEqual(['A'])
    expect(err.message).toBe('needs confirmation')
  })

  it('reports network failures plainly', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('failed')))
    await expect(request('GET', '/trips')).rejects.toMatchObject({ status: 0, message: expect.stringMatching(/Cannot reach/) })
  })

  it('handles 204 and non-JSON error bodies', async () => {
    mockFetch({ status: 204 })
    await expect(request('DELETE', '/trips/1')).resolves.toBeUndefined()
    mockFetch({ ok: false, status: 502, json: async () => { throw new Error('html') } })
    await expect(request('GET', '/trips')).rejects.toMatchObject({ status: 502, message: 'Request failed' })
  })
})
