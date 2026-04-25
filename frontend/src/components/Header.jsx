export default function Header({ user, users, onSelectUser, lastUpdated, onRefresh, refreshing }) {
  return (
    <header className="border-b border-gray-200 bg-white px-6 py-4 flex items-center justify-between">
      <div>
        <h1 className="text-xl font-semibold text-gray-900">Aria</h1>
        {users?.length > 1 ? (
          <select
            className="text-sm text-gray-500 mt-0.5 border-none bg-transparent cursor-pointer focus:outline-none"
            value={user?.user_id ?? ""}
            onChange={(e) => onSelectUser(e.target.value)}
          >
            {users.map((u) => (
              <option key={u.user_id} value={u.user_id}>
                {u.name}'s Companion
              </option>
            ))}
          </select>
        ) : (
          <p className="text-sm text-gray-500">{user?.name ? `${user.name}'s Companion` : "Companion"}</p>
        )}
      </div>
      <div className="flex items-center gap-3">
        {lastUpdated && (
          <p className="text-xs text-gray-400">Last updated {lastUpdated}</p>
        )}
        <button
          onClick={onRefresh}
          disabled={refreshing}
          className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-700 border border-gray-200 rounded-md px-2.5 py-1.5 transition-colors disabled:opacity-50"
        >
          <svg
            className={`w-3.5 h-3.5 ${refreshing ? "animate-spin" : ""}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          {refreshing ? "Refreshing…" : "Refresh"}
        </button>
      </div>
    </header>
  );
}
