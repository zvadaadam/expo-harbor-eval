import { Stack } from 'expo-router'
import { StyleSheet, Text } from 'react-native'

export default function Layout() {
  return (
    <Stack>
      <Stack.Screen
        name="index"
        options={{
          headerTitle: () => (
            <Text style={styles.title}>
              Session <Text style={styles.accent}>Pro</Text>
            </Text>
          ),
        }}
      />
      <Stack.Screen name="details" options={{ title: 'Session detail' }} />
    </Stack>
  )
}

const styles = StyleSheet.create({
  title: { fontSize: 17, fontWeight: '600' },
  accent: { color: '#FF6B35' },
})
