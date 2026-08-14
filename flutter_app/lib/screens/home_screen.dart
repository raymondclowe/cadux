import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:record/record.dart';
import '../models/chat_message.dart';
import '../services/api_service.dart';
import '../services/config_service.dart';
import '../services/notification_service.dart';
import '../widgets/chat_bubble.dart';
import '../widgets/session_drawer.dart';

class HomeScreen extends StatefulWidget {
  final String? initialUrl;
  final String? initialKey;
  const HomeScreen({super.key, this.initialUrl, this.initialKey});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> with WidgetsBindingObserver {
  late final ConfigService _config;
  late final ApiService _api;
  late final NotificationService _notifications;

  String _sessionId = '';
  final List<ChatMessage> _messages = [];
  final TextEditingController _input = TextEditingController();
  final ScrollController _scroll = ScrollController();
  bool _configured = false;
  String _status = 'Tap Settings or scan QR';
  bool _ttsEnabled = false;
  String _gpsMode = 'none';
  bool _notificationForwarding = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _config = ConfigService();
    _api = ApiService(config: _config);
    _notifications = NotificationService(config: _config);
    _initApp();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _input.dispose();
    _scroll.dispose();
    _api.dispose();
    _notifications.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && _configured) {
      // Auto-refresh sessions when returning to app
      _api.loadSessions(silent: true);
    }
  }

  Future<void> _initApp() async {
    // Pre-loaded config from deep link / prior session
    if (widget.initialUrl != null &&
        widget.initialKey != null &&
        widget.initialUrl!.isNotEmpty &&
        widget.initialKey!.isNotEmpty) {
      await _config.save(widget.initialUrl!, widget.initialKey!);
      _onConfigured();
    } else {
      final loaded = await _config.load();
      if (loaded) _onConfigured();
    }

    // Deep link from MethodChannel
    try {
      const channel = MethodChannel('cadux/deeplink');
      final link = await channel.invokeMethod<String>('getInitialDeepLink');
      if (link != null && link.isNotEmpty) _handleDeepLink(link);
      channel.setMethodCallHandler((call) {
        if (call.method == 'onDeepLink' && call.arguments is String) {
          _handleDeepLink(call.arguments as String);
        }
        return Future.value(null);
      });
    } catch (_) {}

    // Check URI base for Android debug builds
    _checkUriBase();
  }

  void _checkUriBase() {
    try {
      final uri = Uri.base;
      final p = uri.queryParameters;
      if (p['url'] != null && p['key'] != null) {
        _saveConfig(p['url']!, p['key']!);
      }
    } catch (_) {}
  }

  void _handleDeepLink(String link) {
    final uri = Uri.parse(link);
    final p = uri.queryParameters;
    if (p['url'] != null && p['key'] != null) {
      _saveConfig(p['url']!, p['key']!);
    }
  }

  void _saveConfig(String url, String key) {
    final decodedUrl = Uri.decodeFull(url);
    _config.save(decodedUrl, key).then((_) => _onConfigured());
  }

  void _onConfigured() {
    setState(() {
      _configured = true;
      _status = 'Connecting…';
    });
    _api.startKeepAlive();
    _api.loadSessions().then((ok) {
      if (ok && _api.sessions.value.isNotEmpty) {
        _selectSession(_api.sessions.value.first.id);
      }
    });

    // Listen to API status changes
    _api.status.addListener(_onStatusChanged);
  }

  void _onStatusChanged() {
    if (mounted) {
      setState(() => _status = _api.status.value);
    }
  }

  void _clearConfig() {
    _api.stopKeepAlive();
    _config.clear();
    setState(() {
      _configured = false;
      _sessionId = '';
      _messages.clear();
      _status = 'Tap Settings or scan QR';
    });
  }

  void _selectSession(String sid) {
    setState(() {
      _sessionId = sid;
      _messages.clear();
      _status = 'Loading messages…';
    });
    _api.loadMessages(sid).then((msgs) {
      if (!mounted) return;
      setState(() {
        _messages.addAll(msgs);
        _status = '${_api.sessions.value.length} session(s) — ${_messages.length} messages';
      });
      _scrollToBottom();
    }).catchError((e) {
      if (mounted) _showError('Failed to load messages');
    });
  }

  Future<void> _newSession() async {
    final sid = await _api.createSession();
    if (sid != null) {
      _selectSession(sid);
    } else {
      _showError(_api.lastError ?? 'Failed to create session');
    }
  }

  Future<void> _deleteSession(String id) async {
    await _api.deleteSession(id);
    if (_sessionId == id && _api.sessions.value.isNotEmpty) {
      _selectSession(_api.sessions.value.first.id);
    }
  }

  Future<void> _sendMessage(String text) async {
    if (text.isEmpty || _sessionId.isEmpty) return;
    final originalText = text;
    setState(() {
      _messages.add(ChatMessage(role: 'user', text: originalText));
      _messages.add(ChatMessage(role: 'assistant', text: '…'));
      _input.clear();
    });
    _scrollToBottom();

    if (text == '/forget') {
      setState(() {
        _messages.removeLast();
        _messages.clear();
      });
      return;
    }

    final response = await _api.sendMessage(
      _sessionId,
      originalText,
      ttsEnabled: _ttsEnabled,
      gpsMode: _gpsMode,
    );

    if (!mounted) return;
    setState(() {
      _messages.removeLast();
      if (response != null) {
        _messages.add(ChatMessage(role: 'assistant', text: response));
      } else {
        _messages.add(ChatMessage(
            role: 'assistant', text: 'Error: ${_api.lastError ?? "unknown"}'));
        _showError(_api.lastError ?? 'Message failed');
      }
    });
    _scrollToBottom();
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.animateTo(
          _scroll.position.maxScrollExtent,
          duration: const Duration(milliseconds: 200),
          curve: Curves.easeOut,
        );
      }
    });
  }

  void _showError(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        duration: const Duration(seconds: 4),
        action: SnackBarAction(
          label: 'Dismiss',
          onPressed: () =>
              ScaffoldMessenger.of(context).hideCurrentSnackBar(),
        ),
      ),
    );
  }

  Future<void> _startRecording() async {
    final recorder = AudioRecorder();
    final dir = Directory.systemTemp;
    final path = '${dir.path}/cadux_voice.m4a';
    try {
      if (await recorder.hasPermission()) {
        await recorder.start(
          const RecordConfig(encoder: AudioEncoder.aacLc),
          path: path,
        );
        setState(() => _status = 'Recording… (5s)');
        await Future.delayed(const Duration(seconds: 5));
        await recorder.stop();
        setState(() => _status = 'Voice captured');
        _sendMessage('[Voice note recorded]');
      }
    } catch (e) {
      setState(() => _status = 'Record error');
      _showError('Recording failed');
    }
  }

  // ── Settings Dialogs ──

  void _showConnectionSettings() {
    final urlCtrl = TextEditingController(text: _config.url);
    final keyCtrl = TextEditingController(text: _config.key);
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Connection'),
        content: SizedBox(
          width: 300,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: urlCtrl,
                decoration: const InputDecoration(
                  label: Text('API URL'),
                  hintText: 'http://192.168.0.70:8642',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 8),
              TextField(
                controller: keyCtrl,
                decoration: const InputDecoration(
                  label: Text('Secret Key'),
                  border: OutlineInputBorder(),
                ),
                obscureText: true,
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () {
              Navigator.pop(ctx);
              _saveConfig(urlCtrl.text.trim(), keyCtrl.text.trim());
            },
            child: const Text('Save'),
          ),
        ],
      ),
    );
  }

  void _showCaduxSettings() {
    bool notifTemp = _notificationForwarding;
    showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDlgState) => AlertDialog(
          title: const Text('Cadux Settings'),
          content: SizedBox(
            width: 300,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                DropdownButtonFormField(
                  value: _gpsMode,
                  decoration: const InputDecoration(
                    label: Text('GPS'),
                    border: OutlineInputBorder(),
                  ),
                  items: const [
                    DropdownMenuItem(value: 'none', child: Text('None')),
                    DropdownMenuItem(
                        value: 'general', child: Text('General (~city)')),
                    DropdownMenuItem(
                        value: 'precise', child: Text('Precise')),
                  ],
                  onChanged: (v) => setDlgState(() => _gpsMode = v as String),
                ),
                const SizedBox(height: 8),
                SwitchListTile(
                  title: const Text('TTS'),
                  value: _ttsEnabled,
                  onChanged: (v) => setDlgState(() => _ttsEnabled = v),
                ),
                const Divider(),
                SwitchListTile(
                  title: const Text('Notification Forwarding'),
                  subtitle: const Text(
                    'Forward Android notifications to Hermes for triage',
                  ),
                  value: notifTemp,
                  onChanged: (v) async {
                    if (v) {
                      final hasPerm =
                          await _notifications.checkPermission();
                      if (!hasPerm) {
                        setDlgState(() => notifTemp = false);
                        _showError(
                            'Enable Notification Listener in Android Settings');
                        await _notifications.openSettings();
                        return;
                      }
                    }
                    setDlgState(() => notifTemp = v);
                  },
                ),
              ],
            ),
          ),
          actions: [
            FilledButton(
              onPressed: () {
                Navigator.pop(ctx);
                setState(() => _notificationForwarding = notifTemp);
                if (_notificationForwarding) {
                  _notifications.start();
                } else {
                  _notifications.stop();
                }
              },
              child: const Text('Save'),
            ),
          ],
        ),
      ),
    );
  }

  // ── Build ──

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final isConnecting = _api.isConnecting.value;
    return Scaffold(
      appBar: AppBar(
        title: Text('Cadux',
            style:
                TextStyle(fontWeight: FontWeight.bold, color: cs.onSurface)),
        leading: Builder(
          builder: (ctx) => IconButton(
            icon: const Icon(Icons.menu),
            onPressed: () => Scaffold.of(ctx).openDrawer(),
          ),
        ),
        actions: [
          Container(
            width: 10,
            height: 10,
            decoration: BoxDecoration(
              color: isConnecting
                  ? Colors.amber
                  : (_configured ? Colors.green : Colors.grey),
              shape: BoxShape.circle,
            ),
          ),
          const SizedBox(width: 8),
          IconButton(
            icon: const Icon(Icons.settings),
            onPressed: _showConnectionSettings,
          ),
        ],
      ),
      drawer: SessionDrawer(
        sessions: _api.sessions.value,
        activeSessionId: _sessionId,
        status: _status,
        isConnecting: isConnecting,
        onReconnect: () => _api.loadSessions(),
        onNewSession: _newSession,
        onSelectSession: _selectSession,
        onDeleteSession: _deleteSession,
        onShowSettings: _showConnectionSettings,
        onShowCaduxSettings: _showCaduxSettings,
        onDisconnect: _clearConfig,
      ),
      body: !_configured ? _buildWelcome() : _buildChat(cs),
    );
  }

  Widget _buildWelcome() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Icon(Icons.forum, size: 64, color: Colors.indigo),
          const SizedBox(height: 16),
          const Text('Cadux',
              style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold)),
          Text(_status, style: TextStyle(color: Colors.grey[600])),
          const SizedBox(height: 24),
          FilledButton.icon(
            icon: const Icon(Icons.settings),
            label: const Text('Setup'),
            onPressed: _showConnectionSettings,
          ),
        ],
      ),
    );
  }

  Widget _buildChat(ColorScheme cs) {
    return Column(
      children: [
        // Active session header
        Container(
          width: double.infinity,
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
          color: cs.surfaceContainerLow,
          child: Text(
            _api.sessions.value
                    .where((s) => s.id == _sessionId)
                    .firstOrNull
                    ?.displayTitle ??
                _sessionId,
            style: TextStyle(fontSize: 11, color: cs.onSurfaceVariant),
          ),
        ),
        // Message list
        Expanded(
          child: _messages.isEmpty
              ? Center(
                  child: Text(
                    _api.isConnecting.value
                        ? 'Connecting…'
                        : 'No messages — type to start',
                    style: TextStyle(color: cs.onSurfaceVariant),
                  ),
                )
              : ListView.builder(
                  controller: _scroll,
                  itemCount: _messages.length,
                  itemBuilder: (_, i) => ChatBubble(message: _messages[i]),
                ),
        ),
        const Divider(height: 1),
        // Input bar
        Row(
          children: [
            IconButton(
              icon: Icon(_ttsEnabled ? Icons.volume_up : Icons.volume_off,
                  size: 20),
              onPressed: () => setState(() => _ttsEnabled = !_ttsEnabled),
              tooltip: 'TTS',
            ),
            IconButton(
              icon: const Icon(Icons.mic, size: 20),
              onPressed: _startRecording,
              tooltip: 'Record',
            ),
            Expanded(
              child: TextField(
                controller: _input,
                decoration: const InputDecoration(
                  hintText: 'Message…',
                  border: InputBorder.none,
                ),
                maxLines: 4,
                minLines: 1,
                onSubmitted: (v) => _sendMessage(v),
              ),
            ),
            IconButton(
              icon: const Icon(Icons.send),
              onPressed: () => _sendMessage(_input.text),
            ),
          ],
        ),
        SizedBox(height: MediaQuery.of(context).padding.bottom),
      ],
    );
  }
}
