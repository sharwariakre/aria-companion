function moodColor(score) {
  if (score === null || score === undefined) return "text-gray-400";
  if (score > 0.6) return "text-green-600";
  if (score >= 0.35) return "text-amber-500";
  return "text-red-600";
}

function moodLabel(score) {
  if (score === null || score === undefined) return "—";
  if (score > 0.6) return `${(score * 100).toFixed(0)} · Good`;
  if (score >= 0.35) return `${(score * 100).toFixed(0)} · Fair`;
  return `${(score * 100).toFixed(0)} · Low`;
}

function formatCallTime(isoString) {
  if (!isoString) return "—";
  const date = new Date(isoString.endsWith("Z") ? isoString : isoString + "Z");
  const now = new Date();
  const isToday = date.toDateString() === now.toDateString();
  const time = date.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
  return isToday ? `Today, ${time}` : `${date.toLocaleDateString("en-US", { month: "short", day: "numeric" })}, ${time}`;
}

function formatDuration(seconds, turns) {
  if (seconds === null || seconds === undefined) return "—";
  const mins = Math.round(seconds / 60);
  return `${mins} min · ${turns ?? 0} turns`;
}

export default function StatusCard({ calls }) {
  const last = calls?.[0];

  return (
    <div className="grid grid-cols-3 gap-4">
      <div className="bg-white border border-gray-200 rounded-lg p-5">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Last Call</p>
        <p className="text-lg font-semibold text-gray-900">
          {last ? formatCallTime(last.started_at) : "No calls yet"}
        </p>
        {last?.missed && (
          <p className="text-xs text-gray-400 mt-0.5">Aria couldn't get through</p>
        )}
      </div>

      <div className="bg-white border border-gray-200 rounded-lg p-5">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Duration</p>
        <p className="text-lg font-semibold text-gray-900">
          {last?.missed ? "—" : last ? formatDuration(last.duration_seconds, last.turn_count) : "—"}
        </p>
      </div>

      <div className="bg-white border border-gray-200 rounded-lg p-5">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Mood</p>
        {last?.missed ? (
          <p className="text-sm text-gray-400 mt-0.5">No data — call not answered</p>
        ) : (
          <>
            <p className={`text-lg font-semibold ${moodColor(last?.mood_score)}`}>
              {moodLabel(last?.mood_score)}
            </p>
            {last?.emotional_state && (
              <p className="text-xs text-gray-500 mt-0.5 capitalize">{last.emotional_state}</p>
            )}
          </>
        )}
      </div>
    </div>
  );
}
