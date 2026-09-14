import React, { useState } from 'react';
import { Pressable, SafeAreaView, Text, View } from 'react-native';
import { AuthScreen } from './screens/AuthScreen';
import { SettingsScreen } from './screens/SettingsScreen';

export default function App() {
  const [route, setRoute] = useState<'sign-in' | 'create-account' | 'settings'>('sign-in');
  return (
    <SafeAreaView>
      <View style={{ flexDirection: 'row', gap: 12, padding: 16 }}>
        {(['sign-in', 'create-account', 'settings'] as const).map(item => (
          <Pressable key={item} accessibilityRole="button" accessibilityLabel={item} onPress={() => setRoute(item)}>
            <Text>{item}</Text>
          </Pressable>
        ))}
      </View>
      {route === 'settings' ? <SettingsScreen /> : <AuthScreen mode={route} />}
    </SafeAreaView>
  );
}
