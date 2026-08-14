class HermesSession {
  final String id;
  final String title;
  final String model;
  final int messageCount;
  final double cost;
  String? preview;

  HermesSession({
    required this.id,
    this.title = '',
    this.model = '',
    this.messageCount = 0,
    this.cost = 0,
    this.preview,
  });

  factory HermesSession.fromJson(Map<String, dynamic> j) => HermesSession(
    id: (j['id'] ?? '').toString(),
    title: (j['title'] ?? '').toString(),
    model: (j['model'] ?? '').toString(),
    messageCount: (j['message_count'] ?? 0) as int,
    cost: ((j['estimated_cost_usd'] ?? 0) as num).toDouble(),
    preview: j['preview']?.toString(),
  );

  String get displayTitle =>
      title.isNotEmpty ? title : id.length > 12 ? '${id.substring(0, 12)}…' : id;
}
