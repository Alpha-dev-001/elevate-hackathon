import { create } from 'zustand'
import { api, ApiError } from '@/lib/api'
import type { Customer } from '@/types/schemas'

interface CustomerAuthState {
  customer: Customer | null
  slug: string | null
  loading: boolean
  init: (slug: string) => Promise<void>
  login: (slug: string, email: string, password: string) => Promise<void>
  register: (slug: string, name: string, email: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

export const useCustomer = create<CustomerAuthState>((set, get) => ({
  customer: null,
  slug: null,
  loading: true,

  init: async (slug) => {
    set({ slug, loading: true })
    try {
      const c = await api.customerMe(slug)
      set({ customer: c, loading: false })
    } catch (e) {
      // 401 = not signed in (the normal guest case), not an error to surface.
      if (!(e instanceof ApiError && (e.status === 401 || e.status === 403))) {
        // eslint-disable-next-line no-console
        console.warn('customer init failed', e)
      }
      set({ customer: null, loading: false })
    }
  },

  login: async (slug, email, password) => {
    const c = await api.customerLogin(slug, { email, password })
    set({ customer: c, slug })
  },

  register: async (slug, name, email, password) => {
    const c = await api.customerRegister(slug, { name, email, password })
    set({ customer: c, slug })
  },

  logout: async () => {
    const slug = get().slug
    if (slug) await api.customerLogout(slug).catch(() => {})
    set({ customer: null })
  },
}))
