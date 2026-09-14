import React, { useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import { styles } from './summaryStyles';

export function SummaryRow({ description, amount }: { description: string; amount: string }) {
  const [visible, setVisible] = useState(true);
  return (
    <View style={styles.screen} testID="summary-screen">
      <View style={styles.row} testID="summary-row">
        <View style={[styles.cell, styles.description]} testID="description-column">
          <Text numberOfLines={1} style={styles.label}>{description}</Text>
        </View>
        <View style={[styles.cell, styles.amount]} testID="amount-column">
          <Text style={styles.label}>Available</Text>
          <Text style={styles.value} testID="amount-value">{visible ? amount : '••••••'}</Text>
        </View>
        <Pressable
          testID="visibility-control"
          style={styles.visibility}
          accessibilityRole="button"
          accessibilityLabel={visible ? 'Hide amount' : 'Show amount'}
          onPress={() => setVisible(!visible)}>
          <Text style={styles.label}>◉</Text>
        </Pressable>
      </View>
    </View>
  );
}
