import { StyleSheet, Text, View } from 'react-native'
import { GestureHandlerRootView } from 'react-native-gesture-handler'

import MoodboardGrid from './MoodboardGrid'

export default function App() {
  return (
    <GestureHandlerRootView style={styles.root}>
      <View style={styles.screen}>
        <Text style={styles.title}>Moodboard</Text>
        <Text style={styles.subtitle}>Hold a photo, then drag to rearrange</Text>
        <MoodboardGrid />
      </View>
    </GestureHandlerRootView>
  )
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  screen: { flex: 1, paddingTop: 96, paddingHorizontal: 16, backgroundColor: '#FFFFFF', gap: 4 },
  title: { fontSize: 28, fontWeight: '700' },
  subtitle: { fontSize: 15, color: '#687076', marginBottom: 16 },
})
