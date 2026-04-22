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
  if (!last?.flagged && !last?.masking_detected && !last?.missed) return null;

  return (
    <div className="space-y-2">
      {last?.missed && (
        <div className="bg-gray-50 border border-gray-300 rounded-lg px-5 py-4 flex items-start gap-3">
          <span className="text-gray-400 text-lg leading-none mt-0.5">📵</span>
          <div>
            <p className="text-sm font-semibold text-gray-700">
              Aria couldn't reach Margaret. A family check-in may be helpful.
            </p>
            <p className="text-xs text-gray-500 mt-0.5">{formatTime(last.started_at)}</p>
          </div>
        </div>
      )}
      {last?.flagged && (
        <div className="bg-red-50 border border-red-200 rounded-lg px-5 py-4 flex items-start gap-3">
          <span className="text-red-500 text-lg leading-none mt-0.5">⚠</span>
          <div>
            <p className="text-sm font-semibold text-red-800">
              Aria flagged this call. Margaret may need a check-in.
            </p>
            <p className="text-xs text-red-600 mt-0.5">{formatTime(last.started_at)}</p>
          </div>
        </div>
      )}
      {last?.masking_detected && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg px-5 py-4 flex items-start gap-3">
          <span className="text-amber-500 text-lg leading-none mt-0.5">◐</span>
          <div>
            <p className="text-sm font-semibold text-amber-800">
              Aria noticed Margaret may be downplaying how she feels.
            </p>
            <p className="text-xs text-amber-600 mt-0.5">{formatTime(last.started_at)}</p>
          </div>
        </div>
      )}
    </div>
  );
}
