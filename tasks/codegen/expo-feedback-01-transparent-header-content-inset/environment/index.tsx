import { FlatList, StyleSheet, Text, View } from 'react-native'

const SESSIONS = [
  { id: '1', title: 'Morning intervals', detail: '6 x 800 m' },
  { id: '2', title: 'Tempo run', detail: '8 km steady' },
  { id: '3', title: 'Sled push + pull', detail: '4 rounds' },
  { id: '4', title: 'Rowing', detail: '2,000 m' },
  { id: '5', title: 'Wall balls', detail: '100 reps' },
  { id: '6', title: 'Burpee broad jumps', detail: '80 m' },
  { id: '7', title: 'Farmers carry', detail: '200 m' },
  { id: '8', title: 'Long run', detail: '14 km easy' },
]

export default function Sessions() {
  return (
    <FlatList
      data={SESSIONS}
      keyExtractor={(session) => session.id}
      contentInsetAdjustmentBehavior="automatic"
      renderItem={({ item }) => (
        <View style={styles.row}>
          <Text style={styles.title}>{item.title}</Text>
          <Text style={styles.detail}>{item.detail}</Text>
        </View>
      )}
    />
  )
}

const styles = StyleSheet.create({
  row: { gap: 4, paddingHorizontal: 24, paddingVertical: 16 },
  title: { fontSize: 17, fontWeight: '600' },
  detail: { fontSize: 15, color: '#687076' },
})
