function formatTime(isoString) {
  if (!isoString) return "";
  const date = new Date(isoString);
  return date.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
}

export default function AlertBanner({ calls }) {
  const last = calls?.[0];
  if (!last?.flagged) return null;

  return (
    <div className="bg-red-50 border border-red-200 rounded-lg px-5 py-4 flex items-start gap-3">
      <span className="text-red-500 text-lg leading-none mt-0.5">⚠</span>
      <div>
        <p className="text-sm font-semibold text-red-800">
          Aria flagged this call. Margaret may need a check-in.
        </p>
        <p className="text-xs text-red-600 mt-0.5">
          {formatTime(last.started_at)}
        </p>
      </div>
    </div>
  );
}
