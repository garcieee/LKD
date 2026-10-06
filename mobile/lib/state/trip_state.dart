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

const rerouteAfterFixes = 3; // good fixes in a row off the path before a new route is asked for
const rerouteEvery = Duration(seconds: 15); // at least this long between asks

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
  List<CommuteLeg> _tripLegs = const [];
  bool rerouting = false; // a new route from where the user is, is on its way
  int _offFixes = 0; // good fixes in a row that were off the path
  int _tripId = 0; // bumped when a trip starts or ends; a reroute that finds it changed is dropped
  DateTime? _lastReroute;

  /// What time it is, for the reroute cooldown. A field so a test can move it.
  DateTime Function() clock = DateTime.now;
  bool loading = false;
  bool planned = false; // routes for this destination have been asked for
  int _round = 0; // bumped per destination; answers from an older one are dropped

  WalkRoute? get route => routes[mode];
  String? get error => errors[mode];
  bool get hasCommute => _fetchCommute != null;

  /// The legs of the trip as it is being travelled. Once Start is pressed these are the trip's own copy: a reroute
  /// replaces the leg the user left, and the planned routes stay as they were.
  List<CommuteLeg> get legs => started ? _tripLegs : activeLegs;
  /// The legs of the trip being taken: the chosen commute option, or, with no ride (or started from the walking
  /// step), the chosen walking route all the way.
  List<CommuteLeg> get activeLegs {
    final o = step == TripStep.commute ? option : null, r = route;
    if (o != null) return o.legs;
    if (r == null) return const [];
    return [CommuteLeg.walk(r, 'Walk to ${destination?.label ?? 'your destination'}')];
  }

  /// Whether Start can be pressed: on the walking step once there is a route (a walk all the way), on the commute
  /// step once the options have landed (or failed) and there is a trip.
  bool get canStart => step == TripStep.commute ? !commuteLoading && activeLegs.isNotEmpty : route != null;

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
    _endTrip();
    loading = false;
    planned = false;
    notifyListeners();
    if (place != null && from != null) plan(from);
  }

  void clear() => setDestination(null);

  void start() {
    if (!canStart || started) return;
    _endTrip();
    _tripLegs = List.of(activeLegs);
    started = true;
    notifyListeners();
  }

  void end() {
    if (!started) return;
    _endTrip();
    notifyListeners();
  }

  // Forgets everything about a trip being travelled, and so drops a reroute still on its way.
  void _endTrip() {
    started = false;
    progress = null;
    _leg = 0;
    _tripLegs = const [];
    rerouting = false;
    _offFixes = 0;
    _lastReroute = null;
    _tripId++;
  }

  /// A new GPS fix while the trip is on. Listeners hear about it only when something worth showing changed: the
  /// leg, arriving, going off the line, the next turn, or the distance left by 10 m. A [weak] fix (a rough guess,
  /// see weakAccuracyM) moves the user along but does not count towards being off the path.
  ///
  /// Off the path on a walk for [rerouteAfterFixes] good fixes in a row: ask for a new route from here to the end
  /// of that leg, at most once per [rerouteEvery].
  void update(double lat, double lng, {bool weak = false}) {
    if (!started) return;
    final p = tripProgress(legs, _leg, lat, lng), old = progress;
    if (p == null) return;
    _leg = p.leg;
    progress = p;
    if (!p.offRoute) {
      _offFixes = 0;
    } else if (!weak) {
      _offFixes++;
    }
    if (_offFixes >= rerouteAfterFixes) _reroute(lat, lng);
    if (old == null ||
        old.leg != p.leg ||
        old.arrived != p.arrived ||
        old.offRoute != p.offRoute ||
        old.turn != p.turn ||
        (old.leftM / 10).round() != (p.leftM / 10).round()) {
      notifyListeners();
    }
  }

  // Replaces the leg the user is on with a walk from ([lat], [lng]) to where that leg ended, in the picked mode (so
  // reported hazards are steered around as before). A failed ask keeps the old line; the next fix past the cooldown
  // tries again while the user is still off it.
  Future<void> _reroute(double lat, double lng) async {
    final now = clock(), last = _lastReroute;
    if (rerouting || (last != null && now.difference(last) < rerouteEvery)) return;
    final i = _leg, old = _tripLegs[i], end = old.line.last, id = _tripId;
    _lastReroute = now;
    rerouting = true;
    notifyListeners();
    try {
      final r = await _fetch((lat: lat, lng: lng), (lat: end[1], lng: end[0]), mode);
      if (id != _tripId) return;
      _tripLegs[i] = CommuteLeg.walk(r, old.label);
      _offFixes = 0;
      progress = tripProgress(_tripLegs, i, lat, lng);
    } on ApiException {
      if (id != _tripId) return;
    }
    rerouting = false;
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
