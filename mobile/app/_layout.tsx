import { useEffect } from 'react';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { PaperProvider } from 'react-native-paper';
import MaterialCommunityIcons from '@expo/vector-icons/MaterialCommunityIcons';
import { Colors } from '../src/theme';
import { hopperDarkTheme } from '../src/paper-theme';
import { PrefsProvider } from '../src/prefs-context';
import { VenueProvider } from '../src/venue-context';
import { KJProvider } from '../src/kj-context';
import { registerForPushNotifications } from '../src/notifications';

export default function RootLayout() {
  useEffect(() => {
    registerForPushNotifications().catch(() => {});
  }, []);

  return (
    <GestureHandlerRootView style={{ flex: 1, backgroundColor: Colors.bg }}>
      {/* Paper's default icon source is react-native-vector-icons, which this
          project does not have — it uses @expo/vector-icons. Without this
          every Paper icon renders as an empty box, silently. */}
      <PaperProvider
        theme={hopperDarkTheme}
        settings={{ icon: (props) => <MaterialCommunityIcons {...props} /> }}
      >
      <PrefsProvider>
        <VenueProvider>
          <KJProvider>
            <StatusBar style="light" />
            <Stack
              screenOptions={{
                headerShown: false,
                contentStyle: { backgroundColor: Colors.bg },
              }}
            >
              <Stack.Screen name="(tabs)" />
            </Stack>
          </KJProvider>
        </VenueProvider>
      </PrefsProvider>
      </PaperProvider>
    </GestureHandlerRootView>
  );
}
