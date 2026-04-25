import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
  Dot,
} from "recharts";

const ALERT_THRESHOLD = 0.35;

function formatDate(isoString) {
  if (!isoString) return "";
  const d = new Date(isoString.endsWith("Z") ? isoString : isoString + "Z");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function CustomDot(props) {
  const { cx, cy, payload } = props;
  const color = payload.mood_score < ALERT_THRESHOLD ? "#dc2626" : "#2563eb";
  return <circle cx={cx} cy={cy} r={5} fill={color} stroke="white" strokeWidth={2} />;
}

function CustomTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  const score = d.mood_score;
  const color = score < ALERT_THRESHOLD ? "#dc2626" : score > 0.6 ? "#16a34a" : "#d97706";
  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm px-3 py-2 text-sm">
      <p className="text-gray-500">{formatDate(d.started_at)}</p>
      <p className="font-semibold" style={{ color }}>
        Score: {(score * 100).toFixed(0)}
      </p>
      {d.flagged && <p className="text-red-600 text-xs">Flagged</p>}
    </div>
  );
}

export default function MoodChart({ data }) {
  if (!data?.length) {
    return (
      <div className="bg-white border border-gray-200 rounded-lg p-5">
        <p className="text-sm font-medium text-gray-700 mb-4">7-Day Mood Trend</p>
        <p className="text-sm text-gray-400 text-center py-8">No mood data yet</p>
      </div>
    );
  }

  const chartData = data.map((d) => ({
    ...d,
    date: formatDate(d.started_at),
    mood_score: d.mood_score,
  }));

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-5">
      <p className="text-sm font-medium text-gray-700 mb-4">7-Day Mood Trend</p>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 12, fill: "#6b7280" }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            domain={[0, 1]}
            ticks={[0, 0.25, 0.5, 0.75, 1]}
            tick={{ fontSize: 12, fill: "#6b7280" }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v) => `${(v * 100).toFixed(0)}`}
            label={{ value: "Mood", angle: -90, position: "insideLeft", offset: 10, style: { fontSize: 11, fill: "#9ca3af" } }}
          />
          <Tooltip content={<CustomTooltip />} />
          <ReferenceLine
            y={ALERT_THRESHOLD}
            stroke="#fca5a5"
            strokeDasharray="4 4"
            label={{ value: "Alert threshold", position: "right", fontSize: 11, fill: "#fca5a5" }}
          />
          <Line
            type="monotone"
            dataKey="mood_score"
            stroke="#2563eb"
            strokeWidth={2}
            dot={<CustomDot />}
            activeDot={{ r: 6 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
