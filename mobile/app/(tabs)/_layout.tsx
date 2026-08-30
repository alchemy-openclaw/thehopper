import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors } from '../../src/theme';
import { useKJContext } from '../../src/kj-context';

export default function TabsLayout() {
  const { kj } = useKJContext();

  return (
    <Tabs
      screenOptions={{
        headerShown: true,
        tabBarActiveTintColor: Colors.pink,
        tabBarInactiveTintColor: Colors.textMute,
        tabBarStyle: {
          backgroundColor: Colors.panel,
          borderTopColor: Colors.border,
          borderTopWidth: 1,
          height: 64,
          paddingBottom: 8,
          paddingTop: 6,
        },
        headerStyle: {
          backgroundColor: Colors.bg,
        },
        headerTintColor: Colors.text,
        headerTitleStyle: {
          fontWeight: '800',
        },
        headerShadowVisible: false,
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: 'Find',
          tabBarLabel: 'Find',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="location" color={color} size={size} />
          ),
        }}
      />
      <Tabs.Screen
        name="event"
        options={{
          title: 'Event',
          tabBarLabel: 'Event',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="megaphone" color={color} size={size} />
          ),
        }}
      />
      <Tabs.Screen
        name="songs"
        options={{
          title: 'My Songs',
          tabBarLabel: 'My Songs',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="musical-notes" color={color} size={size} />
          ),
        }}
      />
      <Tabs.Screen
        name="add-spot"
        options={{
          title: 'Add Spot',
          tabBarLabel: 'Add',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="add-circle" color={color} size={size} />
          ),
        }}
      />
      {/* Hosts only. href: null keeps the route registered but hides the tab,
          so singers never see it and the pending-singers list stays one tap
          away for a KJ running a night. */}
      <Tabs.Screen
        name="kj"
        options={{
          title: 'My KJ',
          tabBarLabel: 'My KJ',
          href: kj ? undefined : null,
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="mic" color={color} size={size} />
          ),
        }}
      />
    </Tabs>
  );
}
