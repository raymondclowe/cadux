package com.cadux.cadux

import android.content.Intent
import android.content.Context
import android.provider.Settings
import android.os.Bundle
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    private val DEEPLINK_CHANNEL = "cadux/deeplink"
    private val NOTIFICATION_CHANNEL = "cadux/notifications"

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        // Deep link channel
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, DEEPLINK_CHANNEL)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "getInitialDeepLink" -> result.success(getDeepLinkFromIntent(intent))
                    else -> result.notImplemented()
                }
            }

        // Notification channel
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, NOTIFICATION_CHANNEL)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "getPendingNotifications" -> {
                        val pending = CaduxNotificationService.getPending()
                        result.success(pending)
                    }
                    "isNotificationListenerEnabled" -> {
                        result.success(isNotificationListenerEnabled())
                    }
                    "openNotificationSettings" -> {
                        openNotificationSettings()
                        result.success(null)
                    }
                    else -> result.notImplemented()
                }
            }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        val link = getDeepLinkFromIntent(intent)
        if (link != null) {
            val engine = flutterEngine
            if (engine != null) {
                MethodChannel(engine.dartExecutor.binaryMessenger, DEEPLINK_CHANNEL)
                    .invokeMethod("onDeepLink", link)
            }
        }
    }

    private fun getDeepLinkFromIntent(intent: Intent?): String? {
        val uri = intent?.data ?: return null
        val scheme = uri.scheme ?: return null
        return if (scheme == "cadux" || scheme == "https" || scheme == "http") {
            uri.toString()
        } else null
    }

    private fun isNotificationListenerEnabled(): Boolean {
        val flat = Settings.Secure.getString(
            contentResolver,
            "enabled_notification_listeners"
        )
        return flat?.contains(packageName) == true
    }

    private fun openNotificationSettings() {
        try {
            val intent = Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            startActivity(intent)
        } catch (_: Exception) {
            // Fallback to app notification settings
            try {
                val intent = Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
                intent.putExtra(Settings.EXTRA_APP_PACKAGE, packageName)
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                startActivity(intent)
            } catch (_: Exception) {
                // Can't open settings — user must navigate manually
            }
        }
    }
}
