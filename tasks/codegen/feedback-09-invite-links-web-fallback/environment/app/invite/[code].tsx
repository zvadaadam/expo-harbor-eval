import { router, useLocalSearchParams } from 'expo-router'
import { Pressable, StyleSheet, Text, View } from 'react-native'

export default function InviteScreen() {
  const { code } = useLocalSearchParams<{ code: string }>()

  return (
    <View style={styles.screen}>
      <Text style={styles.title}>You're invited</Text>
      <Text style={styles.detail}>Table code {code}</Text>
      <Pressable style={styles.primaryButton} onPress={() => router.replace('/')}>
        <Text style={styles.primaryLabel}>Join the table</Text>
      </Pressable>
    </View>
  )
}

const styles = StyleSheet.create({
  screen: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24, gap: 8 },
  title: { fontSize: 28, fontWeight: '700' },
  detail: { fontSize: 15, color: '#687076' },
  primaryButton: {
    marginTop: 16,
    borderRadius: 12,
    paddingVertical: 12,
    paddingHorizontal: 24,
    backgroundColor: '#111418',
  },
  primaryLabel: { color: '#FFFFFF', fontSize: 15, fontWeight: '600' },
})
