import { z } from 'zod'
import catalog from '../../../graders/catalog.json'

export type GraderKind = keyof typeof catalog.checks
export type GraderField = {
  key: string
  label: string
  type: string
  placeholder: string
  optional?: boolean
  allowEmpty?: boolean
  default?: string
  min?: number
  max?: number
}
type Grader = {
  label: string
  group: string
  description: string
  builtin: string | null
  fields: GraderField[]
  score?: string
}
const kinds = Object.keys(catalog.checks) as [GraderKind, ...GraderKind[]]
export const gradingSchema = z
  .object({
    kind: z.enum(kinds),
    config: z.record(z.string(), z.string().max(8000)).default({}),
  })
  .superRefine((value, ctx) => {
    const allowed = catalog.checks[value.kind].fields.map((field) => field.key)
    if (Object.keys(value.config).some((key) => !allowed.includes(key)))
      ctx.addIssue({ code: 'custom', message: 'Unknown grader setting.' })
  })
  .default({ kind: 'ai-review', config: {} })

export const graders: Record<GraderKind, Grader> = catalog.checks
export const graderOptions = kinds.map((kind) => ({ kind, ...graders[kind] }))
export const graderGroups = [...new Set(graderOptions.map((grader) => grader.group))]
export const aggregations = catalog.aggregations
export const scoringSchema = z
  .object({
    aggregation: z
      .enum(
        Object.keys(aggregations) as [
          keyof typeof aggregations,
          ...Array<keyof typeof aggregations>,
        ],
      )
      .default('weighted-mean'),
    threshold: z.number().min(0).max(1).default(0.5),
  })
  .default({ aggregation: 'weighted-mean', threshold: 0.5 })
export const pythonCriterionTemplate = `from pathlib import Path
from rewardkit import criterion

@criterion(description="Check the submitted behavior", shared=True)
def check(workspace: Path) -> bool | float:
    # Read the submission from workspace. Return True/False or a score in [0, 1].
    raise NotImplementedError("Replace this placeholder with your check")
`
export const testScriptTemplate = `const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

// The submitted workspace is passed as the first argument.
const app = process.argv[2];
// Read or import the candidate's code from app, then assert its behavior.
// Keep these assertions here; the candidate cannot edit this test file.
assert.fail('Replace this placeholder with assertions for your task.');
`

export function taskSlug(title: string) {
  return title
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 120)
    .replace(/-$/, '')
}

export function nextCheckId(criteria: { id: string }[]) {
  let index = 1
  while (criteria.some((c) => c.id === `check-${index}`)) index++
  return `check-${index}`
}
