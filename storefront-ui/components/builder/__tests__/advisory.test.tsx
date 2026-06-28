import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ColorPicker } from '@/components/builder/ColorPicker'
import { useBuilderStore } from '@/lib/builderStore'
import { fixtureDSL } from '@/test/fixtures'
import type { BrandGuardRules } from '@/types/schemas'

const token: any = { colors: { primary: '#000000', accent: '#6EE7B7', background: '#ffffff', surface: '#eeeeee', text: '#000000', text_muted: '#999999' } }

const guards: BrandGuardRules = {
  allowed_color_palette: ['#6EE7B7'],
  forbidden_combinations: [],
  rules: [{
    rule_id: 'accent_lock', field: 'accent',
    description: 'Protects the mint accent.',
    warning_message: 'I chose #6EE7B7 to lift off your deep navy — a warm hue collapses that tension.',
  }],
}

beforeEach(() => {
  useBuilderStore.getState().reset()
  useBuilderStore.getState().setFromStore(fixtureDSL, token)
})

describe('ColorPicker brand-guard advisory', () => {
  it('shows the rule warning when accent leaves the allowed palette (no network call)', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch' as any)
    render(<ColorPicker colorKey="accent" guards={guards} advisoryMode="conversational" />)
    const hex = screen.getByTestId('hex-input') as HTMLInputElement
    await userEvent.clear(hex)
    await userEvent.type(hex, '#FF0000')
    expect(screen.getByTestId('advisory')).toHaveTextContent('collapses that tension')
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('shows no advisory for an allowed color', async () => {
    render(<ColorPicker colorKey="accent" guards={guards} advisoryMode="conversational" />)
    const hex = screen.getByTestId('hex-input') as HTMLInputElement
    await userEvent.clear(hex)
    await userEvent.type(hex, '#6EE7B7')
    expect(screen.queryByTestId('advisory')).toBeFalsy()
  })
})
