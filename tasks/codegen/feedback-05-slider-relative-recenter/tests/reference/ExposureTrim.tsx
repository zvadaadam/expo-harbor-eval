import { useState } from 'react'
import { StyleSheet, Text, View } from 'react-native'
import Slider from '@react-native-community/slider'

// One full drag from the centre to either end nudges exposure by half a stop.
const TRIM_RANGE_EV = 0.5

// The installed wrapper (5.0.1, node_modules/@react-native-community/slider/
// dist/Slider.js) drops falsy values before they reach the native component:
//   passedValue = Number.isNaN(value) || !value ? undefined : value
// so a control that rests at 0 can never be re-centred — the reset write is
// swallowed in JS and the unset prop falls back to the native default, which
// is also 0, so the native side sees no change to apply. Keeping the scale
// positive (0…1, resting at 0.5) makes every recenter a truthy write.
const KNOB_MIN = 0
const KNOB_MAX = 1
const KNOB_CENTER = 0.5

export default function ExposureTrim() {
  const [totalEv, setTotalEv] = useState(0)
  // Controlled: the prop follows the thumb during the drag, so the reset to
  // the centre on release is a real prop transition from the last rendered
  // value — not a repeat of the same constant the native side already holds.
  const [knob, setKnob] = useState(KNOB_CENTER)

  const handleSlidingComplete = (released: number) => {
    const offset = released - KNOB_CENTER
    setTotalEv((total) => total + offset * 2 * TRIM_RANGE_EV)
    setKnob(KNOB_CENTER)
  }

  return (
    <View style={styles.card}>
      <Text style={styles.readout}>
        {totalEv >= 0 ? '+' : ''}
        {totalEv.toFixed(2)} EV
      </Text>
      <Slider
        style={styles.slider}
        minimumValue={KNOB_MIN}
        maximumValue={KNOB_MAX}
        value={knob}
        onValueChange={setKnob}
        onSlidingComplete={handleSlidingComplete}
      />
      <Text style={styles.hint}>Drag to nudge exposure — the knob snaps back when you let go</Text>
    </View>
  )
}

const styles = StyleSheet.create({
  card: {
    marginTop: 24,
    padding: 16,
    borderRadius: 12,
    backgroundColor: '#F2F3F5',
    gap: 12,
  },
  readout: { fontSize: 34, fontWeight: '700', textAlign: 'center', fontVariant: ['tabular-nums'] },
  slider: { width: '100%', height: 40 },
  hint: { fontSize: 13, color: '#687076', textAlign: 'center' },
})
