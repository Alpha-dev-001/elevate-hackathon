import type { LayoutGlobalConfig } from '@/types/schemas'

export const RADIUS: Record<LayoutGlobalConfig['corner_radius'], string> = {
  none: '0',
  sm: '4px',
  md: '10px',
  lg: '18px',
  full: '9999px',
}
