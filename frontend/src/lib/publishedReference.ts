export const PUBLISHED_6B03_REFERENCE = {
  source: 'GE Vernova 2025 Gas Power catalog, 6B.03 table',
  caveat: 'Published ratings at ISO conditions on natural gas. The synthetic replay is not calibrated to these values; model geometry is conceptual, not a dimensioned OEM layout.',
  values: [
    { label: 'Net output', value: '45', unit: 'MW' },
    { label: 'LHV efficiency', value: '33.4', unit: '%' },
    { label: 'Pressure ratio', value: '12.8:1', unit: '' },
    { label: 'Exhaust temperature', value: '561', unit: '°C' },
    { label: 'Exhaust flow', value: '145.1', unit: 'kg/s' },
  ],
} as const
