import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lakad/api/api_client.dart';
import 'package:lakad/features/report/category_picker.dart';
import 'package:lakad/layers/reports_layer.dart';
import 'package:lakad/map/pin_chip.dart';

// A `NAME: Record<...> = { key: "value", ... }` table from the dashboard, which mirrors these.
Map<String, String> dashboardTable(String file, String name) {
  final source = File('../dashboard/src/$file').readAsStringSync(); // flutter test runs in mobile/
  final body = RegExp('$name[^{]*\\{([^}]*)\\}').firstMatch(source)![1]!;
  return {for (final m in RegExp(r'(\w+): "([^"]*)"').allMatches(body)) m[1]!: m[2]!};
}

void main() {
  testWidgets('CategoryPicker: none to start, one at a time, and a second tap never clears it', (tester) async {
    String? value;
    await tester.pumpWidget(
      MaterialApp(
        home: Material(
          child: StatefulBuilder(
            builder: (_, setState) => CategoryPicker(value: value, onChanged: (c) => setState(() => value = c)),
          ),
        ),
      ),
    );
    List<String> selected() => [
      for (final chip in tester.widgetList<ChoiceChip>(find.byType(ChoiceChip)))
        if (chip.selected) (chip.label as Text).data!,
    ];

    expect(find.byType(ChoiceChip), findsNWidgets(categoryLabels.length));
    expect(selected(), isEmpty); // so Send stays off until the user picks (report_screen.dart)
    for (final label in ['Pothole', 'Open manhole', 'Open manhole']) {
      await tester.tap(find.text(label));
      await tester.pump();
    }
    expect(value, 'open_manhole');
    expect(selected(), ['Open manhole']);
  });

  testWidgets('CategoryPicker: every label shows in full on a small phone with large text', (tester) async {
    tester.view.physicalSize = const Size(320, 640);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      MediaQuery(
        data: const MediaQueryData(size: Size(320, 640), textScaler: TextScaler.linear(1.5)),
        child: MaterialApp(
          home: Material(child: SingleChildScrollView(child: CategoryPicker(value: null, onChanged: (_) {}))),
        ),
      ),
    );
    for (final label in categoryLabels.values) {
      final text = tester.renderObject<RenderParagraph>(find.text(label));
      // Not cut at the bottom, and not running past the chip's right edge (a faded one-line label does that).
      expect(text.didExceedMaxLines || text.textSize.width > text.size.width, isFalse, reason: label);
    }
  });

  test('ago: just under and exactly on each boundary', () {
    final now = DateTime.utc(2026, 10, 6, 7);
    String at(Duration age) => ago(now.subtract(age), now);
    expect(at(const Duration(seconds: 59)), 'just now');
    expect(at(const Duration(minutes: 1)), '1 min ago');
    expect(at(const Duration(minutes: 59, seconds: 59)), '59 min ago');
    expect(at(const Duration(hours: 1)), '1 h ago');
    expect(at(const Duration(hours: 23, minutes: 59)), '23 h ago');
    expect(at(const Duration(days: 1)), '1 d ago');
    expect(at(const Duration(minutes: -5)), 'just now'); // a server clock ahead of the phone
  });

  group('matches the dashboard', () {
    test('category and status labels', () {
      // The dashboard also labels the SOS, which the app files from the shutter and never lists in its picker.
      expect({...categoryLabels, sosCategory: sosLabel}, dashboardTable('features/queue/tickets.ts', 'CATEGORY_LABEL'));
      // The dashboard also has "rejected", a ticket judged not real. The server never sends those to the app.
      expect({...statusLabels, 'rejected': 'Rejected'}, dashboardTable('features/queue/tickets.ts', 'STATUS_LABEL'));
    });

    test('pin colours, with none for fixed reports (not drawn)', () {
      final hex = dashboardTable('layers/reports.ts', 'STATUS_COLOR');
      expect(statusColors.keys, ['open', 'verified', 'assigned']);
      for (final MapEntry(key: status, value: color) in statusColors.entries) {
        expect(color, Color(0xFF000000 | int.parse(hex[status]!.substring(1), radix: 16)), reason: status);
      }
    });
  });
}
