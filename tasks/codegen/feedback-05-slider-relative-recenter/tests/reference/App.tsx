import { StyleSheet, Text, View } from 'react-native'

import ExposureTrim from './ExposureTrim'

export default function App() {
  return (
    <View style={styles.screen}>
      <Text style={styles.title}>Edit photo</Text>
      <Text style={styles.subtitle}>IMG_0412 — Develop</Text>
      <ExposureTrim />
    </View>
  )
}

const styles = StyleSheet.create({
  screen: { flex: 1, paddingTop: 96, paddingHorizontal: 20, backgroundColor: '#FFFFFF', gap: 4 },
  title: { fontSize: 28, fontWeight: '700' },
  subtitle: { fontSize: 15, color: '#687076' },
})
