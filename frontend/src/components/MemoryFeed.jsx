function formatDate(isoString) {
  if (!isoString) return "";
  return new Date(isoString).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export default function MemoryFeed({ memories }) {
  const items = memories?.slice(0, 10) ?? [];

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-5">
      <p className="text-sm font-medium text-gray-700 mb-4">Recent Memories</p>
      {items.length === 0 ? (
        <p className="text-sm text-gray-400 py-4 text-center">No memories yet</p>
      ) : (
        <ul className="space-y-2">
          {items.map((m) => (
            <li
              key={m.id}
              className="border-l-2 border-blue-200 pl-3 py-1"
            >
              <p className="text-sm text-gray-800">{m.content}</p>
              <p className="text-xs text-gray-400 mt-0.5">{formatDate(m.created_at)}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
