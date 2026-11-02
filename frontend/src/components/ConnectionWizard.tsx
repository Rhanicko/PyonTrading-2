import type { Connection } from "../types/api";

interface Props { connection: Connection; onRetry: () => void; onSave: (symbol: string) => Promise<void>; }

export function ConnectionWizard({ connection, onRetry, onSave }: Props) {
  const hasSymbols = connection.gold_symbols.length > 0;
  const connected = connection.terminal_connected;
  return <section className="wizard" aria-labelledby="connection-title">
    <div className="wizard-kicker">FIRST-RUN CONNECTION</div>
    <h2 id="connection-title">{connected ? "Choose the exact broker symbol for this workstation." : "Connect the terminal already signed in to your broker."}</h2>
    <p>{connected ? "MT5 is connected. Select one discovered XAUUSD / GOLD instrument; PyonTrading 2 will not guess or substitute an alias." : "PyonTrading starts your configured or detected MT5 terminal once when it opens. Sign in there if needed. If you close MT5 later, PyonTrading disconnects and does not relaunch it."}</p>
    <ol>
      <li className={connection.terminal_connected ? "complete" : "active"}><span>01</span> Install and open MetaTrader 5, then sign in to the intended demo account.</li>
      <li className={connection.terminal_connected ? "active" : "muted"}><span>02</span> Add your broker&apos;s exact XAUUSD / GOLD symbol to Market Watch.</li>
      <li className={hasSymbols ? "active" : "muted"}><span>03</span> Select the discovered symbol below. PyonTrading 2 will not guess an alias.</li>
    </ol>
    {hasSymbols && <label className="symbol-picker">Broker gold symbol
      <select defaultValue="" onChange={(event) => { if (event.target.value) void onSave(event.target.value); }}>
        <option value="" disabled>Select a discovered symbol</option>
        {connection.gold_symbols.map((symbol) => <option key={symbol.name} value={symbol.name}>{symbol.name}{symbol.visible ? "" : " (not visible)"}</option>)}
      </select>
    </label>}
    <div className="wizard-actions"><button className="button primary" onClick={onRetry}>{connected ? "Refresh symbols" : "Retry detection"}</button><code>{connection.reason_codes[0] ?? (connected ? "SYMBOL_SELECTION_REQUIRED" : "MT5_TERMINAL_NOT_AVAILABLE")}</code></div>
  </section>;
}

