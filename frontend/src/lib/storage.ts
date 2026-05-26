"use client";

import { useEffect, useState } from "react";

import type { UserTradingRules } from "@/lib/types";

export const DEVELOPMENT_USER_ID_KEY = "crypto-copilot.development-user-id";
export const TRADING_PLAN_KEY = "crypto-copilot.trading-plan";

export function useDevelopmentUserId() {
  const [userId, setUserIdState] = useState("");
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    setUserIdState(window.localStorage.getItem(DEVELOPMENT_USER_ID_KEY) ?? "");
    setIsReady(true);
  }, []);

  function setUserId(nextUserId: string) {
    const trimmed = nextUserId.trim();
    setUserIdState(trimmed);
    if (trimmed) {
      window.localStorage.setItem(DEVELOPMENT_USER_ID_KEY, trimmed);
    } else {
      window.localStorage.removeItem(DEVELOPMENT_USER_ID_KEY);
    }
  }

  return { userId, setUserId, isReady };
}

export function loadTradingPlan(): UserTradingRules {
  if (typeof window === "undefined") {
    return {};
  }
  const raw = window.localStorage.getItem(TRADING_PLAN_KEY);
  if (!raw) {
    return {};
  }
  try {
    return JSON.parse(raw) as UserTradingRules;
  } catch {
    return {};
  }
}

export function saveTradingPlan(plan: UserTradingRules) {
  window.localStorage.setItem(TRADING_PLAN_KEY, JSON.stringify(plan));
}
