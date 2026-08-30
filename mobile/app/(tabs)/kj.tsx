/**
 * "My KJ" tab — a host's dashboard: pending singers, payouts, preferences.
 *
 * The tab is hidden for non-hosts (see (tabs)/_layout.tsx), but the route stays
 * registered, so this still handles the case where someone reaches it without a
 * KJ profile rather than rendering a broken screen.
 */
import { ScrollView, StyleSheet } from 'react-native';
import { useKJContext } from '../../src/kj-context';
import { EmptyState, Loading } from '../../src/components';
import { Colors, Spacing } from '../../src/theme';
import KJProfileScreen from '../kj/[id]';

export default function KJTab() {
  const { kj, loading } = useKJContext();

  if (loading) {
    return (
      <ScrollView style={styles.container} contentContainerStyle={styles.content}>
        <Loading label="Loading your KJ profile…" />
      </ScrollView>
    );
  }

  if (!kj) {
    return (
      <ScrollView style={styles.container} contentContainerStyle={styles.content}>
        <EmptyState
          icon="🎤"
          message={
            "You're not set up as a KJ yet. Go to the Add tab, switch on \"I'm the KJ\", and verify your number to host a venue."
          }
        />
      </ScrollView>
    );
  }

  return <KJProfileScreen kjIdOverride={kj.id} />;
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.bg },
  content: { padding: Spacing.lg },
});
