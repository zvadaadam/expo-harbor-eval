import React, { useState } from 'react';
import { Pressable, SafeAreaView, Text } from 'react-native';
import { SummaryRow } from './SummaryRow';

const descriptions = ['Savings', 'Emergency savings for travel and unexpected expenses'];

export default function App() {
  const [fixture, setFixture] = useState(0);
  return (
    <SafeAreaView>
      <SummaryRow description={descriptions[fixture]} amount="$12,345.67" />
      <Pressable accessibilityRole="button" accessibilityLabel="Switch description" onPress={() => setFixture(1 - fixture)}>
        <Text>Switch description</Text>
      </Pressable>
    </SafeAreaView>
  );
}
