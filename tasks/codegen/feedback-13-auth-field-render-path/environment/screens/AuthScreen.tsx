import React from 'react';
import { AuthNativeForm } from '../components/AuthNativeForm';

export function AuthScreen({ mode }: { mode: 'sign-in' | 'create-account' }) {
  return <AuthNativeForm key={mode} mode={mode} />;
}
