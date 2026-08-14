import 'dart:convert';
import 'dart:io';
import 'package:shared_preferences/shared_preferences.dart';

class ConfigService {
  String url = '';
  String key = '';

  Future<bool> load() async {
    // Try durable config file first
    try {
      final dir = Directory('/data/data/com.cadux.cadux/files');
      final file = File('${dir.path}/cadux_config.json');
      if (await file.exists()) {
        final data = jsonDecode(await file.readAsString()) as Map;
        url = data['url']?.toString() ?? '';
        key = data['key']?.toString() ?? '';
        if (url.isNotEmpty && key.isNotEmpty) return true;
      }
    } catch (_) {
      // Fallback to SharedPreferences below
    }

    // Fallback: SharedPreferences
    try {
      final p = await SharedPreferences.getInstance();
      url = p.getString('config_url') ?? '';
      key = p.getString('config_key') ?? '';
      return url.isNotEmpty && key.isNotEmpty;
    } catch (_) {
      return false;
    }
  }

  Future<void> save(String newUrl, String newKey) async {
    url = newUrl;
    key = newKey;

    // Durable file
    try {
      final dir = Directory('/data/data/com.cadux.cadux/files');
      await dir.create(recursive: true);
      final file = File('${dir.path}/cadux_config.json');
      await file.writeAsString(jsonEncode({'url': url, 'key': key}));
    } catch (_) {
      // Non-fatal
    }

    // SharedPreferences fallback
    try {
      final p = await SharedPreferences.getInstance();
      await p.setString('config_url', url);
      await p.setString('config_key', key);
    } catch (_) {
      // Non-fatal
    }
  }

  Future<void> clear() async {
    url = '';
    key = '';
    try {
      File('/data/data/com.cadux.cadux/files/cadux_config.json').deleteSync();
    } catch (_) {}
    try {
      final p = await SharedPreferences.getInstance();
      await p.remove('config_url');
      await p.remove('config_key');
    } catch (_) {}
  }

  /// Derive notification receiver URL from gateway URL.
  /// Gateway runs on 8642, notification receiver on 8643.
  String get notificationUrl => url.replaceFirst(':8642', ':8643');

  bool get isConfigured => url.isNotEmpty && key.isNotEmpty;
}
