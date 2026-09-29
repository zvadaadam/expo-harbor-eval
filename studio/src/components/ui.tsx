import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Link } from '@tanstack/react-router'
import { AlertCircleIcon, ArrowLeftIcon, CheckCircleIcon, ClockIcon, XCircleIcon } from './icons'

export function Button({
  children,
  variant = 'secondary',
  busy,
  className = '',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'quiet' | 'danger'
  busy?: boolean
}) {
  return (
    <button
      type="button"
      {...props}
      disabled={props.disabled || busy}
      className={`button ${variant} ${className}`}
      aria-busy={busy || undefined}
    >
      {busy ? <span className="spinner" /> : null}
      {children}
    </button>
  )
}
export function Badge({
  children,
  tone = 'neutral',
  dot = false,
}: {
  children: ReactNode
  tone?: string
  dot?: boolean
}) {
  return (
    <span className={`badge ${tone}`}>
      {dot && <span className="dot" />}
      {children}
    </span>
  )
}
export function Status({ status }: { status: string }) {
  const good = status === 'pass' || status === 'completed'
  const bad = status === 'fail' || status === 'failed' || status === 'error'
  const active = status === 'running' || status === 'queued' || status === 'pending'
  const Icon = good ? CheckCircleIcon : bad ? XCircleIcon : ClockIcon
  const labels: Record<string, string> = {
    pass: 'Passed',
    fail: 'Failed',
    error: 'Execution error',
    partial: 'Partial',
    pending: 'Missing result',
    completed: 'Completed',
    failed: 'Failed',
    queued: 'Queued',
    running: 'Running',
    cancelled: 'Cancelled',
    interrupted: 'Interrupted',
  }
  return (
    <span className={`status ${good ? 'green' : bad ? 'red' : active ? 'blue' : 'neutral'}`}>
      <Icon />
      {labels[status] ?? status}
    </span>
  )
}
export function Notice({
  children,
  tone = 'info',
}: {
  children: ReactNode
  tone?: 'info' | 'warning' | 'error' | 'success'
}) {
  return (
    <div className={`notice ${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      <AlertCircleIcon />
      <div>{children}</div>
    </div>
  )
}
export function Empty({
  title,
  children,
  action,
}: {
  title: string
  children: ReactNode
  action?: ReactNode
}) {
  return (
    <div className="empty">
      <span className="empty-icon">
        <ClockIcon />
      </span>
      <h3>{title}</h3>
      <p>{children}</p>
      {action}
    </div>
  )
}
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string
  title: string
  description: string
  actions?: ReactNode
}) {
  return (
    <header className="page-header">
      <div className="page-title">
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
      </div>
      {actions && <div className="actions">{actions}</div>}
      <p className="page-description">{description}</p>
    </header>
  )
}
export function BackLink({ label = 'Task library' }: { label?: string }) {
  return (
    <Link className="back-link" to="/">
      <ArrowLeftIcon />
      {label}
    </Link>
  )
}
export function Metric({
  value,
  label,
  detail,
}: {
  value: ReactNode
  label: string
  detail?: string
}) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
      {detail && <small>{detail}</small>}
    </div>
  )
}
export const measurementNames: Record<string, string> = {
  'source-review': 'Source review',
  'source-and-checks': 'AI review + checks',
  'programmatic-checks': 'Programmatic checks',
  'source-and-policy': 'Source + policy',
  'policy-behavior': 'Policy contract',
  'native-ui': 'Native UI',
  'device-use': 'Device operation',
  'reference-smoke': 'Reference smoke',
  unversioned: 'Unversioned',
}
export const categoryNames: Record<string, string> = {
  'expo-feedback': 'Real-world fixes',
  'expo-sdk': 'Expo SDK',
  'expo-router': 'Expo Router',
  'expo-ui': 'Interface & state',
  simbench: 'Simulator tasks',
}
export function readiness(validation: string) {
  if (validation.startsWith('held')) return 'On hold'
  if (validation === 'unknown') return 'Not recorded'
  if (validation.includes('knowledge-only')) return 'Source only'
  return 'Needs calibration'
}
export function humanize(value: string) {
  return value.replaceAll('-', ' ').replace(/^./, (c) => c.toUpperCase())
}
export function count(value: number | null) {
  return value === null
    ? '—'
    : new Intl.NumberFormat('en', {
        notation: value > 9999 ? 'compact' : 'standard',
        maximumFractionDigits: 1,
      }).format(value)
}
export function date(value: string) {
  return value
    ? new Date(value).toLocaleDateString('en-GB', {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
        timeZone: 'UTC',
      })
    : 'Not recorded'
}
export function download(filename: string, content: string) {
  const url = URL.createObjectURL(new Blob([content], { type: 'application/json' }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
