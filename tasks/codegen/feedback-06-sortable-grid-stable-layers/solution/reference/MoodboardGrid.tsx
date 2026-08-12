import { useState } from 'react'
import { Dimensions, StyleSheet, Text, View } from 'react-native'
import { Gesture, GestureDetector } from 'react-native-gesture-handler'
import Animated, {
  runOnJS,
  useAnimatedReaction,
  useAnimatedStyle,
  useSharedValue,
  withTiming,
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
const GRID_ROWS = Math.ceil(PHOTOS.length / COLUMNS)

type Slots = Record<string, number>

const xForSlot = (slot: number) => {
  'worklet'
  return (slot % COLUMNS) * (TILE_SIZE + TILE_GAP)
}

const yForSlot = (slot: number) => {
  'worklet'
  return Math.floor(slot / COLUMNS) * (TILE_SIZE + TILE_GAP)
}

// Inverts a tile CENTRE back to its slot: subtracting half a tile before
// rounding puts the flip boundary halfway between neighbouring slots in
// every direction, so a hovered swap needs the same travel left or right.
const slotForPoint = (x: number, y: number) => {
  'worklet'
  const column = Math.min(
    COLUMNS - 1,
    Math.max(0, Math.round((x - TILE_SIZE / 2) / (TILE_SIZE + TILE_GAP))),
  )
  const row = Math.min(
    GRID_ROWS - 1,
    Math.max(0, Math.round((y - TILE_SIZE / 2) / (TILE_SIZE + TILE_GAP))),
  )
  return Math.min(PHOTOS.length - 1, row * COLUMNS + column)
}

// The tiles never re-render or reorder while a drag is in progress. Every
// tile is an absolutely positioned layer whose place comes from a shared slot
// map that lives on the UI thread: threshold crossings reassign slots in the
// map (displaced tiles glide to their new slot with withTiming), the dragged
// tile follows the finger from its grab origin, and React state is written
// exactly once — on drop.
function Tile({
  photo,
  initialSlot,
  slots,
  onDrop,
}: {
  photo: (typeof PHOTOS)[number]
  initialSlot: number
  slots: { value: Slots }
  onDrop: (finalSlots: Slots) => void
}) {
  const isDragging = useSharedValue(false)
  const translateX = useSharedValue(xForSlot(initialSlot))
  const translateY = useSharedValue(yForSlot(initialSlot))
  const originX = useSharedValue(0)
  const originY = useSharedValue(0)

  // Displaced tiles follow their slot assignment; the dragged tile ignores
  // it until release, so nothing can move it under the finger.
  useAnimatedReaction(
    () => slots.value[photo.id],
    (slot, previous) => {
      if (previous !== null && slot !== previous && !isDragging.value) {
        translateX.value = withTiming(xForSlot(slot))
        translateY.value = withTiming(yForSlot(slot))
      }
    },
  )

  const pan = Gesture.Pan()
    .activateAfterLongPress(300)
    .onStart(() => {
      isDragging.value = true
      originX.value = translateX.value
      originY.value = translateY.value
    })
    .onUpdate((event) => {
      translateX.value = originX.value + event.translationX
      translateY.value = originY.value + event.translationY
      const hovered = slotForPoint(
        translateX.value + TILE_SIZE / 2,
        translateY.value + TILE_SIZE / 2,
      )
      const current = slots.value[photo.id]
      if (hovered !== current) {
        const next: Slots = { ...slots.value }
        for (const id in next) {
          if (next[id] === hovered) {
            next[id] = current
          }
        }
        next[photo.id] = hovered
        slots.value = next
      }
    })
    .onEnd(() => {
      isDragging.value = false
      const slot = slots.value[photo.id]
      translateX.value = withTiming(xForSlot(slot))
      translateY.value = withTiming(yForSlot(slot))
      runOnJS(onDrop)(slots.value)
    })

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [
      { translateX: translateX.value },
      { translateY: translateY.value },
      { scale: isDragging.value ? 1.05 : 1 },
    ],
    zIndex: isDragging.value ? 10 : 0,
  }))

  return (
    <GestureDetector gesture={pan}>
      <Animated.View
        style={[styles.tile, { backgroundColor: photo.tint }, animatedStyle]}
      >
        <Text style={styles.tileLabel}>{photo.label}</Text>
      </Animated.View>
    </GestureDetector>
  )
}

export default function MoodboardGrid() {
  const [photos, setPhotos] = useState(PHOTOS)
  const slots = useSharedValue<Slots>(
    Object.fromEntries(PHOTOS.map((photo, index) => [photo.id, index])),
  )

  // The single order commit: sort the saved data to match the slot map the
  // completed gesture produced.
  const handleDrop = (finalSlots: Slots) => {
    setPhotos((current) =>
      current.slice().sort((a, b) => finalSlots[a.id] - finalSlots[b.id]),
    )
  }

  return (
    <View style={styles.grid}>
      {photos.map((photo, index) => (
        <Tile
          key={photo.id}
          photo={photo}
          initialSlot={index}
          slots={slots}
          onDrop={handleDrop}
        />
      ))}
    </View>
  )
}

const styles = StyleSheet.create({
  grid: {
    height: GRID_ROWS * (TILE_SIZE + TILE_GAP) - TILE_GAP,
  },
  tile: {
    position: 'absolute',
    left: 0,
    top: 0,
    width: TILE_SIZE,
    height: TILE_SIZE,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  tileLabel: { fontSize: 13, fontWeight: '600', color: '#FFFFFFDD' },
})
