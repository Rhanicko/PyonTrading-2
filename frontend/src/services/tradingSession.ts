// Indicative FX business-hour convention, not the broker's XAUUSD schedule.
// Local-hour table: https://www.forex.com/en-au/forex-trading/forex-market-hours/
// Checked 2026-11-16. IANA zones handle each city's independent DST dates.
const sessions = [
  { label: "Sydney", zone: "Australia/Sydney", start: 8, end: 16 },
  { label: "Tokyo", zone: "Asia/Tokyo", start: 9, end: 18 },
  { label: "London", zone: "Europe/London", start: 8, end: 16 },
  { label: "New York", zone: "America/New_York", start: 8, end: 17 },
].map((session) => ({ ...session, formatter: new Intl.DateTimeFormat("en-US", {
  timeZone: session.zone, weekday: "short", hour: "2-digit", hourCycle: "h23",
}) }));

function localClock(formatter: Intl.DateTimeFormat, now: Date) {
  const parts = formatter.formatToParts(now);
  return { day: parts.find((part) => part.type === "weekday")!.value,
    hour: Number(parts.find((part) => part.type === "hour")!.value) };
}

export function tradingSession(now: Date): { label: string; overlap: boolean } {
  if (!Number.isFinite(now.getTime())) return { label: "Session unavailable", overlap: false };
  const newYork = localClock(sessions[3].formatter, now);
  if (newYork.day === "Sat" || (newYork.day === "Fri" && newYork.hour >= 17)
    || (newYork.day === "Sun" && newYork.hour < 17)) {
    return { label: "Weekend", overlap: false };
  }
  const active = sessions.filter((session) => {
    const local = localClock(session.formatter, now);
    return local.day !== "Sat" && local.day !== "Sun" && local.hour >= session.start && local.hour < session.end;
  });
  return { label: active.length ? active.map((session) => session.label).join(" + ") : "Between sessions", overlap: active.length > 1 };
}
