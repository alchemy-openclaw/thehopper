import { useEffect } from 'react';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { Colors } from '../src/theme';
import { PrefsProvider } from '../src/prefs-context';
import { VenueProvider } from '../src/venue-context';
import { registerForPushNotifications } from '../src/notifications';

export default function RootLayout() {
  useEffect(() => {
    registerForPushNotifications().catch(() => {});
  }, []);

  return (
    <GestureHandlerRootView style={{ flex: 1, backgroundColor: Colors.bg }}>
      <PrefsProvider>
        <VenueProvider>
          <StatusBar style="light" />
          <Stack
            screenOptions={{
              headerShown: false,
              contentStyle: { backgroundColor: Colors.bg },
            }}
          >
            <Stack.Screen name="(tabs)" />
          </Stack>
        </VenueProvider>
      </PrefsProvider>
    </GestureHandlerRootView>
  );
}
