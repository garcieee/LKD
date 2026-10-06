// Where the user wants to go, and the walking routes there in each mode. The map draws the pin and the
// chosen mode's line. The start is the user's live location, given when the destination is picked.
// ponytail: the routes are worked out once from that start and not redone as the user walks. Upgrade:
// re-plan when the location drifts a block from the line.
import 'package:flutter/foundation.dart';

import '../api/api_client.dart';

typedef LatLng = ({double lat, double lng});
typedef RouteFn = Future<WalkRoute> Function(LatLng from, LatLng to, String mode);

class TripState extends ChangeNotifier {
  TripState(this._fetch);

  final RouteFn _fetch;

  Place? destination;
  String mode = 'walkable'; // the mode being shown: a key of routeModes
  final routes = <String, WalkRoute>{}; // filled as each mode's answer arrives
  final errors = <String, String>{}; // why a mode has no route, fit to show
  bool loading = false;
  bool planned = false; // routes for this destination have been asked for
  int _round = 0; // bumped per destination; answers from an older one are dropped

  WalkRoute? get route => routes[mode];
  String? get error => errors[mode];

  /// Picks (or, with null, clears) the destination. With [from] the three routes are fetched at once;
  /// without it (no GPS fix yet) they wait for [plan].
  void setDestination(Place? place, {LatLng? from}) {
    destination = place;
    _round++;
    routes.clear();
    errors.clear();
    loading = false;
    planned = false;
    notifyListeners();
    if (place != null && from != null) plan(from);
  }

  void clear() => setDestination(null);

  void setMode(String next) {
    if (!routeModes.containsKey(next) || next == mode) return;
    mode = next;
    notifyListeners();
  }

  /// Fetches every mode in parallel from [from] to the destination. Each answer shows as it lands, so the
  /// quickest mode draws first, and one mode failing leaves the others alone.
  Future<void> plan(LatLng from) async {
    final place = destination;
    if (place == null || planned) return;
    planned = true;
    loading = true;
    final round = _round;
    notifyListeners();
    await Future.wait([
      for (final m in routeModes.keys)
        () async {
          try {
            final r = await _fetch(from, (lat: place.lat, lng: place.lng), m);
            if (round == _round) routes[m] = r;
          } on ApiException catch (e) {
            if (round == _round) errors[m] = e.message;
          }
          if (round == _round) notifyListeners();
        }(),
    ]);
    if (round != _round) return;
    loading = false;
    notifyListeners();
  }
}
