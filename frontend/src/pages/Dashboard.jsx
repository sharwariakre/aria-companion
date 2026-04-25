import { useEffect, useRef, useState } from "react";
import { fetchUsers, fetchCalls, fetchMoodHistory, fetchMemories } from "../api";
import Header from "../components/Header";
import StatusCard from "../components/StatusCard";
import AlertBanner from "../components/AlertBanner";
import MoodChart from "../components/MoodChart";
import MemoryFeed from "../components/MemoryFeed";

const POLL_INTERVAL = 60_000;

function formatUpdatedAt(date) {
  return date.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
}

function getUrlUserId() {
  return new URLSearchParams(window.location.search).get("user");
}

export default function Dashboard() {
  const [users, setUsers] = useState([]);
  const [selectedUserId, setSelectedUserId] = useState(null);
  const [calls, setCalls] = useState([]);
  const [moodHistory, setMoodHistory] = useState([]);
  const [memories, setMemories] = useState([]);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const intervalRef = useRef(null);
  const userIdRef = useRef(null);

  useEffect(() => {
    fetchUsers()
      .then((list) => {
        setUsers(list);
        const urlId = getUrlUserId();
        const match = list.find((u) => u.user_id === urlId);
        const initial = match ? urlId : list[0]?.user_id;
        setSelectedUserId(initial);
        userIdRef.current = initial;
      })
      .catch(() => setError("Could not reach the Aria backend. Is it running?"));
  }, []);

  async function load(isManual = false, userId = userIdRef.current) {
    if (!userId) return;
    if (isManual) setRefreshing(true);
    try {
      const [c, m, mem] = await Promise.all([
        fetchCalls(userId),
        fetchMoodHistory(userId),
        fetchMemories(userId),
      ]);
      setCalls(c);
      setMoodHistory(m);
      setMemories(mem);
      setLastUpdated(formatUpdatedAt(new Date()));
      setError(null);
    } catch (e) {
      setError("Could not reach the Aria backend. Is it running?");
    } finally {
      if (isManual) setRefreshing(false);
    }
  }

  function startPolling() {
    stopPolling();
    intervalRef.current = setInterval(() => {
      if (!document.hidden) load();
    }, POLL_INTERVAL);
  }

  function stopPolling() {
    if (intervalRef.current) clearInterval(intervalRef.current);
  }

  useEffect(() => {
    if (!selectedUserId) return;
    userIdRef.current = selectedUserId;
    const url = new URL(window.location);
    url.searchParams.set("user", selectedUserId);
    window.history.replaceState({}, "", url);

    load(false, selectedUserId);
    startPolling();

    const onVisibility = () => {
      if (!document.hidden) {
        load();
        startPolling();
      } else {
        stopPolling();
      }
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      stopPolling();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [selectedUserId]);

  const selectedUser = users.find((u) => u.user_id === selectedUserId);

  return (
    <div className="min-h-screen bg-gray-50">
      <Header
        user={selectedUser}
        users={users}
        onSelectUser={(id) => setSelectedUserId(id)}
        lastUpdated={lastUpdated}
        onRefresh={() => load(true)}
        refreshing={refreshing}
      />

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
