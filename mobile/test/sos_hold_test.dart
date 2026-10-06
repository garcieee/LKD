import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lakad/features/report/sos_hold.dart';
import 'package:lakad/features/report/sos_overlay.dart';

void main() {
  group('the hold rules', () {
    test('cancelProgress: 0 at the button, 1 on the X, never past either end, and sliding down does not count', () {
      expect(cancelProgress(0), 0);
      expect(cancelProgress(-sosCancelDistance / 2), closeTo(0.5, 1e-9));
      expect(cancelProgress(-sosCancelDistance), 1);
      expect(cancelProgress(-500), 1);
      expect(cancelProgress(80), 0);
    });

    test('inCancelZone: only on or past the X', () {
      expect(inCancelZone(-sosCancelDistance + 1), isFalse);
      expect(inCancelZone(-sosCancelDistance), isTrue);
      expect(inCancelZone(-sosCancelDistance - 40), isTrue);
      expect(inCancelZone(0), isFalse);
    });

    test('sosOutcome: the X cancels whatever was recorded, a clip under a second is dropped, the rest is sent', () {
      const long = Duration(seconds: 5);
      expect(sosOutcome(recorded: long, cancelZone: true), SosOutcome.cancel);
      expect(sosOutcome(recorded: Duration.zero, cancelZone: true), SosOutcome.cancel);
      expect(sosOutcome(recorded: sosMinRecording - const Duration(milliseconds: 1), cancelZone: false), SosOutcome.tooShort);
      expect(sosOutcome(recorded: sosMinRecording, cancelZone: false), SosOutcome.send);
      expect(sosOutcome(recorded: sosMaxRecording, cancelZone: false), SosOutcome.send);
    });

    test('vignetteStrength creeps in (slow at first), reaches full red, and calms as the finger nears the X', () {
      expect(vignetteStrength(0, 0), 0);
      expect(vignetteStrength(0.25, 0), lessThan(0.25), reason: 'eases in: a quarter of the time, well under a quarter of the red');
      expect(vignetteStrength(0.5, 0), closeTo(0.25, 1e-9));
      expect(vignetteStrength(1, 0), 1);
      expect(vignetteStrength(1, 0.5), lessThan(vignetteStrength(1, 0)));
      expect(vignetteStrength(1, 1), closeTo(0.2, 1e-9), reason: 'on the X most of it is gone');
      expect(vignetteStrength(2, 0), 1, reason: 'never past full');
      expect(vignetteStrength(-1, 0), 0);
    });

    test('clock reads minutes and zero-padded seconds', () {
      expect(clock(Duration.zero), '0:00');
      expect(clock(const Duration(seconds: 7)), '0:07');
      expect(clock(const Duration(seconds: 65)), '1:05');
      expect(clock(sosMaxRecording), '0:30');
    });
  });

  group('SosShutter', () {
    // What the shutter told its owner, in order.
    late List<String> calls;

    Widget shutter({bool enabled = true, bool armed = false, bool cancelling = false}) => MaterialApp(
      home: Scaffold(
        body: Center(
          child: SosShutter(
            enabled: enabled,
            busy: false,
            armed: armed,
            cancelling: cancelling,
            onTap: () => calls.add('tap'),
            onSosStart: () => calls.add('start'),
            onSosMove: (dy) => calls.add('move ${dy.round()}'),
            onSosEnd: (dy) => calls.add('end ${dy.round()}'),
            onSosAbort: () => calls.add('abort'),
          ),
        ),
      ),
    );

    setUp(() => calls = []);

    testWidgets('a quick tap is a photo', (tester) async {
      await tester.pumpWidget(shutter());
      await tester.tap(find.byType(SosShutter));
      await tester.pump(sosHoldDelay * 2); // and the hold timer does not fire later
      expect(calls, ['tap']);
    });

    testWidgets('held past the delay it is an SOS, and lifting the finger ends it', (tester) async {
      await tester.pumpWidget(shutter());
      final finger = await tester.startGesture(tester.getCenter(find.byType(SosShutter)));
      await tester.pump(sosHoldDelay - const Duration(milliseconds: 50));
      expect(calls, isEmpty, reason: 'not yet: still might be a tap');
      await tester.pump(const Duration(milliseconds: 100));
      expect(calls, ['start']);
      await finger.up();
      expect(calls, ['start', 'end 0']);
    });

    testWidgets('sliding up reports how far, and lifting on the X reports it for the cancel check', (tester) async {
      await tester.pumpWidget(shutter());
      final finger = await tester.startGesture(tester.getCenter(find.byType(SosShutter)));
      await tester.pump(sosHoldDelay + const Duration(milliseconds: 50));
      await finger.moveBy(const Offset(0, -40)); // short of the X
      await finger.moveBy(const Offset(0, -40)); // -80 in all, past the near edge of the X at -72
      await finger.up();
      expect(calls, ['start', 'move -40', 'move -80', 'end -80']);
      expect(inCancelZone(-40), isFalse);
      expect(inCancelZone(-80), isTrue);
    });

    testWidgets('a touch the system takes away mid-SOS is reported, so the recording is never left running', (tester) async {
      await tester.pumpWidget(shutter());
      final finger = await tester.startGesture(tester.getCenter(find.byType(SosShutter)));
      await tester.pump(sosHoldDelay + const Duration(milliseconds: 50));
      await finger.cancel();
      expect(calls, ['start', 'abort']);
    });

    testWidgets('a drag that starts before the hold delay is neither a photo nor an SOS', (tester) async {
      await tester.pumpWidget(shutter());
      final finger = await tester.startGesture(tester.getCenter(find.byType(SosShutter)));
      await finger.moveBy(const Offset(0, -40)); // past the touch slop
      await tester.pump(sosHoldDelay * 2);
      await finger.up();
      expect(calls, isEmpty);
    });

    testWidgets('a disabled shutter ignores presses (no GPS fix yet)', (tester) async {
      await tester.pumpWidget(shutter(enabled: false));
      final finger = await tester.startGesture(tester.getCenter(find.byType(SosShutter)));
      await tester.pump(sosHoldDelay * 2);
      await finger.up();
      await tester.tap(find.byType(SosShutter));
      expect(calls, isEmpty);
    });

    testWidgets('an SOS under way still hears the end when the owner disables the shutter (it does, once recording)', (tester) async {
      await tester.pumpWidget(shutter());
      final finger = await tester.startGesture(tester.getCenter(find.byType(SosShutter)));
      await tester.pump(sosHoldDelay + const Duration(milliseconds: 50));
      await tester.pumpWidget(shutter(enabled: false, armed: true));
      await finger.up();
      expect(calls, ['start', 'end 0']);
    });

    testWidgets('a second finger does not start or end anything', (tester) async {
      await tester.pumpWidget(shutter());
      final first = await tester.startGesture(tester.getCenter(find.byType(SosShutter)));
      await tester.pump(sosHoldDelay + const Duration(milliseconds: 50));
      final second = await tester.startGesture(tester.getCenter(find.byType(SosShutter)) + const Offset(10, 0));
      await second.up();
      expect(calls, ['start']);
      await first.up();
      expect(calls, ['start', 'end 0']);
    });

    testWidgets('says what a tap and a hold do, for a screen reader', (tester) async {
      await tester.pumpWidget(shutter());
      expect(find.bySemanticsLabel(RegExp('Press and hold to record an SOS')), findsOneWidget);
    });
  });

  group('the overlay', () {
    testWidgets('the guide tells the user to slide up, then to release once on the X', (tester) async {
      final slide = ValueNotifier<double>(0);
      addTearDown(slide.dispose);
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Center(
              child: SizedBox(width: 240, height: sosGuideHeight, child: SosGuide(cancel: slide, reduceMotion: true)),
            ),
          ),
        ),
      );
      expect(find.text('Slide up to cancel'), findsOneWidget);
      expect(find.byIcon(Icons.close), findsOneWidget, reason: 'the X to slide to');
      expect(find.byIcon(Icons.keyboard_arrow_up_rounded), findsNWidgets(3), reason: 'the arrows along the button');
      slide.value = 1;
      await tester.pump();
      expect(find.text('Release to cancel'), findsOneWidget);
    });

    testWidgets('the banner says SOS mode and the time, and flips to cancel on the X', (tester) async {
      final slide = ValueNotifier<double>(0);
      final recorded = ValueNotifier<Duration>(const Duration(seconds: 7));
      addTearDown(slide.dispose);
      addTearDown(recorded.dispose);
      await tester.pumpWidget(MaterialApp(home: Scaffold(body: Center(child: SosBanner(cancel: slide, recorded: recorded)))));
      expect(find.text('SOS MODE'), findsOneWidget);
      expect(find.text('0:07'), findsOneWidget);
      expect(find.text('Release to send it to the city'), findsOneWidget);
      recorded.value = const Duration(seconds: 8);
      slide.value = 1;
      await tester.pump();
      expect(find.text('CANCEL'), findsOneWidget);
      expect(find.text('0:08'), findsOneWidget);
      expect(find.text('Release to throw the video away'), findsOneWidget);
    });

    testWidgets('the vignette paints nothing at first, then red, and takes it back on the X', (tester) async {
      final ramp = AnimationController(vsync: tester, duration: sosVignetteRamp); // as the screen's is
      final slide = ValueNotifier<double>(0);
      addTearDown(ramp.dispose);
      addTearDown(slide.dispose);
      await tester.pumpWidget(MaterialApp(home: Scaffold(body: SosVignette(ramp: ramp, cancel: slide))));
      final painted = find.descendant(of: find.byType(SosVignette), matching: find.byType(CustomPaint));
      RenderObject paint() => tester.renderObject(painted.last);

      expect(paint(), isNot(paints..rect()));
      ramp.value = 1;
      await tester.pump();
      expect(paint(), paints..rect());
      slide.value = 1;
      ramp.value = 0;
      await tester.pump();
      expect(paint(), isNot(paints..rect()));
    });
  });
}
