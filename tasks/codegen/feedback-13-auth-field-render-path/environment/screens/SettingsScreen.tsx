import React, { useState } from 'react';
import { Host } from '@expo/ui';
import { Text, VStack } from '@expo/ui/swift-ui';
import { NativeTextField } from '../components/NativeTextField';

export function SettingsScreen() {
  const [name, setName] = useState('');
  return <Host matchContents><VStack spacing={12}>
    <NativeTextField placeholder="Profile name" onTextChange={setName} />
    <Text>{`Profile: ${name}`}</Text>
  </VStack></Host>;
}
