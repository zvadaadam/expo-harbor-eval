import { Link } from 'expo-router'
import { Pressable, StyleSheet, Text, View } from 'react-native'

const SESSIONS = [
  { id: '1', title: 'Morning intervals' },
  { id: '2', title: 'Tempo run' },
  { id: '3', title: 'Rowing' },
  { id: '4', title: 'Long run' },
]

export default function Sessions() {
  return (
    <View style={styles.container}>
      <Text style={styles.headline}>
        Session <Text style={styles.accent}>Pro</Text>
      </Text>
      {SESSIONS.map((session) => (
        <Link key={session.id} href="/details" asChild>
          <Pressable style={styles.row}>
            <Text style={styles.title}>{session.title}</Text>
          </Pressable>
        </Link>
      ))}
    </View>
  )
}

const styles = StyleSheet.create({
  container: { flex: 1, gap: 4, padding: 24, paddingTop: 60 },
  headline: { fontSize: 28, fontWeight: '700', marginBottom: 12 },
  accent: { color: '#FF6B35' },
  row: { paddingVertical: 12 },
  title: { fontSize: 17, fontWeight: '600' },
})
