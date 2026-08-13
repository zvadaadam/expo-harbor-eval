import { StyleSheet, View } from 'react-native'

import FeedScreen from './FeedScreen'

export default function App() {
  return (
    <View style={styles.root}>
      <FeedScreen />
    </View>
  )
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#FFFFFF' },
})
