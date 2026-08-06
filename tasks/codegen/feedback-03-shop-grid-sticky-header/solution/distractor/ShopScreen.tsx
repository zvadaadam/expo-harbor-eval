import { useCallback, useEffect, useRef } from 'react'
import { useFocusEffect, useNavigation } from '@react-navigation/native'
import { Animated, ScrollView, StyleSheet, Text, View } from 'react-native'

const PRODUCTS = [
  {
    id: '1',
    name: 'Grip chalk',
    price: '$12',
    copy: 'Loose magnesium chalk milled fine for sweaty pulls. Keeps hook grip locked through the last heavy set and brushes off without caking.',
  },
  {
    id: '2',
    name: 'Speed rope',
    price: '$38',
    copy: 'Bare aluminium handles on sealed bearings with a coated steel cable. Cut it to height once and double-unders stop being a coin flip.',
  },
  {
    id: '3',
    name: 'Knee sleeves',
    price: '$54',
    copy: '7 mm neoprene with a contoured seam that does not fold behind the knee. Warm rebound out of the hole without cutting circulation between sets.',
  },
  {
    id: '4',
    name: 'Wrist wraps',
    price: '$21',
    copy: 'Stiff cotton weave with a wide thumb loop. Sets in one pull and holds the wrist stacked under jerks, presses, and heavy front racks.',
  },
  {
    id: '5',
    name: 'Water bottle',
    price: '$29',
    copy: 'Double-wall steel, one litre, with a cap that seals sideways in a gym bag. Keeps electrolytes cold through a full session in the sun.',
  },
  {
    id: '6',
    name: 'Lifting belt',
    price: '$89',
    copy: 'A 10 cm nylon belt with a self-locking slide buckle. Brace hard without the edge digging in, and rip it off one-handed between movements.',
  },
]

const STICKY_REVEAL_Y = 96

export default function ShopScreen() {
  const navigation = useNavigation()
  const scrollRef = useRef<ScrollView>(null)
  const scrollY = useRef(new Animated.Value(0)).current

  // Reset the driven value every time the tab regains focus so the condensed
  // bar starts hidden, and retry on the next frame in case the first reset
  // lands while the screen is still frozen.
  useFocusEffect(
    useCallback(() => {
      scrollRef.current?.scrollTo({ y: 0, animated: false })
      scrollY.stopAnimation()
      scrollY.setValue(0)
      requestAnimationFrame(() => scrollY.setValue(0))
    }, [scrollY]),
  )

  // Also clear the value on the way out so the bar cannot carry a stale
  // offset across the tab switch.
  useEffect(() => {
    const unsubscribe = navigation.addListener('blur', () => {
      scrollY.setValue(0)
    })
    return unsubscribe
  }, [navigation, scrollY])

  const stickyOpacity = scrollY.interpolate({
    inputRange: [STICKY_REVEAL_Y, STICKY_REVEAL_Y + 32],
    outputRange: [0, 1],
    extrapolate: 'clamp',
  })

  return (
    <View style={styles.screen}>
      <Animated.View
        pointerEvents="none"
        style={[styles.stickyBar, { opacity: stickyOpacity }]}
      >
        <Text style={styles.stickyTitle}>Shop</Text>
      </Animated.View>
      <Animated.ScrollView
        ref={scrollRef}
        contentContainerStyle={styles.content}
        scrollEventThrottle={16}
        onScroll={Animated.event(
          [{ nativeEvent: { contentOffset: { y: scrollY } } }],
          { useNativeDriver: true },
        )}
      >
        <View style={styles.hero}>
          <Text style={styles.heroTitle}>Shop</Text>
          <Text style={styles.heroDetail}>Gear picked for this training block</Text>
        </View>
        <View style={styles.grid}>
          {PRODUCTS.map((product) => (
            <View key={product.id} style={styles.card}>
              <Text style={styles.name}>{product.name}</Text>
              <Text style={styles.price}>{product.price}</Text>
              <Text style={styles.copy}>{product.copy}</Text>
            </View>
          ))}
        </View>
      </Animated.ScrollView>
    </View>
  )
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#FFFFFF' },
  stickyBar: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    zIndex: 1,
    paddingTop: 56,
    paddingBottom: 12,
    alignItems: 'center',
    backgroundColor: '#FFFFFFEE',
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#E6E8EB',
  },
  stickyTitle: { fontSize: 17, fontWeight: '600' },
  content: { flexGrow: 1, padding: 16 },
  hero: { paddingTop: 64, paddingBottom: 24, gap: 4 },
  heroTitle: { fontSize: 34, fontWeight: '700' },
  heroDetail: { fontSize: 15, color: '#687076' },
  grid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between' },
  card: {
    width: '48%',
    height: '45%',
    minHeight: 176,
    marginBottom: 16,
    borderRadius: 12,
    padding: 12,
    backgroundColor: '#F2F3F5',
    gap: 6,
  },
  name: { fontSize: 15, fontWeight: '600' },
  price: { fontSize: 15, color: '#111418' },
  copy: { fontSize: 13, color: '#687076' },
})
