import React, { useState } from 'react';
import { Host } from '@expo/ui';
import { Button, SecureField, Text, TextField, VStack } from '@expo/ui/swift-ui';
import { accessibilityIdentifier, frame, padding, textFieldStyle } from '@expo/ui/swift-ui/modifiers';

const fieldModifiers = [
  textFieldStyle('plain'),
  padding({ horizontal: 14, vertical: 8 }),
  frame({ minHeight: 52, maxHeight: 52 }),
];

export function AuthNativeForm({ mode }: { mode: 'sign-in' | 'create-account' }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  return <Host matchContents><VStack spacing={12}>
    <Text>{mode === 'sign-in' ? 'Welcome back' : 'Create your account'}</Text>
    <TextField placeholder="Email" onTextChange={setEmail} modifiers={[
      ...fieldModifiers, accessibilityIdentifier('auth-email'),
    ]} />
    <SecureField placeholder="Password" onTextChange={setPassword} modifiers={[
      ...fieldModifiers, accessibilityIdentifier('auth-password'),
    ]} />
    <Button onPress={() => setConfirmation(`${mode}: ${email} · ${password.length} characters`)} modifiers={[
      frame({ height: 52 }), accessibilityIdentifier('auth-submit'),
    ]}>{mode === 'sign-in' ? 'Sign in' : 'Create account'}</Button>
    <Text>{confirmation}</Text>
  </VStack></Host>;
}
