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

// Under Android edge-to-edge the modal's window never resizes for the
// keyboard: the dialog requests adjustResize but also goes edge-to-edge,
// and Android ignores adjustResize for windows that manage their own
// insets. The viewport must therefore shrink in JS. KeyboardAvoidingView
// consumes the global keyboard events (which fire for inputs inside the
// modal's window too), so a full-window KAV directly inside the Modal is
// the keyboard-sized outer viewport: it pads the window box by the exact
// keyboard overlap and everything inside — backdrop, card, actions — lays
// out in the space that remains. The card is bounded by that box
// (maxHeight + flexShrink), the composer scrolls inside the card, and the
// action row sits below it, always visible.
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
      <KeyboardAvoidingView behavior="padding" style={styles.viewport}>
        <View style={styles.backdrop}>
          <View style={styles.card}>
            <Text style={styles.heading}>New verse</Text>
            <ScrollView
              style={styles.composer}
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
        </View>
      </KeyboardAvoidingView>
    </Modal>
  )
}

const styles = StyleSheet.create({
  viewport: { flex: 1 },
  backdrop: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
    backgroundColor: 'rgba(17, 20, 24, 0.55)',
  },
  card: {
    alignSelf: 'stretch',
    maxHeight: '100%',
    flexShrink: 1,
    borderRadius: 16,
    backgroundColor: '#FFFFFF',
    padding: 16,
    gap: 12,
    overflow: 'hidden',
  },
  heading: { fontSize: 20, fontWeight: '700' },
  composer: { flexGrow: 0, flexShrink: 1 },
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
