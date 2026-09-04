import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { VitalSign } from "../../entities/clinical/model";
import { formatDateTime } from "../../shared/utils/format";

type Point = { timestamp: string; label: string; heartRate?: number; temperature?: number; morse?: number };

export function TrendChart({ observations }: { observations: VitalSign[] }) {
  const byTime = new Map<string, Point>();
  for (const item of observations) {
    if (!item.measuredAt || item.value === undefined || !["heart-rate", "temperature", "morse-score"].includes(item.kind)) continue;
    const point = byTime.get(item.measuredAt) ?? { timestamp: item.measuredAt, label: formatDateTime(item.measuredAt) };
    if (item.kind === "heart-rate") point.heartRate = item.value;
    if (item.kind === "temperature") point.temperature = item.value;
    if (item.kind === "morse-score") point.morse = item.value;
    byTime.set(item.measuredAt, point);
  }
  const data = [...byTime.values()].sort((a, b) => a.timestamp.localeCompare(b.timestamp)).slice(-30);
  if (data.length < 2) return <div className="chart-empty"><strong>Verlauf noch nicht verfügbar</strong><span>Mindestens zwei zeitlich gültige Messpunkte werden benötigt.</span></div>;
  return (
    <div className="chart-wrap" role="img" aria-label="Zeitlicher Verlauf von Herzfrequenz, Temperatur und Morse Score">
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={data} margin={{ top: 16, right: 20, left: 0, bottom: 4 }}>
          <CartesianGrid strokeDasharray="4 4" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 11 }} minTickGap={24} />
          <YAxis tick={{ fontSize: 11 }} width={36} domain={["auto", "auto"]} />
          <Tooltip contentStyle={{ borderRadius: 10, borderColor: "#dbe5e8" }} />
          <Legend />
          <Line type="linear" dataKey="heartRate" name="Herzfrequenz (/min)" stroke="#087f8c" strokeWidth={2} dot={false} connectNulls={false} isAnimationActive={false} />
          <Line type="linear" dataKey="temperature" name="Temperatur (°C)" stroke="#c66a15" strokeWidth={2} dot={false} connectNulls={false} isAnimationActive={false} />
          <Line type="linear" dataKey="morse" name="Morse Score" stroke="#6554c0" strokeWidth={2} dot={false} connectNulls={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
      <p className="chart-caption">Gemeinsame Skala zur kompakten Orientierung; Einheiten stehen in der Legende. Werte nicht zwischen Messpunkten interpolieren.</p>
    </div>
  );
}
