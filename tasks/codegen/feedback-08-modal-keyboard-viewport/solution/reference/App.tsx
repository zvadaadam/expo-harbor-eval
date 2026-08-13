import { useState } from 'react'
import { Pressable, StyleSheet, Text, View } from 'react-native'

import VersePopup from './VersePopup'

export default function App() {
  const [composing, setComposing] = useState(false)
  const [verses, setVerses] = useState<string[]>([
    'The lighthouse hums a chord the tide forgot.',
  ])

  return (
    <View style={styles.screen}>
      <Text style={styles.title}>Lantern & Reverie</Text>
      <Text style={styles.subtitle}>Tonight's readings</Text>
      {verses.map((verse, index) => (
        <Text key={index} style={styles.verse}>
          {verse}
        </Text>
      ))}
      <Pressable style={styles.compose} onPress={() => setComposing(true)}>
        <Text style={styles.composeLabel}>New verse</Text>
      </Pressable>
      <VersePopup
        visible={composing}
        onSave={(verse) => {
          setVerses((current) => [...current, verse])
          setComposing(false)
        }}
        onCancel={() => setComposing(false)}
      />
    </View>
  )
}

const styles = StyleSheet.create({
  screen: { flex: 1, paddingTop: 96, paddingHorizontal: 24, backgroundColor: '#FFFFFF', gap: 8 },
  title: { fontSize: 28, fontWeight: '700' },
  subtitle: { fontSize: 15, color: '#687076', marginBottom: 8 },
  verse: { fontSize: 15, lineHeight: 24, color: '#111418', fontStyle: 'italic' },
  compose: {
    marginTop: 24,
    alignSelf: 'flex-start',
    borderRadius: 12,
    paddingVertical: 12,
    paddingHorizontal: 20,
    backgroundColor: '#111418',
  },
  composeLabel: { color: '#FFFFFF', fontSize: 15, fontWeight: '600' },
})
