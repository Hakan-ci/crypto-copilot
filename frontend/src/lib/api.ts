import type {
  Candle,
  DashboardMetrics,
  ImportAndReconstructResponse,
  ImportOrderDealsRequest,
  ImportOrderDealsResponse,
  IndicatorSnapshotCalculationResponse,
  MexcReadinessResponse,
  Position,
  PositionDetail,
  PositionFilters,
  Timeframe,
  TradeReviewResponse,
  UserTradingRules
} from "@/lib/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers
    }
  });

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    try {
      const payload = (await response.json()) as { detail?: string };
      message = payload.detail ?? message;
    } catch {
      message = response.statusText || message;
    }
    throw new ApiError(message, response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

function toQueryString(params: Record<string, string | undefined>) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value) {
      query.set(key, value);
    }
  });
  const serialized = query.toString();
  return serialized ? `?${serialized}` : "";
}

export function getDashboard(userId: string) {
  return request<DashboardMetrics>(`/users/${userId}/dashboard`);
}

export function listPositions(userId: string, filters: PositionFilters = {}) {
  const queryString = toQueryString({
    symbol: filters.symbol,
    status: filters.status,
    direction: filters.direction,
    start: filters.start,
    end: filters.end,
    timeframe: filters.timeframe
  });
  return request<Position[]>(`/users/${userId}/positions${queryString}`);
}

export function getPositionDetail(positionId: string) {
  return request<PositionDetail>(`/positions/${positionId}`);
}

export function getMexcReadiness(symbol = "BTC_USDT") {
  return request<MexcReadinessResponse>(`/mexc/readiness${toQueryString({ symbol })}`);
}

export function importOrderDeals(payload: ImportOrderDealsRequest) {
  return request<ImportOrderDealsResponse>("/mexc/import/order-deals", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function importOrderDealsAndReconstruct(payload: ImportOrderDealsRequest) {
  return request<ImportAndReconstructResponse>("/mexc/import/order-deals-and-reconstruct", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function listPositionCandles(positionId: string, timeframe: Timeframe) {
  return request<Candle[]>(`/positions/${positionId}/candles${toQueryString({ timeframe })}`);
}

export function calculateIndicatorSnapshots(positionId: string, timeframes: Timeframe[]) {
  return request<IndicatorSnapshotCalculationResponse>(
    `/positions/${positionId}/indicator-snapshots`,
    {
      method: "POST",
      body: JSON.stringify({ timeframes })
    }
  );
}

export function generateReview(positionId: string, userRules?: UserTradingRules) {
  return request<TradeReviewResponse>(`/positions/${positionId}/review`, {
    method: "POST",
    body: JSON.stringify({
      user_rules: userRules && Object.keys(userRules).length > 0 ? userRules : null
    })
  });
}
