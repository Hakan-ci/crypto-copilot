"use client";

import { useEffect, useState } from "react";

export const DEVELOPMENT_USER_ID_KEY = "crypto-copilot.development-user-id";

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
