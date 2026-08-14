class NotificationData {
  final String packageName;
  final String appName;
  final String? title;
  final String? text;
  final String? category;
  final DateTime postTime;
  final bool isOngoing;
  final bool isClearable;
  final String? groupKey;

  NotificationData({
    required this.packageName,
    required this.appName,
    this.title,
    this.text,
    this.category,
    required this.postTime,
    this.isOngoing = false,
    this.isClearable = true,
    this.groupKey,
  });

  factory NotificationData.fromJson(Map<String, dynamic> j) => NotificationData(
    packageName: j['packageName'] ?? '',
    appName: j['appName'] ?? '',
    title: j['title'],
    text: j['text'],
    category: j['category'],
    postTime: DateTime.fromMillisecondsSinceEpoch(j['postTime'] ?? 0),
    isOngoing: j['isOngoing'] == true,
    isClearable: j['isClearable'] != false,
    groupKey: j['groupKey'],
  );

  Map<String, dynamic> toJson() => {
    'packageName': packageName,
    'appName': appName,
    'title': title,
    'text': text,
    'category': category,
    'postTime': postTime.toIso8601String(),
    'isOngoing': isOngoing,
    'isClearable': isClearable,
    'groupKey': groupKey,
  };
}
