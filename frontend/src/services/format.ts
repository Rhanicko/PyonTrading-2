export function price(value: number | null): string { return value === null ? "—" : value.toFixed(2); }
export function age(value: number | null): string { return value === null ? "—" : `${value.toFixed(1)}s`; }
export function pht(value: string | null): string { return value ? new Intl.DateTimeFormat("en-PH", { hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: "Asia/Manila", hour12: true }).format(new Date(value)) : "—"; }
export function utc(value: string | null): string { return value ? new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: "UTC", hour12: false }).format(new Date(value)) : "—"; }

