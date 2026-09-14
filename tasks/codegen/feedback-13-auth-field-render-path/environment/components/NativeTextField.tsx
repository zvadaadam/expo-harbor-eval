import React from 'react';
import { TextField } from '@expo/ui/swift-ui';
import { accessibilityIdentifier, frame, padding, textFieldStyle } from '@expo/ui/swift-ui/modifiers';

export function NativeTextField({ placeholder, onTextChange }: { placeholder: string; onTextChange: (text: string) => void }) {
  return <TextField placeholder={placeholder} onTextChange={onTextChange} modifiers={[
    textFieldStyle('plain'),
    frame({ height: 44 }),
    padding({ horizontal: 14 }),
    accessibilityIdentifier('profile-name'),
  ]} />;
}
