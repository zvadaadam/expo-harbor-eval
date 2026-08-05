import { StyleSheet, Text, View } from 'react-native'

export default function Details() {
  return (
    <View style={styles.container}>
      <Text style={styles.title}>Session detail</Text>
      <Text style={styles.body}>Splits, pace, and heart-rate zones.</Text>
    </View>
  )
}

const styles = StyleSheet.create({
  container: { flex: 1, gap: 8, padding: 24 },
  title: { fontSize: 20, fontWeight: '600' },
  body: { fontSize: 15, color: '#687076' },
})
