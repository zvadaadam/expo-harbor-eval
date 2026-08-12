import { useState } from 'react'
import { Dimensions, StyleSheet, Text, View } from 'react-native'
import { Gesture, GestureDetector } from 'react-native-gesture-handler'
import Animated, {
  FadeIn,
  FadeOut,
  LinearTransition,
  runOnJS,
  useAnimatedStyle,
  useSharedValue,
} from 'react-native-reanimated'

const PHOTOS = [
  { id: 'p1', label: 'Dawn', tint: '#F4D06F' },
  { id: 'p2', label: 'Harbor', tint: '#9BC1BC' },
  { id: 'p3', label: 'Neon', tint: '#ED6A5A' },
  { id: 'p4', label: 'Moss', tint: '#7FB069' },
  { id: 'p5', label: 'Dune', tint: '#E6C79C' },
  { id: 'p6', label: 'Slate', tint: '#8E9AAF' },
  { id: 'p7', label: 'Blush', tint: '#EFB0C9' },
  { id: 'p8', label: 'Ink', tint: '#5C6B73' },
  { id: 'p9', label: 'Citrus', tint: '#F2CC8F' },
]

const COLUMNS = 3
const GRID_PADDING = 16
const TILE_GAP = 8
const TILE_SIZE =
  (Dimensions.get('window').width - GRID_PADDING * 2 - TILE_GAP * (COLUMNS - 1)) / COLUMNS

const slotForPoint = (x: number, y: number) => {
  'worklet'
  const column = Math.min(COLUMNS - 1, Math.max(0, Math.round(x / (TILE_SIZE + TILE_GAP))))
  const row = Math.max(0, Math.round(y / (TILE_SIZE + TILE_GAP)))
  return Math.min(PHOTOS.length - 1, row * COLUMNS + column)
}

const movePhoto = (photos: typeof PHOTOS, from: number, to: number) => {
  const next = photos.slice()
  const [moved] = next.splice(from, 1)
  next.splice(to, 0, moved)
  return next
}

function Tile({
  photo,
  index,
  onReorder,
}: {
  photo: (typeof PHOTOS)[number]
  index: number
  onReorder: (from: number, to: number) => void
}) {
  const translateX = useSharedValue(0)
  const translateY = useSharedValue(0)

  const pan = Gesture.Pan()
    .activateAfterLongPress(300)
    .onUpdate((event) => {
      translateX.value = event.translationX
      translateY.value = event.translationY
      // Re-home the photo as soon as it crosses into a new slot, so the grid
      // always shows the order the user is creating.
      const centerX =
        (index % COLUMNS) * (TILE_SIZE + TILE_GAP) + TILE_SIZE / 2 + event.translationX
      const centerY =
        Math.floor(index / COLUMNS) * (TILE_SIZE + TILE_GAP) + TILE_SIZE / 2 + event.translationY
      const slot = slotForPoint(centerX, centerY)
      if (slot !== index) {
        runOnJS(onReorder)(index, slot)
      }
    })
    .onEnd(() => {
      translateX.value = 0
      translateY.value = 0
    })

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [{ translateX: translateX.value }, { translateY: translateY.value }],
  }))

  return (
    <GestureDetector gesture={pan}>
      <Animated.View
        layout={LinearTransition}
        entering={FadeIn}
        exiting={FadeOut}
        style={[styles.tile, { backgroundColor: photo.tint }, animatedStyle]}
      >
        <Text style={styles.tileLabel}>{photo.label}</Text>
      </Animated.View>
    </GestureDetector>
  )
}

export default function MoodboardGrid() {
  const [photos, setPhotos] = useState(PHOTOS)

  const handleReorder = (from: number, to: number) => {
    setPhotos((current) => movePhoto(current, from, to))
  }

  return (
    <View style={styles.grid}>
      {photos.map((photo, index) => (
        <Tile key={photo.id} photo={photo} index={index} onReorder={handleReorder} />
      ))}
    </View>
  )
}

const styles = StyleSheet.create({
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: TILE_GAP,
  },
  tile: {
    width: TILE_SIZE,
    height: TILE_SIZE,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  tileLabel: { fontSize: 13, fontWeight: '600', color: '#FFFFFFDD' },
})
