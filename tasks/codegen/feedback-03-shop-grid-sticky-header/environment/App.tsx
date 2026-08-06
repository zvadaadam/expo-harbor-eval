import { createBottomTabNavigator } from '@react-navigation/bottom-tabs'
import { NavigationContainer } from '@react-navigation/native'
import { StyleSheet, Text, View } from 'react-native'
import { enableFreeze } from 'react-native-screens'

import ShopScreen from './ShopScreen'

enableFreeze(true)

const Tab = createBottomTabNavigator()

function HomeScreen() {
  return (
    <View style={styles.home}>
      <Text style={styles.homeTitle}>Today</Text>
      <Text style={styles.homeDetail}>3 workouts planned</Text>
    </View>
  )
}

export default function App() {
  return (
    <NavigationContainer>
      <Tab.Navigator screenOptions={{ freezeOnBlur: true, headerShown: false }}>
        <Tab.Screen name="Home" component={HomeScreen} />
        <Tab.Screen name="Shop" component={ShopScreen} />
      </Tab.Navigator>
    </NavigationContainer>
  )
}

const styles = StyleSheet.create({
  home: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 4 },
  homeTitle: { fontSize: 28, fontWeight: '700' },
  homeDetail: { fontSize: 15, color: '#687076' },
})
