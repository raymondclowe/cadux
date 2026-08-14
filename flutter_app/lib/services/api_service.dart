import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import '../models/hermes_session.dart';
import '../models/chat_message.dart';
import 'config_service.dart';

/// Service for all Hermes Gateway HTTP API calls with auto-reconnect.
class ApiService {
  final ConfigService config;
  int _reconnectAttempts = 0;
  static const int _maxReconnectAttempts = 10;
  Timer? _reconnectTimer;
  bool _keepAlive = false;

  // Configurable timeouts
  Duration sessionTimeout = const Duration(seconds: 10);
  Duration messageTimeout = const Duration(seconds: 10);
  Duration chatTimeout = const Duration(seconds: 180);

  final ValueNotifier<String> status = ValueNotifier('Tap Settings or scan QR');
  final ValueNotifier<bool> isConnecting = ValueNotifier(false);
  final ValueNotifier<List<HermesSession>> sessions =
      ValueNotifier(<HermesSession>[]);

  ApiService({required this.config});

  /// Start auto-reconnect loop. Call when config is saved.
  void startKeepAlive() {
    _keepAlive = true;
    _reconnectAttempts = 0;
    _doReconnect();
  }

  void stopKeepAlive() {
    _keepAlive = false;
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
  }

  void _doReconnect() {
    if (!_keepAlive) return;
    if (_reconnectAttempts >= _maxReconnectAttempts) {
      status.value = 'Connection lost — max retries reached';
      return;
    }
    _reconnectTimer?.cancel();
    final delay = _backoffDelay(_reconnectAttempts);
    _reconnectTimer = Timer(delay, () {
      if (!_keepAlive) return;
      loadSessions(silent: true).then((ok) {
        if (!ok && _keepAlive) {
          _reconnectAttempts++;
          _doReconnect();
        }
      });
    });
  }

  Duration _backoffDelay(int attempt) {
    // Exponential: 1s, 2s, 4s, 8s, 16s, 32s, capped at 60s
    final seconds = (1 << attempt).clamp(1, 60);
    return Duration(seconds: seconds);
  }

  String? _lastError;
  String? get lastError => _lastError;

  Future<bool> loadSessions({bool silent = false}) async {
    if (!config.isConfigured) return false;
    if (!silent) {
      isConnecting.value = true;
      status.value = 'Connecting…';
    }
    try {
      final resp = await http
          .get(
            Uri.parse('${config.url}/api/sessions'),
            headers: {'Authorization': 'Bearer ${config.key}'},
          )
          .timeout(sessionTimeout);
      if (resp.statusCode == 200) {
        final data = jsonDecode(resp.body);
        sessions.value = (data['data'] as List?)
                ?.map((j) => HermesSession.fromJson(j))
                .toList() ??
            [];
        _reconnectAttempts = 0; // Reset on success
        if (sessions.value.isEmpty) {
          status.value = 'No sessions — create one';
        } else {
          status.value =
              '${sessions.value.length} session(s)';
        }
        isConnecting.value = false;
        return true;
      } else {
        _setError('Server returned ${resp.statusCode}');
        return false;
      }
    } catch (e) {
      _setError('Connection failed: ${e.toString().split('\n').first}');
      if (!silent) status.value = 'Connection failed';
      isConnecting.value = false;
      return false;
    }
  }

  Future<List<ChatMessage>> loadMessages(String sessionId) async {
    try {
      final resp = await http
          .get(
            Uri.parse('${config.url}/api/sessions/$sessionId/messages'),
            headers: {'Authorization': 'Bearer ${config.key}'},
          )
          .timeout(messageTimeout);
      if (resp.statusCode == 200) {
        final data = jsonDecode(resp.body);
        return (data['data'] as List? ?? [])
            .map((m) => ChatMessage(
                role: m['role'] ?? 'user', text: m['content'] ?? ''))
            .toList();
      }
      _setError('Failed to load messages: ${resp.statusCode}');
    } catch (e) {
      _setError('Message load error: ${e.toString().split('\n').first}');
    }
    return [];
  }

  Future<String?> createSession() async {
    try {
      final resp = await http
          .post(
            Uri.parse('${config.url}/api/sessions'),
            headers: {
              'Authorization': 'Bearer ${config.key}',
              'Content-Type': 'application/json'
            },
            body: '{}',
          )
          .timeout(sessionTimeout);
      if (resp.statusCode == 200 || resp.statusCode == 201) {
        final data = jsonDecode(resp.body);
        final sid = data['session']?['id']?.toString() ??
            data['id']?.toString() ??
            data['session_id']?.toString();
        if (sid != null) {
          sessions.value = [
            HermesSession(id: sid),
            ...sessions.value,
          ];
        }
        return sid;
      }
      _setError('Failed to create session');
    } catch (e) {
      _setError('Create session error: ${e.toString().split('\n').first}');
    }
    return null;
  }

  Future<bool> deleteSession(String id) async {
    try {
      await http
          .delete(
            Uri.parse('${config.url}/api/sessions/$id'),
            headers: {'Authorization': 'Bearer ${config.key}'},
          )
          .timeout(const Duration(seconds: 5));
      sessions.value = sessions.value.where((s) => s.id != id).toList();
      return true;
    } catch (e) {
      _setError('Delete failed: ${e.toString().split('\n').first}');
      return false;
    }
  }

  Future<String?> sendMessage(
    String sessionId,
    String text, {
    bool ttsEnabled = false,
    String gpsMode = 'none',
  }) async {
    try {
      final Map<String, dynamic> meta = {
        'source': 'cadux',
        'version': '0.5.0',
      };
      if (ttsEnabled) meta['tts'] = true;
      if (gpsMode != 'none') meta['gps'] = {'accuracy': gpsMode};

      final resp = await http
          .post(
            Uri.parse('${config.url}/api/sessions/$sessionId/chat/stream'),
            headers: {
              'Authorization': 'Bearer ${config.key}',
              'Content-Type': 'application/json',
            },
            body: jsonEncode({'message': text, 'metadata': meta}),
          )
          .timeout(chatTimeout);
      if (resp.statusCode == 200) {
        String buffer = '';
        for (final line in resp.body.split('\n')) {
          if (!line.startsWith('data: ')) continue;
          final d = line.substring(6);
          if (d == '[DONE]') break;
          try {
            final chunk = jsonDecode(d);
            if (chunk['delta'] != null) buffer += chunk['delta'];
          } catch (_) {}
        }
        return buffer;
      }
      _setError('Chat failed: ${resp.statusCode}');
    } catch (e) {
      _setError('Chat error: ${e.toString().split('\n').first}');
    }
    return null;
  }

  void _setError(String msg) {
    _lastError = msg;
    debugPrint('[ApiService] $msg');
  }

  void clearError() {
    _lastError = null;
  }

  void dispose() {
    stopKeepAlive();
    status.dispose();
    isConnecting.dispose();
    sessions.dispose();
  }
}
