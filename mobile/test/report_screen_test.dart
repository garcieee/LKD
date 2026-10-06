// The report screen, whole, with the camera, GPS and compass faked (test_support.dart): how it fits small phones
// and large text, that Send stays in view, and the SOS hold's ends. Without a server the app's own calls get a
// 400 in tests, which is how "SOS not sent" is reached.
import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geolocator/geolocator.dart';
import 'package:lakad/features/report/report_screen.dart';
import 'package:lakad/features/report/sos_overlay.dart';

import 'test_support.dart';

void main() {
  setUpAll(loadRoboto);

  late Plugins plugins;
  setUp(() => plugins = Plugins());

  Widget screen() => const ReportScreen();

  // A fix in Makati: the shutter wakes up.
  Future<void> locate(WidgetTester tester) async {
    plugins.geo.emit(fixAt(14.5547, 121.0244));
    await tester.pump(const Duration(milliseconds: 100));
  }

  // The shutter pressed and let go: the shot springs into the corner, then the tag sheet opens.
  Future<void> shoot(WidgetTester tester) async {
    await tester.tap(find.byType(SosShutter));
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pump(const Duration(seconds: 2));
    await tester.pump(const Duration(milliseconds: 400));
  }

  // The shutter held down, for [seconds] of the clock the recording is timed by (the real one).
  Future<TestGesture> hold(WidgetTester tester, {double seconds = 1.1}) async {
    final finger = await tester.startGesture(tester.getCenter(find.byType(SosShutter)));
    await tester.pump(const Duration(milliseconds: 600)); // long enough to be an SOS
    await tester.runAsync(() => Future<void>.delayed(Duration(milliseconds: (seconds * 1000).round())));
    await tester.pump(const Duration(milliseconds: 100));
    return finger;
  }

  Future<void> settle(WidgetTester tester) async {
    for (var i = 0; i < 5; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }
  }

  testWidgets('the camera view fits, with the location chips and the camera error', (tester) async {
    await fitsEveryPhone(tester, screen, after: locate);
    for (final (serviceOn, permission) in [
      (false, LocationPermission.whileInUse),
      (true, LocationPermission.denied),
      (true, LocationPermission.deniedForever),
    ]) {
      plugins.geo.serviceOn = serviceOn;
      plugins.geo.permission = permission;
      await fitsEveryPhone(tester, screen);
    }
    plugins.geo.serviceOn = true;
    plugins.geo.permission = LocationPermission.whileInUse;
    plugins.camera.initError = CameraException('CameraAccessDenied', 'Camera access is denied.');
    await fitsEveryPhone(tester, screen);
    plugins.camera.initError = CameraException(
      'cameraNotReadable',
      'The camera is in use by another app, so it could not be opened.',
    );
    await fitsEveryPhone(tester, screen);
    await leave(tester);
  });

  testWidgets('the tag sheet fits with a category, a long note and a failed send', (tester) async {
    await fitsEveryPhone(
      tester,
      screen,
      after: (tester) async {
        await locate(tester);
        await shoot(tester);
        await tester.ensureVisible(find.text('Blocked or missing tactile paving')); // the form scrolls
        await tester.tap(find.text('Blocked or missing tactile paving'));
        await tester.enterText(find.byType(TextField), 'Deep, by the jeepney stop. ' * 8);
        await tester.pump();
        await tester.tap(find.text('Send report')); // the test's own 400 comes back as the error
        await settle(tester);
        expect(find.text('Server error 400.'), findsOneWidget);
      },
    );
    await leave(tester);
  });

  testWidgets('the SOS banner and guide fit while recording, and on the X', (tester) async {
    await fitsEveryPhone(
      tester,
      screen,
      after: (tester) async {
        await locate(tester);
        final finger = await hold(tester, seconds: 0);
        await tester.pump(const Duration(milliseconds: 100));
        await finger.moveBy(const Offset(0, -80)); // onto the X
        await tester.pump(const Duration(milliseconds: 100));
        await finger.up();
        await settle(tester);
      },
    );
    await leave(tester);
  });

  testWidgets('the SOS card fits a failed send, on the smallest phone at the largest text', (tester) async {
    tester.view.physicalSize = phones.first;
    tester.view.devicePixelRatio = 1;
    tester.platformDispatcher.textScaleFactorTestValue = 2;
    addTearDown(tester.view.reset);
    addTearDown(tester.platformDispatcher.clearAllTestValues);
    await tester.pumpWidget(MaterialApp(theme: testTheme(), home: screen()));
    await tester.pump(const Duration(milliseconds: 100));
    await locate(tester);
    final finger = await hold(tester);
    await finger.up();
    await settle(tester); // sent: the test's own 400 brings the retry card

    expect(find.text('SOS not sent'), findsOneWidget);
    expect(find.text('Try again'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await leave(tester);
  });

  testWidgets('Send stays in view under the form, on a short phone and with the keyboard up', (tester) async {
    addTearDown(tester.view.reset);
    for (final (phone, keyboard) in [(phones.first, 0.0), (phones.last, 0.0), (phones.last, 300.0)]) {
      tester.view.physicalSize = phone;
      tester.view.devicePixelRatio = 1;
      tester.view.padding = const FakeViewPadding(top: 24, bottom: 16); // the status bar, the gesture bar
      await tester.pumpWidget(const SizedBox());
      await tester.pumpWidget(MaterialApp(theme: testTheme(), home: screen()));
      await tester.pump(const Duration(milliseconds: 100));
      await locate(tester);
      await shoot(tester);
      tester.view.viewInsets = FakeViewPadding(bottom: keyboard);
      await tester.pump(const Duration(milliseconds: 400));

      final send = tester.getRect(find.widgetWithText(FilledButton, 'Send report'));
      expect(send.top, greaterThanOrEqualTo(0), reason: '$phone, keyboard $keyboard');
      expect(send.bottom, lessThanOrEqualTo(phone.height - keyboard), reason: '$phone, keyboard $keyboard');
    }
    await leave(tester);
  });

  group('SOS', () {
    testWidgets('the camera comes back when the upload outlasts a call', (tester) async {
      tester.view.physicalSize = phones.last;
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(theme: testTheme(), home: screen()));
      await tester.pump(const Duration(milliseconds: 100));
      await locate(tester);
      final finger = await hold(tester);

      // The phone rings mid-recording and the user is straight back, before the clip has gone up.
      for (final state in [
        AppLifecycleState.inactive,
        AppLifecycleState.hidden,
        AppLifecycleState.inactive,
        AppLifecycleState.resumed,
      ]) {
        tester.binding.handleAppLifecycleStateChanged(state);
      }
      await settle(tester); // the upload fails (the test's 400); the screen lets go of the camera it recorded with
      expect(find.text('SOS not sent'), findsOneWidget);
      await finger.up();
      await tester.tap(find.text('Discard the video'));
      await settle(tester);

      expect(plugins.camera.log, containsAllInOrder(['startVideo', 'stopVideo', 'dispose', 'create', 'initialize']));
      expect(tester.widget<SosShutter>(find.byType(SosShutter)).enabled, isTrue, reason: 'a live camera to shoot with');
      await leave(tester);
    });

    testWidgets('letting go on the X throws the clip away, and nothing is sent', (tester) async {
      tester.view.physicalSize = phones.last;
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(theme: testTheme(), home: screen()));
      await tester.pump(const Duration(milliseconds: 100));
      await locate(tester);
      final finger = await hold(tester);
      await finger.moveBy(const Offset(0, -80));
      await tester.pump(const Duration(milliseconds: 100));
      expect(find.text('CANCEL'), findsOneWidget);
      await finger.up();
      await settle(tester);

      expect(find.text('SOS cancelled. Nothing was sent.'), findsOneWidget);
      expect(find.text('Sending SOS'), findsNothing);
      expect(find.text('SOS not sent'), findsNothing);
      await leave(tester);
    });

    testWidgets('a hold under a second is dropped with a hint, and nothing is sent', (tester) async {
      tester.view.physicalSize = phones.last;
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(theme: testTheme(), home: screen()));
      await tester.pump(const Duration(milliseconds: 100));
      await locate(tester);
      final finger = await hold(tester, seconds: 0);
      await finger.up();
      await settle(tester);

      expect(find.text('Keep holding to send an SOS.'), findsOneWidget);
      expect(find.text('SOS not sent'), findsNothing);
      await leave(tester);
    });
  });
}
