/**
 * useNotificationBadge — updates document.title with an unread alert count badge.
 * Call with the current unread count; set to 0 to clear the badge.
 */

import { useEffect } from "react";

const BASE_TITLE = "AI Trading Navigator";

export function useNotificationBadge(unreadCount: number): void {
  useEffect(() => {
    document.title = unreadCount > 0
      ? `(${unreadCount}) ${BASE_TITLE}`
      : BASE_TITLE;

    return () => {
      document.title = BASE_TITLE;
    };
  }, [unreadCount]);
}
