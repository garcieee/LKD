// Where the user is: GPS permission, the live fix, and what to tell them when there is none.
// ponytail: features/report/report_screen.dart keeps its own copy of this flow (its AR camera needs
// the fix tied to its own lifecycle). Upgrade: have it read this class instead.
import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:geolocator/geolocator.dart';

enum Gps { starting, ok, off, denied, blocked }

/// What the permission answer means for the app. [serviceOn] is the phone's Location switch.
Gps gpsStatus({required bool serviceOn, required LocationPermission permission}) {
  if (!serviceOn) return Gps.off;
  return switch (permission) {
    LocationPermission.whileInUse || LocationPermission.always => Gps.ok,
    LocationPermission.deniedForever => Gps.blocked,
    _ => Gps.denied,
  };
}

/// "±8 m". Metres are rounded, and an unknown accuracy (0, under half a metre, or NaN) says nothing.
String accuracyLabel(double metres) => metres.isFinite && metres.round() > 0 ? '±${metres.round()} m' : '';

/// Past this the fix is a rough guess (a few city blocks of doubt), so the chip warns.
const weakAccuracyM = 50.0;

class LocationState extends ChangeNotifier {
  Gps status = Gps.starting;
  Position? fix;
  StreamSubscription<Position>? _fixes;
  Future<void>? _starting;

  /// Asks for permission if needed, then follows the GPS. Safe to call again (after the user
  /// comes back from Settings): it restarts the stream. A call while one is still under way (the app
  /// resuming beneath the permission prompt) joins it: a second would open a stream nothing cancels.
  Future<void> start() => _starting ??= _start().whenComplete(() => _starting = null);

  Future<void> _start() async {
    await _fixes?.cancel();
    _fixes = null;
    final serviceOn = await Geolocator.isLocationServiceEnabled();
    var permission = await Geolocator.checkPermission();
    if (serviceOn && permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }
    status = gpsStatus(serviceOn: serviceOn, permission: permission);
    if (status != Gps.ok) fix = null;
    notifyListeners();
    if (status != Gps.ok) return;
    _fixes = Geolocator.getPositionStream(
      locationSettings: AndroidSettings(
        accuracy: LocationAccuracy.best,
        intervalDuration: const Duration(seconds: 1), // the default is 5 s
      ),
    ).listen(
      (p) {
        fix = p;
        notifyListeners();
      },
      onError: (Object e) {
        fix = null;
        status = e is LocationServiceDisabledException ? Gps.off : Gps.denied;
        notifyListeners();
      },
    );
  }

  @override
  void dispose() {
    _fixes?.cancel();
    super.dispose();
  }
}
