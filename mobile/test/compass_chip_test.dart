import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lakad/features/navigate/compass_chip.dart';
import 'package:lakad/theme.dart';

Future<void> show(
  WidgetTester tester, {
  required ValueNotifier<double> bearing,
  required ValueNotifier<bool> following,
  VoidCallback? onTap,
}) => tester.pumpWidget(
  MaterialApp(
    home: Scaffold(
      body: Center(
        child: CompassChip(bearing: bearing, following: following, onTap: onTap ?? () {}),
      ),
    ),
  ),
);

/// sin of the angle the arrow is turned by: -1 is a quarter turn anticlockwise, 1 a quarter turn clockwise.
double arrowSin(WidgetTester tester) {
  final t = tester.widget<Transform>(
    find.ancestor(of: find.byIcon(Icons.north), matching: find.byType(Transform)).first,
  );
  return t.transform.entry(1, 0);
}

void main() {
  testWidgets('it names the direction at the top of the map, and follows the bearing as it changes', (tester) async {
    final bearing = ValueNotifier(0.0), following = ValueNotifier(false);
    await show(tester, bearing: bearing, following: following);
    expect(find.text('N'), findsOneWidget);
    bearing.value = 45;
    await tester.pump();
    expect(find.text('NE'), findsOneWidget);
    bearing.value = 270;
    await tester.pump();
    expect(find.text('W'), findsOneWidget);
    bearing.value = 359;
    await tester.pump();
    expect(find.text('N'), findsOneWidget, reason: 'just short of a full turn is still north');
  });

  testWidgets('the arrow keeps pointing at north: it turns against the map', (tester) async {
    final bearing = ValueNotifier(0.0), following = ValueNotifier(false);
    await show(tester, bearing: bearing, following: following);
    expect(arrowSin(tester), closeTo(0, 1e-9), reason: 'north-up: the arrow points up');
    bearing.value = 90; // the map turned a quarter clockwise (facing east): north is now to the left
    await tester.pump();
    expect(arrowSin(tester), closeTo(-1, 1e-9));
    bearing.value = 270; // facing west: north is to the right
    await tester.pump();
    expect(arrowSin(tester), closeTo(1, 1e-9));
  });

  testWidgets('following shows in the colours and the label, and a tap calls back', (tester) async {
    final bearing = ValueNotifier(0.0), following = ValueNotifier(false);
    var taps = 0;
    await show(tester, bearing: bearing, following: following, onTap: () => taps++);
    Color? fill() => tester
        .widget<Material>(find.descendant(of: find.byType(CompassChip), matching: find.byType(Material)).first)
        .color;
    expect(fill(), Colors.white);
    expect(find.bySemanticsLabel(RegExp('Tap to follow your heading')), findsOneWidget);

    following.value = true;
    await tester.pump();
    expect(fill(), navy);
    expect(find.bySemanticsLabel(RegExp('Following your heading')), findsOneWidget);

    await tester.tap(find.byType(CompassChip));
    expect(taps, 1);
  });
}
