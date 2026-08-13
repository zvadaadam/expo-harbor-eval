import { useState } from 'react'
import { StyleSheet, Text, View } from 'react-native'
import Slider from '@react-native-community/slider'

// One full drag from the centre to either end nudges exposure by half a stop.
const TRIM_RANGE_EV = 0.5

export default function ExposureTrim() {
  const [totalEv, setTotalEv] = useState(0)
  // Zero-centred: the knob rests at 0 and each drag reads as -1…+1.
  const [knob, setKnob] = useState(0)

  const handleSlidingComplete = (released: number) => {
    setTotalEv((total) => total + released * TRIM_RANGE_EV)
    // Snap the knob back to the middle so the next drag is relative again.
    setKnob(0)
  }

  return (
    <View style={styles.card}>
      <Text style={styles.readout}>
        {totalEv >= 0 ? '+' : ''}
        {totalEv.toFixed(2)} EV
      </Text>
      <Slider
        style={styles.slider}
        minimumValue={-1}
        maximumValue={1}
        value={knob}
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
