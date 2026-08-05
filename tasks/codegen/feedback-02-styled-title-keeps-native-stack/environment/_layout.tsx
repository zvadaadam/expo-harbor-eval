import { Stack } from 'expo-router'

export default function Layout() {
  return (
    <Stack>
      <Stack.Screen name="index" options={{ title: 'Session Pro' }} />
      <Stack.Screen name="details" options={{ title: 'Session detail' }} />
    </Stack>
  )
}
