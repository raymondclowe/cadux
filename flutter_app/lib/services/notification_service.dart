import 'dart:async';
import 'dart:convert';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import '../models/notification_data.dart';
import 'config_service.dart';

/// Bridges Android NotificationListenerService to Dart.
/// Polls the native side for new notifications and forwards them to Hermes.
class NotificationService {
  static const _channel = MethodChannel('cadux/notifications');

  final ConfigService config;
  bool _enabled = false;
  Timer? _pollTimer;

  bool get isEnabled => _enabled;

  NotificationService({required this.config});

  Future<bool> checkPermission() async {
    try {
      return await _channel.invokeMethod('isNotificationListenerEnabled') == true;
    } catch (_) {
      return false;
    }
  }

  Future<void> openSettings() async {
    try {
      await _channel.invokeMethod('openNotificationSettings');
    } catch (_) {}
  }

  void start() {
    _enabled = true;
    _pollTimer?.cancel();
    _pollTimer = Timer.periodic(const Duration(seconds: 3), (_) => _poll());
    _poll(); // Immediate first poll
  }

  void stop() {
    _enabled = false;
    _pollTimer?.cancel();
    _pollTimer = null;
  }

  Future<void> _poll() async {
    if (!_enabled || !config.isConfigured) return;
    try {
      final pending =
          await _channel.invokeListMethod<Map>('getPendingNotifications');
      if (pending == null || pending.isEmpty) return;

      for (final map in pending) {
        final notification = NotificationData.fromJson(
            Map<String, dynamic>.from(map));
        await _forward(notification);
      }
    } catch (_) {
      // Silently skip — don't spam user on polling failures
    }
  }

  Future<void> _forward(NotificationData notification) async {
    try {
      await http
          .post(
            Uri.parse('${config.notificationUrl}/api/notifications'),
            headers: {
              'Authorization': 'Bearer ${config.key}',
              'Content-Type': 'application/json',
            },
            body: jsonEncode(notification.toJson()),
          )
          .timeout(const Duration(seconds: 5));
    } catch (_) {
      // Non-critical — notification forwarding failures shouldn't disrupt chat
    }
  }

  void dispose() {
    stop();
  }
}
