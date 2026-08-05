import { Stack } from 'expo-router'

export default function Layout() {
  return (
    <Stack
      screenOptions={{
        headerTransparent: true,
        headerLargeTitle: true,
        headerBlurEffect: 'none',
      }}
    >
      <Stack.Screen
        name="index"
        options={{
          title: 'Sessions',
          headerSearchBarOptions: {
            placeholder: 'Search sessions',
            placement: 'stacked',
          },
        }}
      />
    </Stack>
  )
}
