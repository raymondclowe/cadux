import 'package:flutter_test/flutter_test.dart';
import 'package:cadux/main.dart';

void main() {
  testWidgets('App renders Cadux title', (WidgetTester tester) async {
    await tester.pumpWidget(const CaduxApp());
    expect(find.text('Cadux'), findsWidgets);
  });
}
