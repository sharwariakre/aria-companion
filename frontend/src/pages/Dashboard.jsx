import { useEffect, useState } from "react";
import { fetchCalls, fetchMoodHistory, fetchMemories } from "../api";
import Header from "../components/Header";
import StatusCard from "../components/StatusCard";
import AlertBanner from "../components/AlertBanner";
import MoodChart from "../components/MoodChart";
import MemoryFeed from "../components/MemoryFeed";

function formatUpdatedAt(date) {
  return date.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
}

export default function Dashboard() {
  const [calls, setCalls] = useState([]);
  const [moodHistory, setMoodHistory] = useState([]);
  const [memories, setMemories] = useState([]);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [error, setError] = useState(null);

  async function load() {
    try {
      const [c, m, mem] = await Promise.all([
        fetchCalls(),
        fetchMoodHistory(),
        fetchMemories(),
      ]);
      setCalls(c);
      setMoodHistory(m);
      setMemories(mem);
      setLastUpdated(formatUpdatedAt(new Date()));
      setError(null);
    } catch (e) {
      setError("Could not reach the Aria backend. Is it running?");
    }
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="min-h-screen bg-gray-50">
      <Header lastUpdated={lastUpdated} />

      <main className="max-w-4xl mx-auto px-6 py-8 space-y-6">
        {error && (
          <div className="bg-yellow-50 border border-yellow-200 rounded-lg px-4 py-3 text-sm text-yellow-800">
            {error}
          </div>
        )}

        <StatusCard calls={calls} />
        <AlertBanner calls={calls} />
        <MoodChart data={moodHistory} />
        <MemoryFeed memories={memories} />
      </main>
    </div>
  );
}
