import 'package:flutter_test/flutter_test.dart';
import 'package:geolocator/geolocator.dart';
import 'package:lakad/state/location_state.dart';

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

  group('accuracyLabel', () {
    test('rounds metres and says nothing for an unknown accuracy', () {
      expect(accuracyLabel(7.6), '±8 m');
      expect(accuracyLabel(0.4), '');
      expect(accuracyLabel(0), '');
      expect(accuracyLabel(double.nan), '');
    });
  });
}
