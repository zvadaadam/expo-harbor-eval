import { z } from 'zod'
import { graders, gradingSchema, scoringSchema } from './grading'

export const taskIdSchema = z
  .string()
  .min(1)
  .max(160)
  .regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/)
export const localIdSchema = z.uuid()
export const criterionSchema = z.object({
  id: z
    .string()
    .min(1)
    .max(100)
    .regex(/^[a-z0-9-]+$/),
  name: z.string().min(1).max(160),
  description: z.string().max(8000),
  weight: z.number().min(-100).max(100).default(1),
  type: z.enum(['binary', 'likert', 'numeric']).optional(),
  points: z.number().int().min(2).max(100).optional(),
  min: z.number().optional(),
  max: z.number().optional(),
  negate: z.boolean().optional(),
  optional: z.boolean().optional(),
  grading: gradingSchema,
})
export const filePathSchema = z
  .string()
  .min(1)
  .max(200)
  .refine(
    (path) =>
      !path.startsWith('/') &&
      !path.includes('\\') &&
      !path.includes('\0') &&
      path.split('/').every((part) => !!part && part !== '..' && !part.startsWith('.')),
    'Use a relative path without hidden files or parent directories.',
  )
export const draftFileSchema = z.object({
  area: z.enum(['environment', 'reference', 'distractor', 'checks']),
  path: filePathSchema,
  content: z.string().max(200_000),
})
export const draftSchema = z
  .object({
    id: localIdSchema,
    revision: z.number().int().min(0),
    title: z.string().max(180),
    slug: z
      .string()
      .max(120)
      .regex(/^[a-z0-9-]*$/),
    category: z.enum(['expo-feedback', 'expo-sdk', 'expo-router', 'expo-ui', 'simbench']),
    difficulty: z.enum(['easy', 'medium', 'hard', 'mixed']),
    motivation: z.string().max(12000),
    instruction: z.string().max(30000),
    sourceTask: taskIdSchema.nullable(),
    simulator: z
      .object({
        template: taskIdSchema,
        fingerprint: z.string().regex(/^[a-f0-9]{64}$/),
        tier: z.string().max(100),
      })
      .nullable()
      .default(null),
    scoring: scoringSchema,
    criteria: z.array(criterionSchema).max(24),
    files: z.array(draftFileSchema).max(100),
    mustFail: z.array(z.string().max(100)).max(24),
    baselineMustFail: z.array(z.string().max(100)).max(24).default([]),
    updatedAt: z.string(),
  })
  .superRefine((draft, ctx) => {
    for (const [key, values] of [
      ['files', draft.files.map((f) => `${f.area}/${f.path}`)],
      ['criteria', draft.criteria.map((c) => c.id)],
    ] as const) {
      if (new Set(values).size !== values.length)
        ctx.addIssue({ code: 'custom', path: [key], message: `Duplicate ${key} are not allowed.` })
    }
    if (JSON.stringify(draft.files).length > 1_500_000)
      ctx.addIssue({ code: 'custom', path: ['files'], message: 'Keep draft files under 1.5 MB.' })
  })
export type Draft = z.infer<typeof draftSchema>
export const taskEditSchema = z.object({
  draft: draftSchema,
  fingerprint: z.string().regex(/^[a-f0-9]{64}$/),
  family: z.enum(['expo-codegen', 'simbench']),
  protectedGrading: z.boolean(),
  policyCriteria: z.array(z.string()).default([]),
})
export type TaskEdit = z.infer<typeof taskEditSchema>

export function draftIssues(draft: Draft): string[] {
  const issues: string[] = []
  if (!draft.title.trim()) issues.push('Give the task a title.')
  if (!taskIdSchema.safeParse(draft.slug).success)
    issues.push('Choose a task ID using lowercase words and hyphens.')
  if (draft.instruction.trim().length < 40)
    issues.push('Describe the starting problem and expected behavior in the prompt.')
  if (!draft.motivation.trim()) issues.push('Explain why this task matters.')
  if (draft.category === 'simbench') {
    if (!draft.simulator) issues.push('Choose a simulator scenario to start from.')
    for (const [area, path] of [
      ['checks', 'verify.py'],
      ['reference', 'oracle.py'],
    ] as const) {
      if (
        !draft.files.some((file) => file.area === area && file.path === path && file.content.trim())
      )
        issues.push(
          `Add the simulator ${area === 'checks' ? 'verifier' : 'reference automation'} (${path}).`,
        )
    }
    if (
      !draft.files.some(
        (f) => f.area === 'environment' && f.path === 'app-src/Info.plist' && f.content.trim(),
      ) ||
      !draft.files.some(
        (f) => f.area === 'environment' && f.path.endsWith('.swift') && f.content.trim(),
      )
    )
      issues.push('Keep the simulator app source and Info.plist.')
    return issues
  }
  if (!draft.criteria.length || draft.criteria.some((c) => !c.description.trim()))
    issues.push('Describe at least one acceptance check.')
  for (const [index, criterion] of draft.criteria.entries()) {
    const { kind, config } = criterion.grading
    for (const field of graders[kind].fields) {
      const value = config[field.key] ?? field.default ?? ''
      const label = `Check ${index + 1}: ${field.label}`
      if (!value.trim() && !field.allowEmpty) {
        if (field.optional) continue
        issues.push(`${label} is required.`)
        continue
      }
      if (
        ['path', 'script', 'python'].includes(field.type) &&
        !filePathSchema.safeParse(value).success
      )
        issues.push(`${label} must be a relative path without hidden or parent directories.`)
      if (field.type === 'json' || field.type === 'column') {
        try {
          const parsed = JSON.parse(value)
          if (
            field.type === 'column' &&
            !(
              (typeof parsed === 'string' && parsed.length) ||
              (Number.isInteger(parsed) && parsed >= 0)
            )
          )
            issues.push(`${label} must be a column index or quoted heading.`)
        } catch {
          issues.push(`${label} must be valid JSON.`)
        }
      }
      if (
        ['script', 'python'].includes(field.type) &&
        (!(field.type === 'python' ? /\.py$/ : /\.(cjs|py)$/).test(value) ||
          !draft.files.some((f) => f.area === 'checks' && f.path === value && f.content.trim()))
      )
        issues.push(`${label} needs a .cjs or .py file in Test files.`)
      if (['integer', 'number'].includes(field.type)) {
        const number = Number(value)
        if (
          !Number.isFinite(number) ||
          (field.type === 'integer' && !Number.isInteger(number)) ||
          number < (field.min ?? -Infinity) ||
          number > (field.max ?? Infinity)
        )
          issues.push(`${label} must be a valid ${field.type} in range.`)
      }
      if (
        field.type === 'trajectory' &&
        value !== '/logs/agent/trajectory.json' &&
        !filePathSchema.safeParse(value).success
      )
        issues.push(`${label} must be the Harbor trajectory or a relative Test files path.`)
      if (field.type === 'url') {
        try {
          if (!['http:', 'https:'].includes(new URL(value).protocol)) throw new Error()
        } catch {
          issues.push(`${label} must use http:// or https://.`)
        }
      }
      if (field.type === 'identifier' && !/^[A-Za-z_][A-Za-z0-9_]*$/.test(value))
        issues.push(`${label} must be a Python function name.`)
    }
    if (!/^[a-zA-Z0-9_-]{1,64}$/.test(criterion.name))
      issues.push(
        `Check ${index + 1}: the internal name must use letters, numbers, underscores or hyphens (64 characters maximum).`,
      )
  }
  if (draft.criteria.some((c) => c.weight < 0) && draft.scoring.aggregation !== 'weighted-sum')
    issues.push('Negative weights require weighted sum scoring.')
  if (draft.scoring.aggregation === 'required-pass' && draft.criteria.every((c) => c.optional))
    issues.push('Mark at least one check as required.')
  if (
    ['weighted-mean', 'weighted-sum', 'threshold'].includes(draft.scoring.aggregation) &&
    draft.criteria.length &&
    draft.criteria.every((c) => c.weight === 0)
  )
    issues.push('Give at least one check a nonzero weight.')
  if (draft.criteria.some((c) => c.type === 'numeric' && (c.max ?? 1) <= (c.min ?? 0)))
    issues.push('Numeric score maximum must exceed its minimum.')
  for (const area of ['environment', 'reference', 'distractor'] as const) {
    if (!draft.files.some((f) => f.area === area && f.content.trim()))
      issues.push(`Add ${area === 'environment' ? 'starting' : area} code.`)
  }
  if (
    !draft.files.some(
      (f) => f.area === 'environment' && f.path.endsWith('.tsx') && f.content.trim(),
    )
  )
    issues.push(
      'Include a TSX starting file; the current calibration harness requires it for the commented-baseline control.',
    )
  if (
    !draft.mustFail.length ||
    draft.mustFail.some((id) => !draft.criteria.some((c) => c.id === id))
  )
    issues.push('Select the checks that must reject the wrong fix.')
  if (
    !draft.baselineMustFail.length ||
    draft.baselineMustFail.some((id) => !draft.criteria.some((c) => c.id === id))
  )
    issues.push(
      'Select the checks that must reject the unchanged behavior in the commented baseline.',
    )
  if (
    draft.files.some((f) =>
      ['Dockerfile', 'docker-compose.yml', 'docker-compose.yaml'].includes(
        f.path.split('/').at(-1)!,
      ),
    )
  )
    issues.push('Remove Docker files; the export uses the repository’s managed environment.')
  return issues
}

export const taskSchema = z.object({
  id: z.string(),
  title: z.string(),
  description: z.string(),
  family: z.string(),
  category: z.string(),
  difficulty: z.string(),
  tier: z.string(),
  motivation: z.string(),
  validation: z.string(),
  validationNote: z.string(),
  held: z.boolean(),
  measurements: z.array(z.string()),
  checks: z.number(),
  hasReference: z.boolean(),
  hasDistractor: z.boolean(),
  path: z.string(),
})
export type Task = z.infer<typeof taskSchema>
export const taskDetailSchema = taskSchema.extend({
  instruction: z.string(),
  criteria: z.array(criterionSchema),
  files: z.array(z.object({ area: z.string(), path: z.string(), bytes: z.number() })),
  calibration: z.record(z.string(), z.json()),
  policyCriteria: z.array(z.string()).default([]),
  scoring: scoringSchema,
})
export type TaskDetail = z.infer<typeof taskDetailSchema>
export const checkSchema = z.object({
  name: z.string(),
  passed: z.boolean().nullable(),
  detail: z.string(),
})
export const trialSchema = z.object({
  id: z.string(),
  name: z.string(),
  task: z.string(),
  run: z.string(),
  agent: z.string(),
  model: z.string(),
  reward: z.number().nullable(),
  outcome: z.enum(['pending', 'error', 'pass', 'fail', 'partial']),
  error: z.string().nullable(),
  measurement: z.string(),
  backend: z.string(),
  cost: z.number().nullable(),
  inputTokens: z.number().nullable(),
  outputTokens: z.number().nullable(),
  regradeOf: z.string(),
  startedAt: z.string(),
  finishedAt: z.string(),
  checks: z.array(checkSchema),
  provenance: z.record(z.string(), z.json()),
})
export type Trial = z.infer<typeof trialSchema>
export const trialDetailSchema = trialSchema.extend({
  artifacts: z.array(z.object({ path: z.string(), bytes: z.number() })),
})
export const catalogSchema = z.object({ tasks: z.array(taskSchema), warnings: z.array(z.string()) })
export const runsSchema = z.object({ trials: z.array(trialSchema), warnings: z.array(z.string()) })
export const fileContentSchema = z.object({
  content: z.string(),
  kind: z.enum(['text', 'image']),
  truncated: z.boolean(),
})
export const actionSchema = z.enum(['guards', 'policy', 'harbor'])
export const jobPlanSchema = z.object({ task: taskIdSchema, action: actionSchema })
export type JobPlan = z.infer<typeof jobPlanSchema>
export const jobSchema = jobPlanSchema.extend({
  id: localIdSchema,
  status: z.enum(['queued', 'running', 'completed', 'failed', 'cancelled', 'interrupted']),
  createdAt: z.string(),
  finishedAt: z.string().optional(),
  exitCode: z.number().nullable().optional(),
  message: z.string().optional(),
})
export type Job = z.infer<typeof jobSchema>
export const modelPlanSchema = z.object({
  task: taskIdSchema,
  effort: z.enum(['low', 'medium', 'high']),
  attempts: z.number().int().min(1).max(3),
})
