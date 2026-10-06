import 'package:flutter_test/flutter_test.dart';
import 'package:geolocator/geolocator.dart';
import 'package:lakad/state/location_state.dart';

import 'test_support.dart';

void main() {
  group('gpsStatus', () {
    test('the phone Location switch wins over any permission', () {
      expect(gpsStatus(serviceOn: false, permission: LocationPermission.whileInUse), Gps.off);
    });

    test('whileInUse and always are ok; denied and deniedForever differ', () {
      Gps s(LocationPermission p) => gpsStatus(serviceOn: true, permission: p);
      expect(s(LocationPermission.whileInUse), Gps.ok);
      expect(s(LocationPermission.always), Gps.ok);
      expect(s(LocationPermission.denied), Gps.denied);
      expect(s(LocationPermission.unableToDetermine), Gps.denied);
      expect(s(LocationPermission.deniedForever), Gps.blocked);
    });
  });

  group('start', () {
    // The app resuming beneath the permission prompt calls start() again while the first call still waits.
    test('a second call joins the first: one stream, nothing left running after dispose', () async {
      final geo = FakeGeolocator();
      GeolocatorPlatform.instance = geo;
      final location = LocationState();
      await Future.wait([location.start(), location.start()]);
      expect(location.status, Gps.ok);
      expect(geo.listening, 1);
      location.dispose();
      expect(geo.listening, 0);
    });

    test('and does not ask for the permission twice', () async {
      final geo = FakeGeolocator()
        ..permission = LocationPermission.denied
        ..promptTime = const Duration(milliseconds: 20);
      GeolocatorPlatform.instance = geo;
      final location = LocationState();
      await Future.wait([location.start(), location.start()]);
      expect(geo.prompts, 1);
      expect(location.status, Gps.denied);
      location.dispose();
    });

    test('a call after the first is done starts again, so a return from Settings picks up the new answer', () async {
      final geo = FakeGeolocator()..permission = LocationPermission.deniedForever;
      GeolocatorPlatform.instance = geo;
      final location = LocationState();
      await location.start();
      expect(location.status, Gps.blocked);
      geo.permission = LocationPermission.whileInUse;
      await location.start();
      expect(location.status, Gps.ok);
      expect(geo.listening, 1);
      location.dispose();
    });
  });

  group('accuracyLabel', () {
    test('rounds metres and says nothing for an unknown accuracy', () {
      expect(accuracyLabel(7.6), '±8 m');
      expect(accuracyLabel(0.4), '');
      expect(accuracyLabel(0), '');
      expect(accuracyLabel(double.nan), '');
    });
  });
}
