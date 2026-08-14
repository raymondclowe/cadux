import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'services/config_service.dart';
import 'screens/home_screen.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);

  // Pre-load config so HomeScreen has initial values ready
  String? savedUrl, savedKey;
  final config = ConfigService();
  if (await config.load()) {
    savedUrl = config.url;
    savedKey = config.key;
  }

  runApp(CaduxApp(initialUrl: savedUrl, initialKey: savedKey));
}

class CaduxApp extends StatelessWidget {
  final String? initialUrl;
  final String? initialKey;
  const CaduxApp({super.key, this.initialUrl, this.initialKey});

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'Cadux',
    debugShowCheckedModeBanner: false,
    theme: ThemeData(
      colorSchemeSeed: Colors.indigo,
      brightness: Brightness.light,
      useMaterial3: true,
    ),
    darkTheme: ThemeData(
      colorSchemeSeed: Colors.indigo,
      brightness: Brightness.dark,
      useMaterial3: true,
    ),
    themeMode: ThemeMode.system,
    home: HomeScreen(initialUrl: initialUrl, initialKey: initialKey),
  );
}
