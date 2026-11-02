import { CandlestickSeries, ColorType, createChart, HistogramSeries, LineSeries, type IChartApi, type IPaneApi, type ISeriesApi, type Time, type UTCTimestamp } from "lightweight-charts";
import { useEffect, useMemo, useRef } from "react";
import { bollingerSeries, emaSeries, indicatorReadings, tickActivitySeries, tickActivityVwap } from "../services/chartIndicators";
import { defaultViewportRange } from "../services/chartViewport";
import type { Candle } from "../types/api";

export type ChartOverlayKey = "trend" | "vwap" | "bands" | "activity";
export type ChartOverlays = Record<ChartOverlayKey, boolean>;

interface Props { candles: Candle[]; timeframe: string; overlays: ChartOverlays; }

type CandleSeries = ISeriesApi<"Candlestick", Time>;
type LineChartSeries = ISeriesApi<"Line", Time>;
type HistogramChartSeries = ISeriesApi<"Histogram", Time>;
type ViewportRange = { from: number; to: number };

function viewportKey(timeframe: string) {
  return `pyontrading.chart.viewport.v2.xauusd.${timeframe}`;
}

function savedViewport(timeframe: string): ViewportRange | null {
  try {
    const value = JSON.parse(window.localStorage.getItem(viewportKey(timeframe)) ?? "null") as ViewportRange | null;
    return value && Number.isFinite(value.from) && Number.isFinite(value.to) && value.to > value.from ? value : null;
  } catch {
    return null;
  }
}

function saveViewport(timeframe: string, range: ViewportRange) {
  try {
    window.localStorage.setItem(viewportKey(timeframe), JSON.stringify(range));
  } catch {
    // A private browser mode may reject storage. The chart still works for this session.
  }
}

function chartData(candles: Candle[]) {
  return candles.map((item) => ({ time: Math.floor(new Date(item.open_time_utc).getTime() / 1000) as UTCTimestamp, open: item.open, high: item.high, low: item.low, close: item.close }));
}

function centeredPriceRange(candles: Candle[]) {
  const latestClose = candles.at(-1)?.close;
  if (latestClose === undefined || !candles.length) return null;
  const high = Math.max(...candles.map((item) => item.high));
  const low = Math.min(...candles.map((item) => item.low));
  const halfRange = Math.max(
    Math.abs(high - latestClose),
    Math.abs(latestClose - low),
    (high - low) * 0.2,
    Math.abs(latestClose) * 0.001,
  ) * 1.12;
  return { from: latestClose - halfRange, to: latestClose + halfRange };
}

function format(value: number | null, digits = 2): string {
  return value === null ? "—" : value.toFixed(digits);
}

export function PriceChart({ candles, timeframe, overlays }: Props) {
  const root = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const candleSeries = useRef<CandleSeries | null>(null);
  const ema20Series = useRef<LineChartSeries | null>(null);
  const ema60Series = useRef<LineChartSeries | null>(null);
  const vwapSeries = useRef<LineChartSeries | null>(null);
  const upperBandSeries = useRef<LineChartSeries | null>(null);
  const lowerBandSeries = useRef<LineChartSeries | null>(null);
  const activitySeries = useRef<HistogramChartSeries | null>(null);
  const activityPane = useRef<IPaneApi<Time> | null>(null);
  const fittedTimeframe = useRef<string | null>(null);
  const centeredPriceTimeframe = useRef<string | null>(null);
  const readings = useMemo(() => indicatorReadings(candles), [candles]);

  useEffect(() => {
    if (!root.current) return;
    const element = root.current;
    const instance = createChart(element, {
      width: element.clientWidth,
      height: element.clientHeight || 512,
      layout: { background: { type: ColorType.Solid, color: "#090e13" }, textColor: "#aebbc2", fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" },
      grid: { vertLines: { color: "rgba(157, 177, 187, .08)" }, horzLines: { color: "rgba(157, 177, 187, .08)" } },
      rightPriceScale: { visible: true, autoScale: false, minimumWidth: 66, borderColor: "rgba(157, 177, 187, .2)", scaleMargins: { top: 0.08, bottom: 0.12 } },
      timeScale: { borderColor: "rgba(157, 177, 187, .2)", timeVisible: true, secondsVisible: false, rightOffset: 28, barSpacing: 7, minBarSpacing: 0.5, lockVisibleTimeRangeOnResize: true },
      handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
    });
    candleSeries.current = instance.addSeries(CandlestickSeries, { upColor: "#5ee3ae", downColor: "#ff8278", borderVisible: false, wickUpColor: "#5ee3ae", wickDownColor: "#ff8278" });
    ema20Series.current = instance.addSeries(LineSeries, { color: "#66c7e8", lineWidth: 1, title: "EMA 20", lastValueVisible: false, priceLineVisible: false });
    ema60Series.current = instance.addSeries(LineSeries, { color: "#b99ce3", lineWidth: 1, title: "EMA 60", lastValueVisible: false, priceLineVisible: false });
    vwapSeries.current = instance.addSeries(LineSeries, { color: "#e1b64d", lineWidth: 1, lineStyle: 2, title: "Session VWAP - MT5 tick-activity proxy", lastValueVisible: false, priceLineVisible: false });
    upperBandSeries.current = instance.addSeries(LineSeries, { color: "rgba(154, 174, 188, .58)", lineWidth: 1, lineStyle: 2, title: "Bollinger upper", lastValueVisible: false, priceLineVisible: false });
    lowerBandSeries.current = instance.addSeries(LineSeries, { color: "rgba(154, 174, 188, .58)", lineWidth: 1, lineStyle: 2, title: "Bollinger lower", lastValueVisible: false, priceLineVisible: false });
    const pane = instance.addPane();
    pane.setHeight(94);
    activityPane.current = pane;
    activitySeries.current = instance.addSeries(HistogramSeries, { title: "MT5 tick activity", priceScaleId: "activity", priceFormat: { type: "volume" }, lastValueVisible: false, priceLineVisible: false, base: 0 }, pane.paneIndex());
    instance.priceScale("activity", pane.paneIndex()).applyOptions({ visible: false });
    const observer = new ResizeObserver(() => instance.applyOptions({
      width: element.clientWidth,
      height: element.clientHeight || 512,
    }));
    const timeScale = instance.timeScale();
    const persistViewport = (range: ViewportRange | null) => {
      if (!range || !fittedTimeframe.current) return;
      saveViewport(fittedTimeframe.current, range);
    };
    timeScale.subscribeVisibleLogicalRangeChange(persistViewport);
    observer.observe(element);
    chart.current = instance;
    return () => {
      observer.disconnect();
      timeScale.unsubscribeVisibleLogicalRangeChange(persistViewport);
      instance.remove();
      chart.current = null;
      candleSeries.current = null;
      ema20Series.current = null;
      ema60Series.current = null;
      vwapSeries.current = null;
      upperBandSeries.current = null;
      lowerBandSeries.current = null;
      activitySeries.current = null;
      activityPane.current = null;
    };
  }, []);

  useEffect(() => {
    const bands = bollingerSeries(candles);
    const timeScale = chart.current?.timeScale();
    const visibleRange = timeScale?.getVisibleLogicalRange() ?? null;
    candleSeries.current?.setData(chartData(candles));
    ema20Series.current?.setData(emaSeries(candles, 20));
    ema60Series.current?.setData(emaSeries(candles, 60));
    vwapSeries.current?.setData(tickActivityVwap(candles));
    upperBandSeries.current?.setData(bands.upper);
    lowerBandSeries.current?.setData(bands.lower);
    activitySeries.current?.setData(tickActivitySeries(candles));
    if (centeredPriceTimeframe.current !== timeframe) {
      const range = centeredPriceRange(candles);
      if (range) {
        const priceScale = chart.current?.priceScale("right");
        priceScale?.setAutoScale(false);
        priceScale?.setVisibleRange(range);
      }
      centeredPriceTimeframe.current = timeframe;
    }
    if (timeScale && fittedTimeframe.current !== timeframe) {
      const storedViewport = savedViewport(timeframe);
      timeScale.setVisibleLogicalRange(storedViewport ?? defaultViewportRange(candles.length));
      fittedTimeframe.current = timeframe;
    } else if (timeScale && visibleRange) {
      // Retain the trader's zoom and manual pan through websocket/API updates.
      // The view never follows a new bar automatically.
      timeScale.setVisibleLogicalRange(visibleRange);
    }
  }, [candles, timeframe]);

  useEffect(() => {
    ema20Series.current?.applyOptions({ visible: overlays.trend });
    ema60Series.current?.applyOptions({ visible: overlays.trend });
    vwapSeries.current?.applyOptions({ visible: overlays.vwap });
    upperBandSeries.current?.applyOptions({ visible: overlays.bands });
    lowerBandSeries.current?.applyOptions({ visible: overlays.bands });
    activitySeries.current?.applyOptions({ visible: overlays.activity });
    activityPane.current?.setHeight(overlays.activity ? 94 : 0);
  }, [overlays]);

  const trend = readings.ema20 === null || readings.ema60 === null ? "UNAVAILABLE" : readings.ema20 > readings.ema60 ? "EMA UP" : readings.ema20 < readings.ema60 ? "EMA DOWN" : "EMA FLAT";
  const resetView = () => {
    const timeScale = chart.current?.timeScale();
    if (!timeScale) return;
    try {
      window.localStorage.removeItem(viewportKey(timeframe));
    } catch {
      // Resetting the in-memory view remains available when storage is unavailable.
    }
    timeScale.resetTimeScale();
    timeScale.setVisibleLogicalRange(defaultViewportRange(candles.length));
    const range = centeredPriceRange(candles);
    if (range) {
      const priceScale = chart.current?.priceScale("right");
      priceScale?.setAutoScale(false);
      priceScale?.setVisibleRange(range);
    }
  };

  return <div className="chart-wrap">
    <div className="visually-hidden" aria-label="Chart overlays">
      {overlays.trend && <span className="legend-trend">EMA 20 / 60</span>}
      {overlays.vwap && <span className="legend-vwap">SESSION VWAP · MT5 TICK-ACTIVITY PROXY</span>}
      {overlays.bands && <span className="legend-bands">BOLLINGER 20,2</span>}
      {overlays.activity && <span className="legend-activity">TICK ACTIVITY · NOT EXECUTED VOLUME</span>}
    </div>
    <div className="chart-canvas" ref={root} aria-label="XAUUSD broker candlestick chart with research overlays" />
    <button type="button" className="chart-reset-view" onClick={resetView}>Reset chart view</button>
    <div className="chart-readings" aria-label="Completed-candle chart readings">
      <span><b>Trend</b>{trend}</span><span><b>RSI 14</b>{format(readings.rsi14, 1)}</span><span><b>ATR 14</b>{format(readings.atr14)}</span><span><b>Activity</b>{readings.relativeActivity === null ? "—" : `${readings.relativeActivity.toFixed(2)}×`}</span><span><b>Basis</b>COMPLETED CANDLES</span>
    </div>
  </div>;
}
