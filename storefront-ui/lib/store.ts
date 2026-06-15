/**
 * Global onboarding state (Zustand).
 *
 * Holds the authenticated merchant and the live brand-generation phase so the
 * setup flow and the brand-review page share one source of truth. Types come
 * straight from the Zod schemas that mirror the backend's Pydantic models.
 */
import { create } from 'zustand'
import type { Merchant, BrandPackage } from '@/types/schemas'

export type OnboardingPhase =
  | 'idle' // logged in, no logo submitted yet
  | 'generating' // pipeline running, waiting on brand_ready
  | 'ready' // brand received, awaiting review/publish
  | 'failed' // generation errored
  | 'published' // store is live

interface ElevateState {
  merchant: Merchant | null
  authChecked: boolean // have we resolved the session cookie yet

  brand: BrandPackage | null
  storeShellUrl: string | null
  phase: OnboardingPhase
  error: string | null
  liveUrl: string | null

  setMerchant: (m: Merchant | null) => void
  setAuthChecked: (v: boolean) => void
  setBrand: (brand: BrandPackage, storeShellUrl: string) => void
  setPhase: (phase: OnboardingPhase) => void
  setError: (error: string | null) => void
  setLiveUrl: (url: string) => void
  resetOnboarding: () => void
}

export const useStore = create<ElevateState>((set) => ({
  merchant: null,
  authChecked: false,

  brand: null,
  storeShellUrl: null,
  phase: 'idle',
  error: null,
  liveUrl: null,

  setMerchant: (merchant) => set({ merchant }),
  setAuthChecked: (authChecked) => set({ authChecked }),
  setBrand: (brand, storeShellUrl) =>
    set({ brand, storeShellUrl, phase: 'ready', error: null }),
  setPhase: (phase) => set({ phase }),
  setError: (error) => set({ error, phase: error ? 'failed' : 'idle' }),
  setLiveUrl: (liveUrl) => set({ liveUrl, phase: 'published' }),
  resetOnboarding: () =>
    set({ brand: null, storeShellUrl: null, phase: 'idle', error: null, liveUrl: null }),
}))
