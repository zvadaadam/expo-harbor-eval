import { Pressable, Share, StyleSheet, Text, View } from 'react-native'

const INVITE_CODE = 'ember-7f3k'
const INVITE_URL = `https://emberline.app/invite/${INVITE_CODE}`

export default function HomeScreen() {
  const shareInvite = () => {
    Share.share({ message: `Join my table on Emberline: ${INVITE_URL}` })
  }

  return (
    <View style={styles.screen}>
      <Text style={styles.title}>Emberline</Text>
      <Text style={styles.subtitle}>Supper club, every Thursday</Text>
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Your table invite</Text>
        <Text style={styles.cardCode}>{INVITE_URL}</Text>
        <Pressable style={styles.primaryButton} onPress={shareInvite}>
          <Text style={styles.primaryLabel}>Share invite</Text>
        </Pressable>
      </View>
    </View>
  )
}

const styles = StyleSheet.create({
  screen: { flex: 1, paddingTop: 96, paddingHorizontal: 24, backgroundColor: '#FFFFFF', gap: 4 },
  title: { fontSize: 28, fontWeight: '700' },
  subtitle: { fontSize: 15, color: '#687076', marginBottom: 16 },
  card: { borderRadius: 16, backgroundColor: '#F2F3F5', padding: 16, gap: 8 },
  cardTitle: { fontSize: 16, fontWeight: '600' },
  cardCode: { fontSize: 14, color: '#4B5563', fontVariant: ['tabular-nums'] },
  primaryButton: {
    marginTop: 8,
    borderRadius: 12,
    paddingVertical: 12,
    alignItems: 'center',
    backgroundColor: '#111418',
  },
  primaryLabel: { color: '#FFFFFF', fontSize: 15, fontWeight: '600' },
})
