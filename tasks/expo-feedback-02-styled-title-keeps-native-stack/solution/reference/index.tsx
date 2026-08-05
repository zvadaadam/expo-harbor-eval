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
  container: { flex: 1, gap: 4, padding: 24 },
  row: { paddingVertical: 12 },
  title: { fontSize: 17, fontWeight: '600' },
})
