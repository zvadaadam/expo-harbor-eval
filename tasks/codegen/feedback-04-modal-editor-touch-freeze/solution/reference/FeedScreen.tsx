import { useState } from 'react'
import {
  FlatList,
  Modal,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native'

const INITIAL_POSTS = [
  {
    id: 'w1',
    title: 'Monday — Push',
    description: 'Bench 5x5 at RPE 8, incline dumbbell work, and a strict dip finisher.',
  },
  {
    id: 'w2',
    title: 'Wednesday — Pull',
    description: 'Deadlift triples, weighted chins, and a long row superset to close.',
  },
  {
    id: 'w3',
    title: 'Friday — Legs',
    description: 'Front squats, Bulgarian split squats, and sled pushes until done.',
  },
]

// One native presentation, one state machine. iOS allows a presenter a single
// presented controller, and RN's modal host marks itself presented before
// UIKit answers — a second sibling Modal therefore never appears but leaves
// its screen-sized, touch-claiming host mounted, which is the reported
// freeze. The editor is a content switch inside the already-presented sheet,
// so a second presentation can never be requested, and no timer needs to
// guess when a dismissal finished.
type SheetMode = 'closed' | 'viewing' | 'editing'

export default function FeedScreen() {
  const [posts, setPosts] = useState(INITIAL_POSTS)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [mode, setMode] = useState<SheetMode>('closed')
  const [draft, setDraft] = useState('')

  const selected = posts.find((post) => post.id === selectedId)

  const openPost = (id: string) => {
    setSelectedId(id)
    setMode('viewing')
  }

  const openEditor = () => {
    setDraft(selected?.description ?? '')
    setMode('editing')
  }

  const saveDraft = () => {
    setPosts((current) =>
      current.map((post) =>
        post.id === selectedId ? { ...post, description: draft } : post,
      ),
    )
    setMode('viewing')
  }

  const cancelEdit = () => {
    setMode('viewing')
  }

  const closeSheet = () => {
    setMode('closed')
  }

  return (
    <View style={styles.screen}>
      <Text style={styles.heading}>Iron Body</Text>
      <FlatList
        data={posts}
        keyExtractor={(post) => post.id}
        contentContainerStyle={styles.feed}
        renderItem={({ item }) => (
          <Pressable style={styles.card} onPress={() => openPost(item.id)}>
            <Text style={styles.cardTitle}>{item.title}</Text>
            <Text style={styles.cardCopy} numberOfLines={2}>
              {item.description}
            </Text>
          </Pressable>
        )}
      />

      <Modal
        visible={mode !== 'closed'}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => (mode === 'editing' ? cancelEdit() : closeSheet())}
      >
        {mode === 'editing' ? (
          <View style={styles.sheet}>
            <Text style={styles.sheetTitle}>Edit description</Text>
            <TextInput
              style={styles.input}
              value={draft}
              onChangeText={setDraft}
              multiline
              autoFocus
            />
            <Pressable style={styles.primaryButton} onPress={saveDraft}>
              <Text style={styles.primaryLabel}>Save</Text>
            </Pressable>
            <Pressable style={styles.secondaryButton} onPress={cancelEdit}>
              <Text style={styles.secondaryLabel}>Cancel</Text>
            </Pressable>
          </View>
        ) : (
          <View style={styles.sheet}>
            <Text style={styles.sheetTitle}>{selected?.title}</Text>
            <Text style={styles.sheetCopy}>{selected?.description}</Text>
            <Pressable style={styles.primaryButton} onPress={openEditor}>
              <Text style={styles.primaryLabel}>Edit description</Text>
            </Pressable>
            <Pressable style={styles.secondaryButton} onPress={closeSheet}>
              <Text style={styles.secondaryLabel}>Close</Text>
            </Pressable>
          </View>
        )}
      </Modal>
    </View>
  )
}

const styles = StyleSheet.create({
  screen: { flex: 1, paddingTop: 96 },
  heading: { fontSize: 28, fontWeight: '700', paddingHorizontal: 20, marginBottom: 12 },
  feed: { paddingHorizontal: 20, gap: 12 },
  card: { padding: 16, borderRadius: 12, backgroundColor: '#F2F3F5', gap: 4 },
  cardTitle: { fontSize: 16, fontWeight: '600' },
  cardCopy: { fontSize: 14, color: '#687076' },
  sheet: { flex: 1, padding: 24, paddingTop: 32, gap: 12 },
  sheetTitle: { fontSize: 22, fontWeight: '700' },
  sheetCopy: { fontSize: 15, color: '#111418', lineHeight: 22 },
  input: {
    minHeight: 120,
    borderRadius: 12,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: '#C6CBD1',
    padding: 12,
    fontSize: 15,
    textAlignVertical: 'top',
  },
  primaryButton: {
    marginTop: 8,
    borderRadius: 12,
    paddingVertical: 14,
    alignItems: 'center',
    backgroundColor: '#111418',
  },
  primaryLabel: { color: '#FFFFFF', fontSize: 15, fontWeight: '600' },
  secondaryButton: { borderRadius: 12, paddingVertical: 14, alignItems: 'center' },
  secondaryLabel: { color: '#687076', fontSize: 15, fontWeight: '600' },
})
