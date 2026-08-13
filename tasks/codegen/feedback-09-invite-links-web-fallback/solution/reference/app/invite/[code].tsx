import { router, useLocalSearchParams } from 'expo-router'
import { Platform, Pressable, StyleSheet, Text, View } from 'react-native'

// The canonical HTTPS invite URL must be a real web page. Universal links
// and App Links hand the URL to the browser whenever native interception
// does not happen — app not installed, an earlier open-in-browser choice,
// same-domain navigation, the URL typed into the address bar, third-party
// in-app browsers, Android link verification off, desktop clicks — and the
// association files only route those URLs, they never serve content for
// them. Web output is therefore set to "server" (a static build cannot
// render arbitrary invite codes), and the web branch of this shared route
// is the fallback page: invite context, a user-gesture attempt at the
// custom scheme (browsers only launch external apps from a gesture), and
// store links for when the app is missing. Shares keep using the one
// canonical URL, and the code parameter flows through both branches.
export default function InviteScreen() {
  const { code } = useLocalSearchParams<{ code: string }>()

  if (Platform.OS === 'web') {
    return (
      <View style={styles.screen}>
        <Text style={styles.title}>You're invited to Emberline</Text>
        <Text style={styles.detail}>Table code {code} — supper club, every Thursday</Text>
        <Pressable
          style={styles.primaryButton}
          onPress={() => {
            window.location.href = `emberline://invite/${code}`
          }}
        >
          <Text style={styles.primaryLabel}>Open in the app</Text>
        </Pressable>
        <Text style={styles.hint}>Don't have Emberline yet?</Text>
        <View style={styles.stores}>
          <Text
            style={styles.storeLink}
            accessibilityRole="link"
            onPress={() => {
              window.location.href = 'https://apps.apple.com/app/id6752209953'
            }}
          >
            Download on the App Store
          </Text>
          <Text
            style={styles.storeLink}
            accessibilityRole="link"
            onPress={() => {
              window.location.href =
                'https://play.google.com/store/apps/details?id=app.emberline'
            }}
          >
            Get it on Google Play
          </Text>
        </View>
      </View>
    )
  }

  return (
    <View style={styles.screen}>
      <Text style={styles.title}>You're invited</Text>
      <Text style={styles.detail}>Table code {code}</Text>
      <Pressable style={styles.primaryButton} onPress={() => router.replace('/')}>
        <Text style={styles.primaryLabel}>Join the table</Text>
      </Pressable>
    </View>
  )
}

const styles = StyleSheet.create({
  screen: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24, gap: 8 },
  title: { fontSize: 28, fontWeight: '700', textAlign: 'center' },
  detail: { fontSize: 15, color: '#687076', textAlign: 'center' },
  primaryButton: {
    marginTop: 16,
    borderRadius: 12,
    paddingVertical: 12,
    paddingHorizontal: 24,
    backgroundColor: '#111418',
  },
  primaryLabel: { color: '#FFFFFF', fontSize: 15, fontWeight: '600' },
  hint: { marginTop: 24, fontSize: 14, color: '#687076' },
  stores: { marginTop: 4, gap: 8, alignItems: 'center' },
  storeLink: { fontSize: 15, fontWeight: '600', color: '#1D4ED8' },
})
