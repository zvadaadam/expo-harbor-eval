import { createStore } from 'zustand/vanilla'
import type { Draft } from './schema'

export function blankDraft(id: string): Draft {
  return {
    id,
    revision: 0,
    title: '',
    slug: '',
    category: 'expo-feedback',
    difficulty: 'medium',
    motivation: '',
    instruction: '',
    sourceTask: null,
    simulator: null,
    scoring: { aggregation: 'weighted-mean', threshold: 0.5 },
    criteria: [
      {
        id: 'check-1',
        name: 'check-1',
        description: '',
        weight: 1,
        grading: { kind: 'ai-review', config: {} },
      },
    ],
    files: [
      {
        area: 'environment',
        path: 'App.tsx',
        content:
          'import { Text, View } from "react-native";\n\nexport default function App() {\n  return <View><Text>Starting application</Text></View>;\n}\n',
      },
      { area: 'reference', path: 'App.tsx', content: '' },
      { area: 'distractor', path: 'App.tsx', content: '' },
    ],
    mustFail: ['check-1'],
    baselineMustFail: ['check-1'],
    updatedAt: '',
  }
}
export function createEditorStore(initial: Draft) {
  return createStore<{
    draft: Draft
    dirty: boolean
    patch: (patch: Partial<Draft>) => void
    saved: (draft: Draft) => void
  }>((set) => ({
    draft: initial,
    dirty: false,
    patch: (patch) => set((state) => ({ draft: { ...state.draft, ...patch }, dirty: true })),
    saved: (draft) => set({ draft, dirty: false }),
  }))
}
