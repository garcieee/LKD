import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lakad/features/navigate/compass_chip.dart';
import 'package:lakad/theme.dart';

Future<void> show(
  WidgetTester tester, {
  required ValueNotifier<double> bearing,
  required ValueNotifier<bool> following,
}) => tester.pumpWidget(
  MaterialApp(
    home: Scaffold(
      body: Center(
        child: CompassChip(bearing: bearing, following: following),
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

  testWidgets('following shows in the colours and the label', (tester) async {
    final bearing = ValueNotifier(0.0), following = ValueNotifier(false);
    await show(tester, bearing: bearing, following: following);
    Color? fill() => tester
        .widget<Material>(find.descendant(of: find.byType(CompassChip), matching: find.byType(Material)).first)
        .color;
    expect(fill(), Colors.white);
    expect(find.bySemanticsLabel(RegExp('Following your heading')), findsNothing);

    following.value = true;
    await tester.pump();
    expect(fill(), navy);
    expect(find.bySemanticsLabel(RegExp('Following your heading')), findsOneWidget);
  });

  testWidgets('it is a display, not a button, and still tall enough to read', (tester) async {
    await show(tester, bearing: ValueNotifier(0.0), following: ValueNotifier(true));
    expect(find.descendant(of: find.byType(CompassChip), matching: find.byType(InkWell)), findsNothing);
    expect(tester.getSize(find.byType(CompassChip)).height, greaterThanOrEqualTo(48));
  });
}
