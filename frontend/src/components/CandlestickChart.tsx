"use client";

import { createChart, type IChartApi, type UTCTimestamp } from "lightweight-charts";
import { useEffect, useRef } from "react";

export interface ChartCandle {
  time: UTCTimestamp;
  open: number;
  high: number;
  low: number;
  close: number;
}

export function CandlestickChart({ data = [] }: { data?: ChartCandle[] }) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!containerRef.current || data.length === 0) {
      return undefined;
    }

    const chart: IChartApi = createChart(containerRef.current, {
      height: 280,
      layout: {
        background: { color: "#ffffff" },
        textColor: "#334155"
      },
      grid: {
        vertLines: { color: "#ece7de" },
        horzLines: { color: "#ece7de" }
      },
      rightPriceScale: {
        borderColor: "#d8d3ca"
      },
      timeScale: {
        borderColor: "#d8d3ca"
      }
    });
    const series = chart.addCandlestickSeries({
      upColor: "#047857",
      downColor: "#b91c1c",
      wickUpColor: "#047857",
      wickDownColor: "#b91c1c",
      borderVisible: false
    });
    series.setData(data);
    chart.timeScale().fitContent();

    const resizeObserver = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    });
    resizeObserver.observe(containerRef.current);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
    };
  }, [data]);

  if (data.length === 0) {
    return (
      <div className="flex h-72 items-center justify-center rounded-md border border-dashed border-stone-300 bg-white text-center text-sm text-slate-600">
        Candle chart will appear after snapshots prepare MEXC candles.
      </div>
    );
  }

  return <div ref={containerRef} className="h-72 w-full rounded-md border border-stone-200 bg-white" />;
}
