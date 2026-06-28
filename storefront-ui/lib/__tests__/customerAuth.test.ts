import { describe, it, expect, vi, beforeEach } from 'vitest'

const customerLogin = vi.fn()
const customerRegister = vi.fn()
const customerMe = vi.fn()
const customerLogout = vi.fn()

vi.mock('@/lib/api', () => ({
  api: {
    customerLogin: (...a: any[]) => customerLogin(...a),
    customerRegister: (...a: any[]) => customerRegister(...a),
    customerMe: (...a: any[]) => customerMe(...a),
    customerLogout: (...a: any[]) => customerLogout(...a),
  },
  ApiError: class ApiError extends Error { status = 401 },
}))

import { useCustomer } from '@/lib/customerAuth'

beforeEach(() => {
  useCustomer.setState({ customer: null, slug: null, loading: true })
  vi.clearAllMocks()
})

describe('useCustomer', () => {
  it('init sets customer when signed in', async () => {
    customerMe.mockResolvedValue({ id: 'c1', name: 'Ada', store_slug: 'haree' })
    await useCustomer.getState().init('haree')
    expect(useCustomer.getState().customer?.name).toBe('Ada')
    expect(useCustomer.getState().loading).toBe(false)
  })

  it('init leaves customer null for a guest (401)', async () => {
    customerMe.mockRejectedValue(Object.assign(new Error('x'), { status: 401 }))
    await useCustomer.getState().init('haree')
    expect(useCustomer.getState().customer).toBeNull()
  })

  it('login stores the returned customer', async () => {
    customerLogin.mockResolvedValue({ id: 'c2', name: 'Grace', store_slug: 'haree' })
    await useCustomer.getState().login('haree', 'g@x.com', 'password123')
    expect(useCustomer.getState().customer?.name).toBe('Grace')
    expect(customerLogin).toHaveBeenCalledWith('haree', { email: 'g@x.com', password: 'password123' })
  })

  it('logout clears the customer', async () => {
    useCustomer.setState({ customer: { id: 'c', name: 'X' } as any, slug: 'haree' })
    customerLogout.mockResolvedValue({ status: 'logged_out' })
    await useCustomer.getState().logout()
    expect(useCustomer.getState().customer).toBeNull()
  })
})
