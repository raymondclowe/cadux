package com.cadux.cadux

import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.app.Notification

/**
 * Captures all notifications posted to the device and makes them available
 * to Flutter via a static queue that MainActivity polls.
 */
class CaduxNotificationService : NotificationListenerService() {

    companion object {
        private val pending = mutableListOf<Map<String, Any?>>()

        @Synchronized
        fun getPending(): List<Map<String, Any?>> {
            val result = pending.toList()
            pending.clear()
            return result
        }
    }

    override fun onNotificationPosted(sbn: StatusBarNotification?) {
        super.onNotificationPosted(sbn)
        if (sbn == null) return
        try {
            val notification = sbn.notification
            val extras = notification.extras
            val pkg = sbn.packageName

            // Try to get app name from package manager
            val appName = try {
                packageManager.getApplicationLabel(
                    packageManager.getApplicationInfo(pkg, 0)
                ).toString()
            } catch (_: Exception) {
                pkg
            }

            val data = mapOf<String, Any?>(
                "packageName" to pkg,
                "appName" to appName,
                "title" to extras.getCharSequence(Notification.EXTRA_TITLE)?.toString(),
                "text" to extras.getCharSequence(Notification.EXTRA_TEXT)?.toString(),
                "category" to notification.category,
                "postTime" to sbn.postTime,
                "isOngoing" to sbn.isOngoing,
                "isClearable" to sbn.isClearable,
                "groupKey" to notification.group,
            )

            synchronized(pending) {
                // Keep at most 200 pending notifications
                if (pending.size < 200) {
                    pending.add(data)
                }
            }
        } catch (_: Exception) {
            // Never crash — this runs in a system service context
        }
    }

    override fun onNotificationRemoved(sbn: StatusBarNotification?) {
        super.onNotificationRemoved(sbn)
    }
}
