/**
 * Desktop Push Notifications Hook — uses the browser Notification API.
 * Works even when the tab is in the background.
 *
 * Usage:
 *   const { sendNotification, permission, requestPermission } = usePushNotifications();
 */

import { useCallback, useEffect, useState } from "react";

type PermissionState = "default" | "granted" | "denied";

export function usePushNotifications() {
  const [permission, setPermission] = useState<PermissionState>("default");

  useEffect(() => {
    if (typeof window !== "undefined" && "Notification" in window) {
      setPermission(Notification.permission as PermissionState);
    }
  }, []);

  const requestPermission = useCallback(async (): Promise<PermissionState> => {
    if (typeof window === "undefined" || !("Notification" in window)) {
      return "denied";
    }
    const result = await Notification.requestPermission();
    setPermission(result as PermissionState);
    return result as PermissionState;
  }, []);

  const sendNotification = useCallback(
    (title: string, options?: NotificationOptions): void => {
      if (typeof window === "undefined" || !("Notification" in window)) return;
      if (Notification.permission !== "granted") return;

      // Don't notify if tab is visible
      if (document.visibilityState === "visible") return;

      try {
        new Notification(title, {
          icon: "/favicon.ico",
          badge: "/favicon.ico",
          ...options,
        });
      } catch {
        // Silently ignore if notifications fail
      }
    },
    [],
  );

  return { sendNotification, permission, requestPermission };
}
