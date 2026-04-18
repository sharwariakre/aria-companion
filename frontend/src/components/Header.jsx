export default function Header({ lastUpdated }) {
  return (
    <header className="border-b border-gray-200 bg-white px-6 py-4 flex items-center justify-between">
      <div>
        <h1 className="text-xl font-semibold text-gray-900">Aria</h1>
        <p className="text-sm text-gray-500">Margaret's Companion</p>
      </div>
      {lastUpdated && (
        <p className="text-xs text-gray-400">
          Last updated {lastUpdated}
        </p>
      )}
    </header>
  );
}
