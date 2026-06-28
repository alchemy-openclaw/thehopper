import type { Song } from './types';
import { DIFFICULTY_LABELS } from './types';

/** Difficulty badge component. */
export function DifficultyBadge({ level }: { level: number }) {
  const info = DIFFICULTY_LABELS[level] ?? { label: '?', emoji: '⚪' };
  return (
    <span
      className="meta-pill"
      title={`Difficulty ${level}/5`}
    >
      {info.emoji} {info.label}
    </span>
  );
}

/** Range chips for a song. */
export function RangeChips({ ranges }: { ranges: string[] }) {
  return (
    <>
      {ranges.map((r) => (
        <span key={r} className="meta-pill">
          {r}
        </span>
      ))}
    </>
  );
}

/** Full song card with optional score/reason + actions. */
export function SongCard({
  song,
  score,
  reason,
  isFavorite,
  onToggleFavorite,
  onRequestAtVenue,
}: {
  song: Song;
  score?: number;
  reason?: string;
  isFavorite?: boolean;
  onToggleFavorite?: () => void;
  onRequestAtVenue?: () => void;
}) {
  return (
    <div className="song">
      <div className="song-top">
        <div>
          <div className="song-title">{song.title}</div>
          <div className="song-artist">{song.artist}</div>
        </div>
        {score != null && (
          <div className="song-score" title="Match score">
            {Math.round(score)}%
          </div>
        )}
        {onToggleFavorite && (
          <button
            className={`star ${isFavorite ? 'active' : ''}`}
            onClick={onToggleFavorite}
            aria-label={isFavorite ? 'Remove from favorites' : 'Add to favorites'}
            title={isFavorite ? 'Remove from favorites' : 'Add to favorites'}
          >
            {isFavorite ? '⭐' : '☆'}
          </button>
        )}
      </div>

      <div className="song-meta">
        <span className="meta-pill">{song.genre}</span>
        {song.year && <span className="meta-pill">{song.year}</span>}
        <DifficultyBadge level={song.difficulty} />
        <RangeChips ranges={song.range_fit} />
      </div>

      {reason && <div className="song-reason">{reason}</div>}
      {song.notes && <div className="song-notes">{song.notes}</div>}

      {onRequestAtVenue && (
        <div className="song-actions">
          <button className="btn cyan" onClick={onRequestAtVenue}>
            🎤 Request this
          </button>
        </div>
      )}
    </div>
  );
}

/** Loading spinner. */
export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="loading">
      <div className="spinner" />
      <span>{label}</span>
    </div>
  );
}

/** Empty state. */
export function EmptyState({ icon, message }: { icon: string; message: string }) {
  return (
    <div className="empty">
      <span className="big" aria-hidden="true">
        {icon}
      </span>
      {message}
    </div>
  );
}
