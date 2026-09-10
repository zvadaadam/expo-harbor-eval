import React, { useState } from 'react';
import { Pressable, ScrollView, Text, View } from 'react-native';

const { fixtures } = require('./fixtures');
const { getPaywallOffering } = require('./paywall');

export default function App() {
  const [selected, setSelected] = useState(0);
  const snapshot = fixtures[selected].state;
  const offering = getPaywallOffering(snapshot);
  return (
    <ScrollView contentContainerStyle={{ padding: 24, paddingTop: 72, gap: 12 }}>
      <Text style={{ fontSize: 26 }}>Placement paywall</Text>
      {fixtures.map((fixture: { label: string }, index: number) => (
        <Pressable key={fixture.label} onPress={() => setSelected(index)} accessibilityRole="button">
          <Text style={{ padding: 8 }}>{fixture.label}</Text>
        </Pressable>
      ))}
      <View testID="paywall-state">
        <Text>{fixtures[selected].label}</Text>
        <Text>{offering ? `Paywall: ${offering}` : 'Paywall hidden'}</Text>
      </View>
    </ScrollView>
  );
}
