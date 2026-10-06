// Where the user wants to go, the walking routes there in each mode, and the commute options (walk, ride, walk).
// The map draws the pin and the chosen route's line. The start is the user's live location, given when the destination is picked.
// ponytail: the routes are worked out once from that start and not redone as the user walks. Upgrade:
// re-plan when the location drifts a block from the line.
import 'package:flutter/foundation.dart';

import '../api/api_client.dart';

typedef LatLng = ({double lat, double lng});
typedef RouteFn = Future<WalkRoute> Function(LatLng from, LatLng to, String mode);
typedef CommuteFn = Future<List<CommuteOption>> Function(LatLng from, LatLng to);

/// What the card shows: ways to commute, or the walking routes.
const tripKinds = {'commute', 'walk'};

class TripState extends ChangeNotifier {
  TripState(this._fetch, [this._fetchCommute]) : kind = _fetchCommute == null ? 'walk' : 'commute';

  final RouteFn _fetch;
  final CommuteFn? _fetchCommute; // null: no commute options (walking only)

  Place? destination;
  String mode = 'walkable'; // the mode being shown: a key of routeModes
  final routes = <String, WalkRoute>{}; // filled as each mode's answer arrives
  final errors = <String, String>{}; // why a mode has no route, fit to show
  String kind; // a member of tripKinds: commute first when there are commute options to show
  List<CommuteOption> commute = const []; // quickest first
  String? commuteError; // why there are no commute options, fit to show
  int selected = 0; // index into commute: the one drawn on the map
  bool loading = false;
  bool planned = false; // routes for this destination have been asked for
  int _round = 0; // bumped per destination; answers from an older one are dropped

  WalkRoute? get route => routes[mode];
  String? get error => errors[mode];
  bool get hasCommute => _fetchCommute != null;
  CommuteOption? get option => selected < commute.length ? commute[selected] : null;

  /// Picks (or, with null, clears) the destination. With [from] the three routes are fetched at once;
  /// without it (no GPS fix yet) they wait for [plan].
  void setDestination(Place? place, {LatLng? from}) {
    destination = place;
    _round++;
    routes.clear();
    errors.clear();
    commute = const [];
    commuteError = null;
    selected = 0;
    loading = false;
    planned = false;
    notifyListeners();
    if (place != null && from != null) plan(from);
  }

  void clear() => setDestination(null);

  void setKind(String next) {
    if (!tripKinds.contains(next) || next == kind) return;
    kind = next;
    notifyListeners();
  }

  void select(int i) {
    if (i < 0 || i >= commute.length || i == selected) return;
    selected = i;
    notifyListeners();
  }

  void setMode(String next) {
    if (!routeModes.containsKey(next) || next == mode) return;
    mode = next;
    notifyListeners();
  }

  /// Fetches the commute options and every walking mode in parallel from [from] to the destination. Each answer
  /// shows as it lands, so the quickest draws first, and one failing leaves the others alone.
  Future<void> plan(LatLng from) async {
    final place = destination;
    if (place == null || planned) return;
    planned = true;
    loading = true;
    final round = _round;
    notifyListeners();
    final to = (lat: place.lat, lng: place.lng);
    await Future.wait([
      if (_fetchCommute != null)
        () async {
          try {
            final o = await _fetchCommute(from, to);
            if (round == _round) commute = o;
          } on ApiException catch (e) {
            if (round == _round) commuteError = e.message;
          }
          if (round == _round) notifyListeners();
        }(),
      for (final m in routeModes.keys)
        () async {
          try {
            final r = await _fetch(from, to, m);
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
