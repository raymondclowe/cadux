import 'package:flutter/material.dart';
import '../models/hermes_session.dart';

class SessionDrawer extends StatelessWidget {
  final List<HermesSession> sessions;
  final String activeSessionId;
  final String status;
  final bool isConnecting;
  final VoidCallback onReconnect;
  final VoidCallback onNewSession;
  final void Function(String id) onSelectSession;
  final void Function(String id) onDeleteSession;
  final VoidCallback onShowSettings;
  final VoidCallback onShowCaduxSettings;
  final VoidCallback onDisconnect;

  const SessionDrawer({
    super.key,
    required this.sessions,
    required this.activeSessionId,
    required this.status,
    required this.isConnecting,
    required this.onReconnect,
    required this.onNewSession,
    required this.onSelectSession,
    required this.onDeleteSession,
    required this.onShowSettings,
    required this.onShowCaduxSettings,
    required this.onDisconnect,
  });

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Drawer(
      child: ListView(
        padding: EdgeInsets.zero,
        children: [
          DrawerHeader(
            decoration: const BoxDecoration(color: Colors.indigo),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(Icons.forum, size: 40, color: Colors.white),
                const SizedBox(height: 8),
                const Text('Cadux',
                    style: TextStyle(
                        fontSize: 22,
                        fontWeight: FontWeight.bold,
                        color: Colors.white)),
                Text(status,
                    style: const TextStyle(fontSize: 12, color: Colors.white70)),
              ],
            ),
          ),
          // Sessions header
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
            child: Row(
              children: [
                const Text('Sessions',
                    style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14)),
                if (isConnecting)
                  const Padding(
                    padding: EdgeInsets.only(left: 8),
                    child: SizedBox(
                      width: 12,
                      height: 12,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    ),
                  ),
                const Spacer(),
                IconButton(
                  icon: const Icon(Icons.add, size: 20),
                  onPressed: onNewSession,
                  tooltip: 'New session',
                ),
              ],
            ),
          ),
          // Session tiles (max 15 to avoid huge lists)
          ...sessions.take(15).map((s) => ListTile(
            selected: s.id == activeSessionId,
            title: Text(s.displayTitle, style: const TextStyle(fontSize: 13)),
            subtitle: Text(
              '${s.messageCount} msgs${s.model.isNotEmpty ? ' — ${s.model}' : ''}',
              style: const TextStyle(fontSize: 11),
            ),
            trailing: IconButton(
              icon: const Icon(Icons.close, size: 16),
              onPressed: () => onDeleteSession(s.id),
            ),
            onTap: () => onSelectSession(s.id),
          )),
          const Divider(),
          ListTile(
            leading: const Icon(Icons.refresh),
            title: const Text('Reconnect'),
            onTap: onReconnect,
          ),
          ListTile(
            leading: const Icon(Icons.settings),
            title: const Text('Cadux Settings'),
            onTap: () {
              Navigator.pop(context);
              onShowCaduxSettings();
            },
          ),
          ListTile(
            leading: const Icon(Icons.info_outline),
            title: const Text('About'),
            onTap: () {
              Navigator.pop(context);
              showAboutDialog(
                context: context,
                applicationName: 'Cadux',
                applicationVersion: '0.5.0',
                applicationIcon: const Icon(Icons.forum, size: 48),
                children: const [
                  Text('A native Hermes Agent client.\n'
                      'github.com/raymondclowe/cadux')
                ],
              );
            },
          ),
          ListTile(
            leading: Icon(Icons.logout, color: cs.error),
            title: Text('Disconnect', style: TextStyle(color: cs.error)),
            onTap: () {
              Navigator.pop(context);
              onDisconnect();
            },
          ),
        ],
      ),
    );
  }
}
