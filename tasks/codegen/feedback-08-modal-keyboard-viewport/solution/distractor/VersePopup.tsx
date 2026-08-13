import { useState } from 'react'
import {
  KeyboardAvoidingView,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native'

type Props = {
  visible: boolean
  onSave: (verse: string) => void
  onCancel: () => void
}

export default function VersePopup({ visible, onSave, onCancel }: Props) {
  const [draft, setDraft] = useState('')

  const save = () => {
    if (draft.trim()) {
      onSave(draft.trim())
      setDraft('')
    }
  }

  return (
    <Modal
      visible={visible}
      transparent
      statusBarTranslucent
      navigationBarTranslucent
      animationType="fade"
      onRequestClose={onCancel}
    >
      <View style={styles.backdrop}>
        {/* Let the card itself avoid the keyboard: wrapping the popup card
            in a KeyboardAvoidingView pushes it up as the keyboard opens. */}
        <KeyboardAvoidingView behavior="padding">
          <View style={styles.card}>
            <Text style={styles.heading}>New verse</Text>
            <ScrollView
              contentContainerStyle={styles.composerContent}
              keyboardShouldPersistTaps="handled"
            >
              <TextInput
                style={styles.input}
                value={draft}
                onChangeText={setDraft}
                placeholder="Write tonight's verse…"
                multiline
              />
            </ScrollView>
            <View style={styles.actions}>
              <Pressable style={styles.secondaryButton} onPress={onCancel}>
                <Text style={styles.secondaryLabel}>Cancel</Text>
              </Pressable>
              <Pressable style={styles.primaryButton} onPress={save}>
                <Text style={styles.primaryLabel}>Save</Text>
              </Pressable>
            </View>
          </View>
        </KeyboardAvoidingView>
      </View>
    </Modal>
  )
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
    backgroundColor: 'rgba(17, 20, 24, 0.55)',
  },
  card: {
    alignSelf: 'stretch',
    borderRadius: 16,
    backgroundColor: '#FFFFFF',
    padding: 16,
    gap: 12,
  },
  heading: { fontSize: 20, fontWeight: '700' },
  composerContent: { paddingBottom: 160 },
  input: {
    minHeight: 140,
    borderRadius: 12,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: '#C6CBD1',
    padding: 12,
    fontSize: 15,
    lineHeight: 22,
    textAlignVertical: 'top',
  },
  actions: { flexDirection: 'row', justifyContent: 'flex-end', gap: 8 },
  primaryButton: {
    borderRadius: 12,
    paddingVertical: 12,
    paddingHorizontal: 20,
    backgroundColor: '#111418',
  },
  primaryLabel: { color: '#FFFFFF', fontSize: 15, fontWeight: '600' },
  secondaryButton: { borderRadius: 12, paddingVertical: 12, paddingHorizontal: 16 },
  secondaryLabel: { color: '#687076', fontSize: 15, fontWeight: '600' },
})
