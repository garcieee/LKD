// Where the user wants to go, the walking routes there in each mode, and the commute options (walk, ride, walk).
// The trip goes in steps: compare the walking routes and pick a mode, then pick a commute option (its walking legs
// use that mode). The map draws the pin and the chosen route's line. The start is the user's live location, given
// when the destination is picked.
// ponytail: the routes are worked out once from that start and not redone as the user walks. Upgrade:
// re-plan when the location drifts a block from the line.
import 'package:flutter/foundation.dart';

import '../api/api_client.dart';
import 'trip_progress.dart';

typedef LatLng = ({double lat, double lng});
typedef RouteFn = Future<WalkRoute> Function(LatLng from, LatLng to, String mode);
typedef CommuteFn = Future<List<CommuteOption>> Function(LatLng from, LatLng to, String mode);

/// What the card shows: the walking routes to compare, then the ways to commute.
enum TripStep { walk, commute }

class TripState extends ChangeNotifier {
  TripState(this._fetch, [this._fetchCommute]);

  final RouteFn _fetch;
  final CommuteFn? _fetchCommute; // null: no commute options (walking only)

  Place? destination;
  String mode = 'walkable'; // the mode being shown: a key of routeModes
  final routes = <String, WalkRoute>{}; // filled as each mode's answer arrives
  final errors = <String, String>{}; // why a mode has no route, fit to show
  TripStep step = TripStep.walk;
  List<CommuteOption> commute = const []; // quickest first, for walking mode [commuteMode]
  String? commuteError; // why there are no commute options, fit to show
  String? commuteMode; // the walking mode the commute options were asked for
  bool commuteLoading = false;
  int selected = 0; // index into commute: the one drawn on the map
  LatLng? _from; // where the trip starts, kept from plan() so the commute options can be asked for later
  bool started = false; // the user pressed Start: the trip is on
  TripProgress? progress; // where the user is on the trip, once a fix has come in since Start
  int _leg = 0; // the leg the user is on; only ever goes up
  bool loading = false;
  bool planned = false; // routes for this destination have been asked for
  int _round = 0; // bumped per destination; answers from an older one are dropped

  WalkRoute? get route => routes[mode];
  String? get error => errors[mode];
  bool get hasCommute => _fetchCommute != null;
  /// The legs of the trip being taken: the chosen commute option, or, with no ride, the chosen walking route.
  List<CommuteLeg> get activeLegs {
    final o = option, r = route;
    if (o != null) return o.legs;
    if (r == null) return const [];
    return [CommuteLeg.walk(r, 'Walk to ${destination?.label ?? 'your destination'}')];
  }

  /// Whether Start can be pressed: on the commute step, once the options have landed (or failed) and there is a route.
  bool get canStart => step == TripStep.commute && !commuteLoading && activeLegs.isNotEmpty;

  CommuteOption? get option => selected < commute.length ? commute[selected] : null;

  /// Picks (or, with null, clears) the destination. With [from] the three routes are fetched at once;
  /// without it (no GPS fix yet) they wait for [plan].
  void setDestination(Place? place, {LatLng? from}) {
    destination = place;
    _round++;
    routes.clear();
    errors.clear();
    step = TripStep.walk;
    commute = const [];
    commuteError = null;
    commuteMode = null;
    commuteLoading = false;
    selected = 0;
    _from = null;
    started = false;
    progress = null;
    _leg = 0;
    loading = false;
    planned = false;
    notifyListeners();
    if (place != null && from != null) plan(from);
  }

  void clear() => setDestination(null);

  void start() {
    if (!canStart || started) return;
    started = true;
    progress = null;
    _leg = 0;
    notifyListeners();
  }

  void end() {
    if (!started) return;
    started = false;
    progress = null;
    _leg = 0;
    notifyListeners();
  }

  /// A new GPS fix while the trip is on. Listeners hear about it only when something worth showing changed: the
  /// leg, arriving, going off the line, or the distance left by 10 m.
  void update(double lat, double lng) {
    if (!started) return;
    final p = tripProgress(activeLegs, _leg, lat, lng), old = progress;
    if (p == null) return;
    _leg = p.leg;
    progress = p;
    if (old == null ||
        old.leg != p.leg ||
        old.arrived != p.arrived ||
        old.offRoute != p.offRoute ||
        (old.leftM / 10).round() != (p.leftM / 10).round()) {
      notifyListeners();
    }
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

  /// Moves to the commute step and asks for the options with walking in the chosen [mode]. Options already fetched
  /// for this mode are kept, so stepping back and forward again costs nothing; a different mode asks again.
  Future<void> toCommute() async {
    step = TripStep.commute;
    final place = destination, from = _from, fetch = _fetchCommute;
    if (place == null || from == null || fetch == null || commuteMode == mode) {
      notifyListeners();
      return;
    }
    commute = const [];
    commuteError = null;
    commuteMode = mode;
    commuteLoading = true;
    selected = 0;
    final round = _round, asked = mode;
    notifyListeners();
    try {
      final o = await fetch(from, (lat: place.lat, lng: place.lng), asked);
      if (round == _round) commute = o;
    } on ApiException catch (e) {
      if (round == _round) {
        commuteError = e.message;
        commuteMode = null; // a failed ask is worth repeating
      }
    }
    if (round != _round) return;
    commuteLoading = false;
    notifyListeners();
  }

  void backToWalk() {
    if (step == TripStep.walk) return;
    step = TripStep.walk;
    notifyListeners();
  }

  /// Fetches every walking mode in parallel from [from] to the destination. Each answer shows as it lands, so
  /// the quickest mode draws first, and one mode failing leaves the others alone.
  Future<void> plan(LatLng from) async {
    final place = destination;
    if (place == null || planned) return;
    planned = true;
    _from = from;
    loading = true;
    final round = _round;
    notifyListeners();
    final to = (lat: place.lat, lng: place.lng);
    await Future.wait([
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
