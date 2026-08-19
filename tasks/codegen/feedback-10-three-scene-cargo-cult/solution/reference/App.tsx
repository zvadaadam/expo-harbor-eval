import { StyleSheet, Text, View } from 'react-native'

import TerrainScene from './TerrainScene'

export default function App() {
  return (
    <View style={styles.screen}>
      <View style={styles.header}>
        <Text style={styles.title}>Ridgeline</Text>
        <Text style={styles.subtitle}>Today's route, rendered live</Text>
      </View>
      <TerrainScene />
    </View>
  )
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#0B1220' },
  header: { paddingTop: 96, paddingHorizontal: 24, paddingBottom: 16, gap: 4 },
  title: { fontSize: 28, fontWeight: '700', color: '#FFFFFF' },
  subtitle: { fontSize: 15, color: '#8A94A6' },
})
