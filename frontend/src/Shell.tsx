import { useEffect, useId, useRef, useState } from 'react'
import type { RefObject } from 'react'
import type { LucideIcon } from 'lucide-react'
import {
  Activity,
  Bot,
  BookOpenText,
  Box,
  Check,
  CircleCheck,
  CircleX,
  Ellipsis,
  Gauge,
  Monitor,
  Moon,
  ShieldCheck,
  Sun,
  X,
} from 'lucide-react'
import type { EngineStatus, RoutePage, ThemePreference } from './shellLogic'
import { parseRoute, routeHash } from './app/router'
import { PUBLISHED_6B03_REFERENCE } from './lib/publishedReference'
import { Sheet } from './components/ui/Sheet'

const NAV_ITEMS: Array<{ page: RoutePage; label: string; mobileLabel: string; icon: LucideIcon }> = [
  { page: 'overview', label: 'Overview', mobileLabel: 'Overview', icon: Gauge },
  { page: 'components', label: 'Components', mobileLabel: 'Parts', icon: Box },
  { page: 'evidence', label: 'Evidence', mobileLabel: 'Evidence', icon: BookOpenText },
  { page: 'assistant', label: 'Assistant', mobileLabel: 'Assistant', icon: Bot },
]

function routeHref(page: RoutePage, selectedComponentId: string): string {
  const current = parseRoute(window.location.hash)
  const componentId = page === 'components' ? selectedComponentId as typeof current.componentId : current.componentId
  return routeHash({ ...current, page, componentId, sampleIndex: current.sampleIndex })
}

function CycleGlyph() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M2.5 21 6.5 7.5Q13 5.5 21.5 2.5L18.8 16.8Q10 20 2.5 21Z" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="2.5" cy="21" r="1.2" fill="currentColor" />
      <circle cx="6.5" cy="7.5" r="1.2" fill="currentColor" />
      <circle cx="21.5" cy="2.5" r="1.2" fill="currentColor" />
      <circle cx="18.8" cy="16.8" r="1.2" fill="currentColor" />
    </svg>
  )
}

function useDismissOnOutside(open: boolean, close: () => void, root: RefObject<HTMLElement | null>) {
  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: PointerEvent) => {
      if (event.target instanceof Node && !root.current?.contains(event.target)) close()
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close()
    }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [close, open, root])
}

function EngineStatusControl({ status, compact = false }: { status: EngineStatus; compact?: boolean }) {
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  const popoverId = `engine-status-${useId().replaceAll(':', '')}`
  const close = () => setOpen(false)
  useDismissOnOutside(open, close, root)
  const statusLabel = status === 'connected' ? 'connected' : status === 'offline' ? 'offline' : 'checking'
  const accessibleName = `Local engine · ${statusLabel}`
  const StatusIcon = status === 'connected' ? CircleCheck : status === 'offline' ? CircleX : Activity

  return (
    <div className={`utility-anchor ${compact ? 'utility-anchor-compact' : ''}`} ref={root} role={compact ? 'presentation' : undefined}>
      <button
        className="utility-button engine-button"
        type="button"
        aria-label={accessibleName}
        aria-expanded={open}
        aria-controls={popoverId}
        title={accessibleName}
        role={compact ? 'menuitem' : undefined}
        onClick={() => setOpen((value) => !value)}
      >
        <span className={`engine-indicator engine-${status}`} aria-hidden="true">
          <StatusIcon size={16} strokeWidth={1.6} />
          <span className="engine-dot" />
        </span>
        {compact && <span>{accessibleName}</span>}
      </button>
      {open && (
        <div className="utility-popover status-popover" id={popoverId} role="status">
          <StatusIcon size={16} strokeWidth={1.6} aria-hidden="true" />
          <span>{accessibleName}</span>
        </div>
      )}
    </div>
  )
}

function ThemeToggle({
  theme,
  onChange,
  compact = false,
}: {
  theme: ThemePreference
  onChange: (theme: ThemePreference) => void
  compact?: boolean
}) {
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  const menuId = `theme-menu-${useId().replaceAll(':', '')}`
  const close = () => setOpen(false)
  useDismissOnOutside(open, close, root)
  const CurrentThemeIcon = theme === 'dark' ? Moon : theme === 'light' ? Sun : Monitor

  return (
    <div className={`utility-anchor ${compact ? 'utility-anchor-compact' : ''}`} ref={root} role={compact ? 'presentation' : undefined}>
      <button
        className="utility-button theme-button"
        type="button"
        aria-label={`Theme: ${theme}`}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        title={`Theme: ${theme}`}
        role={compact ? 'menuitem' : undefined}
        onClick={() => setOpen((value) => !value)}
      >
        <CurrentThemeIcon size={16} strokeWidth={1.6} aria-hidden="true" />
        {compact && <span>Theme</span>}
      </button>
      {open && (
        <div className="utility-popover theme-popover" id={menuId} role="menu" aria-label="Theme">
          {(['system', 'light', 'dark'] as const).map((option) => {
            const Icon = option === 'system' ? Monitor : option === 'light' ? Sun : Moon
            return (
              <button
                className="theme-option"
                key={option}
                type="button"
                role="menuitemradio"
                aria-checked={theme === option}
                onClick={() => { onChange(option); close() }}
              >
                <Icon size={15} strokeWidth={1.6} aria-hidden="true" />
                <span>{option === 'system' ? 'System' : option === 'light' ? 'Light' : 'Dark'}</span>
                {theme === option && <Check size={14} aria-hidden="true" />}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

function BoundaryButton({ expanded, onClick, compact = false }: { expanded: boolean; onClick: () => void; compact?: boolean }) {
  return (
    <button
      className="utility-button boundary-button"
      type="button"
      aria-label="Boundary"
      aria-haspopup="dialog"
      aria-expanded={expanded}
      aria-controls="boundary-sheet"
      title="Boundary"
      role={compact ? 'menuitem' : undefined}
      onClick={onClick}
    >
      <ShieldCheck size={16} strokeWidth={1.6} aria-hidden="true" />
      {compact && <span>Boundary</span>}
    </button>
  )
}

function DesktopNav({ page, selectedComponentId }: { page: RoutePage; selectedComponentId: string }) {
  const renderItem = ({ page: itemPage, label, icon: Icon }: typeof NAV_ITEMS[number]) => (
    <a
      className={`rail-link ${page === itemPage ? 'is-active' : ''}`}
      href={routeHref(itemPage, selectedComponentId)}
      aria-label={label}
      aria-current={page === itemPage ? 'page' : undefined}
      key={itemPage}
    >
      <Icon size={16} strokeWidth={1.5} aria-hidden="true" />
      <span className="rail-tooltip" aria-hidden="true">{label}</span>
    </a>
  )

  return (
    <nav className="rail-nav" aria-label="Primary navigation">
      <div className="rail-nav-group">{NAV_ITEMS.slice(0, 2).map(renderItem)}</div>
      <span className="rail-separator" aria-hidden="true" />
      <div className="rail-nav-group">{NAV_ITEMS.slice(2).map(renderItem)}</div>
    </nav>
  )
}

export function IconRail({
  page,
  selectedComponentId,
  engineStatus,
  theme,
  onThemeChange,
  boundaryOpen,
  onBoundary,
}: {
  page: RoutePage
  selectedComponentId: string
  engineStatus: EngineStatus
  theme: ThemePreference
  onThemeChange: (theme: ThemePreference) => void
  boundaryOpen: boolean
  onBoundary: () => void
}) {
  return (
    <aside className="icon-rail" aria-label="TurbineIQ workspace">
      <a className="rail-brand" href="#/overview" aria-label="TurbineIQ" title="TurbineIQ">
        <CycleGlyph />
      </a>
      <DesktopNav page={page} selectedComponentId={selectedComponentId} />
      <div className="rail-utilities" aria-label="Workspace utilities">
        <EngineStatusControl status={engineStatus} />
        <ThemeToggle theme={theme} onChange={onThemeChange} />
        <BoundaryButton expanded={boundaryOpen} onClick={onBoundary} />
      </div>
    </aside>
  )
}

export function MobileBottomBar({ page, selectedComponentId }: { page: RoutePage; selectedComponentId: string }) {
  return (
    <nav className="mobile-bottom-bar" aria-label="Primary navigation">
      {NAV_ITEMS.map(({ page: itemPage, mobileLabel, icon: Icon }) => (
        <a
          className={`mobile-nav-link ${page === itemPage ? 'is-active' : ''}`}
          key={itemPage}
          href={routeHref(itemPage, selectedComponentId)}
          aria-label={mobileLabel}
          aria-current={page === itemPage ? 'page' : undefined}
        >
          <Icon size={16} strokeWidth={1.5} aria-hidden="true" />
          <span>{mobileLabel}</span>
        </a>
      ))}
    </nav>
  )
}

export function PageHeader({
  page,
  seed,
  engineStatus,
  theme,
  onThemeChange,
  boundaryOpen,
  onBoundary,
}: {
  page: RoutePage
  seed: string
  engineStatus: EngineStatus
  theme: ThemePreference
  onThemeChange: (theme: ThemePreference) => void
  boundaryOpen: boolean
  onBoundary: () => void
}) {
  const [overflowOpen, setOverflowOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  const menuId = `header-utilities-${useId().replaceAll(':', '')}`
  const close = () => setOverflowOpen(false)
  useDismissOnOutside(overflowOpen, close, root)
  const titles: Record<RoutePage, string> = {
    overview: 'Overview',
    components: 'Turbine components',
    evidence: 'Evidence',
    assistant: 'Assistant',
  }

  return (
    <header className="page-header">
      <div className="page-heading-copy">
        <div className="page-context">GE 6B.03 reference · Synthetic</div>
        <h1>{titles[page]}</h1>
      </div>
      <div className="page-header-actions">
        {page === 'evidence' && <span className="page-route-chip">Local lexical retrieval</span>}
        <button
          className="boundary-chip"
          type="button"
          aria-label={`Synthetic · seed ${seed}; open model boundary`}
          aria-haspopup="dialog"
          aria-expanded={boundaryOpen}
          aria-controls="boundary-sheet"
          onClick={onBoundary}
        >
          Synthetic · seed {seed}
        </button>
        <div className="header-overflow-anchor" ref={root}>
          <button
            className="header-overflow-button"
            type="button"
            aria-label="Workspace utilities"
            aria-haspopup="menu"
            aria-expanded={overflowOpen}
            aria-controls={menuId}
            onClick={() => setOverflowOpen((value) => !value)}
          >
            <Ellipsis size={18} aria-hidden="true" />
          </button>
          {overflowOpen && (
            <div className="header-overflow-menu" id={menuId} role="menu" aria-label="Workspace utilities">
              <EngineStatusControl status={engineStatus} compact />
              <ThemeToggle theme={theme} onChange={onThemeChange} compact />
              <BoundaryButton expanded={boundaryOpen} onClick={() => { onBoundary(); close() }} compact />
            </div>
          )}
        </div>
      </div>
    </header>
  )
}

export function BoundarySheet({
  open,
  onClose,
  seed,
  scenario,
  modelName,
  provenance,
}: {
  open: boolean
  onClose: () => void
  seed: string
  scenario: string
  modelName: string
  provenance: string
}) {
  return (
    <Sheet open={open} onClose={onClose} className="boundary-sheet" id="boundary-sheet" labelledBy="boundary-title" describedBy="boundary-lede">
      <div className="boundary-sheet-heading">
        <div>
          <div className="page-context">Data and model scope</div>
          <h2 id="boundary-title">Boundary</h2>
        </div>
        <button className="boundary-close" data-sheet-autofocus type="button" aria-label="Close boundary" onClick={onClose}><X size={17} aria-hidden="true" /></button>
      </div>
      <p className="boundary-lede" id="boundary-lede">This workspace uses synthetic operating data and a simplified open-cycle model.</p>
      <dl className="boundary-facts">
        <div><dt>Data provenance</dt><dd>{provenance}</dd></div>
        <div><dt>Model</dt><dd>{modelName} · simplified, not OEM-validated</dd></div>
        <div><dt>Connection</dt><dd>No physical connection or control.</dd></div>
        <div><dt>Seed</dt><dd className="boundary-mono">{seed}</dd></div>
        <div><dt>Scenario</dt><dd>{scenario}</dd></div>
      </dl>
      <section className="boundary-reference" aria-labelledby="boundary-reference-title">
        <h3 id="boundary-reference-title">GE 6B.03 reference</h3>
        <dl className="boundary-reference-values">
          {PUBLISHED_6B03_REFERENCE.values.map(({ label, value, unit }) => (
            <div key={label}><dt>{label}</dt><dd>{value}{unit && <span className="unit">{unit}</span>}</dd></div>
          ))}
        </dl>
        <p>{PUBLISHED_6B03_REFERENCE.caveat}</p>
      </section>
    </Sheet>
  )
}
