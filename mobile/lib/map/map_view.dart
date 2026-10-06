// The map page: a full-bleed Mapbox map pinned on Makati, with floating chips over it.
// Mirrors dashboard/src/map/MapCanvas.tsx and App.tsx.
import 'dart:async';
import 'dart:math' as math;
import 'dart:typed_data' show Uint8List;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show rootBundle;
import 'package:geolocator/geolocator.dart' show Geolocator;
import 'package:mapbox_maps_flutter/mapbox_maps_flutter.dart' hide Size; // Flutter's Size here
import 'package:wakelock_plus/wakelock_plus.dart';

import '../api/api_client.dart';
import '../config/env.dart';
import '../config/makati.dart';
import '../config/map_styles.dart';
import '../features/navigate/compass_chip.dart';
import '../features/navigate/nav_bar.dart';
import '../features/report/ar_math.dart' show inMakati;
import '../features/report/report_screen.dart';
import '../features/search/place_search.dart';
import '../features/search/search_bar.dart';
import '../features/transfer_walk/hub_picker.dart';
import '../features/transfer_walk/route_card.dart';
import '../layers/buildings_layer.dart';
import '../layers/congestion_layer.dart';
import '../layers/destination_layer.dart';
import '../layers/hubs_layer.dart';
import '../layers/reports_layer.dart';
import '../layers/route_layer.dart';
import '../state/layers_state.dart';
import '../state/location_state.dart';
import '../state/trip_state.dart';
import '../theme.dart';
import '../widgets/map_menu.dart';
import 'pin_chip.dart';

// Strip at the bottom kept free of chips for the Mapbox logo and the attribution button.
const _ornamentBand = 40.0;

class MapView extends StatefulWidget {
  const MapView({super.key, @visibleForTesting this.mapboxToken = Env.mapboxToken});

  final String mapboxToken; // a test builds the page without a real token

  @override
  State<MapView> createState() => _MapViewState();
}

class _MapViewState extends State<MapView> with WidgetsBindingObserver {
  final _layers = LayersState();
  final _location = LocationState();
  final _trip = TripState(
    (from, to, mode) => api.route(from: from, to: to, mode: mode),
    (from, to, mode) => api.commute(from: from, to: to, mode: mode),
  );
  late final _search = PlaceSearch((text, near) => api.geocode(text, near: near));
  MapboxMap? _map;
  Timer? _timer;
  Timer? _reportsTimer;
  List<Report> _reports = const []; // the pins on the map, for the card a tap opens
  List<Hub> _hubs = const []; // transit terminals and stops: static, loaded once
  Future<void> _queue = Future.value(); // style edits one at a time: a toggle can land mid-refresh
  bool _framed = false;

  // The camera's home and lock: the city plus Makati.lockMargin on every side.
  static final _home = CoordinateBounds(
    southwest: Point(
      coordinates: Position(Makati.west - Makati.lockMargin, Makati.south - Makati.lockMargin),
    ),
    northeast: Point(
      coordinates: Position(Makati.east + Makati.lockMargin, Makati.north + Makati.lockMargin),
    ),
    infiniteBounds: false,
  );

  // The tilt every camera move ends on: flat in 2D.
  bool _threeDShown = false; // what the camera and the buildings layer last matched
  double get _pitch => _layers.threeD ? Makati.pitch : 0;

  // Where the camera is when the whole city cannot be fitted: Makati.zoom frames it on a ~390px phone.
  CameraOptions get _fallback => CameraOptions(
    center: Point(coordinates: Position(Makati.lng, Makati.lat)),
    zoom: Makati.zoom,
    bearing: 0,
    pitch: _pitch,
  );

  // The first frames, until the style loads and the whole city is framed.
  final _opening = CameraViewportState(
    center: Point(coordinates: Position(Makati.lng, Makati.lat)),
    zoom: Makati.zoom,
  );

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _layers.addListener(_apply);
    _location.addListener(_syncPuck);
    _location.addListener(_planWhenLocated);
    _location.addListener(_startNearUser);
    _location.addListener(_trackTrip);
    _location.start();
    _trip.addListener(_onTrip);
    _trip.addListener(_syncAwake);
    _trip.addListener(_syncFollow);
    _timer = Timer.periodic(congestionRefresh, (_) {
      if (_layers.congestionOn) _layers.refresh();
    });
    _reportsTimer = Timer.periodic(reportsRefresh, (_) {
      _loadReports();
      _loadHubs(); // a no-op once they are in
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _timer?.cancel();
    _reportsTimer?.cancel();
    if (_awake) WakelockPlus.disable();
    for (final s in _gestures) {
      s.cancel();
    }
    _bearing.dispose();
    _following.dispose();
    _viewport.dispose();
    _layers.dispose();
    _location.dispose();
    _trip.dispose();
    _search.dispose();
    super.dispose();
  }

  // Back from the Settings screen: look again, so turning Location on shows the pin at once.
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && _location.status != Gps.ok) _location.start();
  }

  // The pin: Mapbox's location puck (dot, heading arrow, accuracy ring), on while we have GPS.
  // It reads the phone's location itself; LocationState only gets the permission first.
  bool _puckOn = false;

  Future<void> _syncPuck() async {
    final map = _map;
    final want = _location.status == Gps.ok;
    if (map == null || want == _puckOn) return;
    _puckOn = want;
    try {
      // An arrow in place of the dot: the bearing image is the part that turns with the phone's heading, its tip the front.
      final arrow = (await rootBundle.load('assets/arrow.png')).buffer.asUint8List();
      await map.location.updateSettings(
        LocationComponentSettings(
          enabled: want,
          showAccuracyRing: true,
          puckBearingEnabled: true,
          puckBearing: PuckBearing.HEADING,
          locationPuck: LocationPuck(
            locationPuck2D: LocationPuck2D(
              topImage: Uint8List(0),
              bearingImage: arrow,
              shadowImage: Uint8List(0),
            ),
          ),
        ),
      );
    } catch (e) {
      _puckOn = false; // try again on the next fix
      debugPrint('location puck: $e');
    }
  }

  // The user's position as the search's focus: results near them rank first.
  Near? _near() {
    final fix = _location.fix;
    return fix == null ? null : (lat: fix.latitude, lng: fix.longitude);
  }

  // The destination was picked, cleared, or a route arrived, changed mode or was picked from the commute list:
  // redraw the pin and the line. The camera moves twice per destination: to the user and the pin at once, then
  // to the whole route when the first one lands. Picking another commute option, or Commute/Walk, refits to
  // what is drawn; changing walking mode leaves the camera alone.
  //
  // On a trip the line is what is left of it, from the user's spot on, redrawn at each step of progress. Between
  // those only the line is redrawn: the pins are where they were, and the camera is following the user.
  Place? _framedTrip;
  String? _framedRoute; // what the camera last fitted: 'walk' or 'commute:<option id>'
  Place? _pinsFor; // the destination the pins are drawn for (null after a style load drops them)
  List<double>? _start; // where the trip began: the "From" pin, which stays put while the line is rerouted

  void _onTrip() {
    _queue = _queue.then((_) async {
      final map = _map, place = _trip.destination, started = _trip.started;
      if (map == null) return;
      // The commute step draws the chosen option; until one lands, or when there is none, the walking route.
      final option = _trip.step == TripStep.commute ? _trip.option : null;
      final route = option == null ? _trip.route : null;
      try {
        if (!await map.isStyleLoaded()) return; // _ready() draws it once the style is up
        if (started && place != null && place == _pinsFor) {
          await showTrip(map, _trip.legs, _trip.progress);
          return;
        }
        // "From" is where the line begins: the user's position when the routes were asked for.
        final first = option != null ? option.legs.first.line : route?.line;
        if (!started) _start = first == null || first.isEmpty ? null : first.first;
        await showDestination(map, place, start: started ? _start ??= _trip.legs.first.line.first : _start);
        _pinsFor = place;
        if (started) {
          await showTrip(map, _trip.legs, _trip.progress);
        } else if (option != null) {
          await showCommute(map, option);
        } else {
          await showRoute(map, route);
        }
        if (place != _framedTrip) {
          _framedTrip = place;
          _framedRoute = null;
          if (place != null) await _frameTrip(map, place);
        }
        final key = started ? null : (option != null ? 'commute:${option.id}' : (route != null ? 'walk' : null));
        if (place != null && key != null && key != _framedRoute) {
          _framedRoute = key;
          final line = option != null ? [for (final l in option.legs) ...l.line] : route!.line;
          await _fit(map, [for (final p in line) Point(coordinates: Position(p[0], p[1]))]);
        }
      } catch (e) {
        debugPrint('trip: $e');
      }
    });
  }

  // The GPS fix can arrive after the destination was picked: plan the routes as soon as it does.
  void _planWhenLocated() {
    final fix = _location.fix;
    if (fix != null && _trip.destination != null && !_trip.planned) {
      _trip.plan((lat: fix.latitude, lng: fix.longitude));
    }
  }

  // While the trip is on, every fix moves the user along it.
  void _trackTrip() {
    final fix = _location.fix;
    if (fix == null || !_trip.started) return;
    if (_pendingFollow) _follow(); // Start came before the first fix: the camera joins the user now
    _trip.update(fix.latitude, fix.longitude, weak: fix.accuracy > weakAccuracyM);
  }

  // The camera follows the pin and turns with the phone's heading, so the way ahead is up the screen. Mapbox's
  // puck already shows the heading; this moves the camera with it. Not while the user is panning the map.
  final _viewport = ViewportController();
  final _bearing = ValueNotifier<double>(0); // where the top of the map points, degrees clockwise from north
  final _following = ValueNotifier<bool>(false);
  final _gestures = <StreamSubscription<MapContentGestureContext>>[];
  bool _readingBearing = false;
  bool _pendingFollow = false;
  bool _wasStarted = false;

  bool _follow() {
    final fix = _location.fix;
    if (fix == null || !inMakati(fix.latitude, fix.longitude)) {
      _pendingFollow = fix == null && _trip.started; // no fix yet: join the user when the first one lands
      return false;
    }
    _pendingFollow = false;
    _viewport.moveTo(FollowPuckViewportState(zoom: Makati.walkZoom, pitch: _pitch));
    _following.value = true;
    return true;
  }

  void _stopFollowing({bool northUp = false}) {
    _pendingFollow = false;
    if (!_following.value) return;
    _following.value = false;
    _viewport.moveTo(const IdleViewportState(), transition: null);
    if (northUp) _map?.easeTo(CameraOptions(bearing: 0), MapAnimationOptions(duration: 600));
  }

  // Start puts the camera on the user, turning with them; End returns it to north-up. Off a trip the map stays
  // north-up and only the arrow turns.
  void _syncFollow() {
    _layers.setNavigating(_trip.started); // before the camera moves: Auto's tilt follows it
    if (_trip.started == _wasStarted) return;
    _wasStarted = _trip.started;
    if (_wasStarted) {
      _follow();
    } else {
      _stopFollowing(northUp: true);
    }
  }

  // The camera moves every frame while following: read the bearing for the compass one at a time.
  Future<void> _readBearing() async {
    final map = _map;
    if (map == null || _readingBearing) return;
    _readingBearing = true;
    try {
      final b = (await map.getCameraState()).bearing;
      _bearing.value = (b % 360 + 360) % 360;
    } catch (e) {
      debugPrint('bearing: $e');
    } finally {
      _readingBearing = false;
    }
  }

  // The screen stays on from Start until the user arrives or ends the trip, so the app keeps getting fixes and
  // the nav bar stays in view. Foreground only: no background location service.
  bool _awake = false;

  void _syncAwake() {
    final want = _trip.started && _trip.progress?.arrived != true;
    final starting = _trip.started && _trip.progress == null && !_awake;
    if (want != _awake) {
      _awake = want;
      WakelockPlus.toggle(enable: want).catchError((Object e) => debugPrint('wakelock: $e'));
    }
    if (starting) _trackTrip(); // Start was pressed with a fix already in hand: show where they are now
  }

  // A walking app opens at street level on the user, north-up, not on the whole city: once, on the first fix
  // inside Makati (whether it comes before or after the map is framed).
  bool _startedNearUser = false;

  void _startNearUser() {
    final map = _map, fix = _location.fix;
    if (_startedNearUser || map == null || !_framed || fix == null || !inMakati(fix.latitude, fix.longitude)) return;
    _startedNearUser = true;
    if (_trip.destination != null) return; // they already picked somewhere: that framing wins
    map.flyTo(
      CameraOptions(
        center: Point(coordinates: Position(fix.longitude, fix.latitude)),
        zoom: Makati.walkZoom,
        bearing: 0,
        pitch: _pitch,
      ),
      MapAnimationOptions(duration: 1200),
    );
  }

  // Both pins on screen; just the destination when we do not know where the user is (or they are
  // outside the city).
  Future<void> _frameTrip(MapboxMap map, Place place) async {
    final fix = _location.fix;
    final dest = Point(coordinates: Position(place.lng, place.lat));
    if (fix == null || !inMakati(fix.latitude, fix.longitude)) {
      await map.flyTo(CameraOptions(center: dest, zoom: 16, bearing: 0, pitch: _pitch), MapAnimationOptions(duration: 1000));
      return;
    }
    await _fit(map, [Point(coordinates: Position(fix.longitude, fix.latitude)), dest]);
  }

  // Frames [points] clear of the search field above and the buttons below.
  Future<void> _fit(MapboxMap map, List<Point> points) async {
    final fit = await map.cameraForCoordinates(
      points,
      MbxEdgeInsets(top: 190, left: 60, bottom: 300, right: 60),
      0,
      0,
    );
    // Points close together would zoom to street-corner level: stop at 17.
    final zoom = fit.zoom;
    final camera = zoom != null && zoom.isFinite ? CameraOptions(center: fit.center, zoom: math.min(zoom, 17), bearing: 0, pitch: _pitch) : fit;
    await map.flyTo(camera, MapAnimationOptions(duration: 1000));
  }

  // The locate button: fly to the pin. Outside Makati the camera is locked to the city, so say so.
  void _locate() {
    final fix = _location.fix;
    if (fix == null) {
      _location.start(); // permission or GPS missing: ask again, the chip says why
      return;
    }
    if (!inMakati(fix.latitude, fix.longitude)) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("You're outside Makati. Lakad covers the city only.")),
      );
      return;
    }
    if (_trip.started) {
      _follow(); // on a trip the locate button puts the camera back on the user, turning with them
      return;
    }
    _map?.flyTo(
      CameraOptions(
        center: Point(coordinates: Position(fix.longitude, fix.latitude)),
        zoom: Makati.walkZoom,
        bearing: 0,
        pitch: _pitch,
      ),
      MapAnimationOptions(duration: 1000),
    );
  }

  // Fetches the reports, then redraws the pins. A failed fetch keeps the pins already drawn.
  Future<void> _loadReports() async {
    try {
      _reports = await api.reports();
    } catch (e) {
      debugPrint('reports: $e'); // offline, or an odd answer: try again next round
      return;
    }
    if (!mounted) return;
    _queue = _queue.then((_) async {
      final map = _map;
      try {
        if (map != null && await map.isStyleLoaded()) await showReports(map, _reports);
      } catch (e) {
        debugPrint('reports layer: $e'); // a failed redraw must not take the app down
      }
    });
  }

  // The hubs never change while the app runs, so one good answer is enough; a failed one is retried
  // with the next report refresh.
  Future<void> _loadHubs() async {
    if (_hubs.isNotEmpty) return;
    try {
      _hubs = await api.hubs();
    } catch (e) {
      debugPrint('hubs: $e');
      return;
    }
    if (mounted) {
      setState(() {}); // the layer sheet's colour key
      _apply(); // draws them
    }
  }

  void _openHub(String id) {
    final hub = _hubs.where((h) => h.id == id).firstOrNull;
    if (hub != null && mounted) showHubSheet(context, hub, from: _near(), onWalk: _walkTo);
  }

  // "Walk here" on a hub: it becomes the destination, so the route card and line work as for a searched place.
  void _walkTo(Hub hub) => _trip.setDestination(hub.place, from: _near());

  void _openReport(String id) {
    final report = _reports.where((r) => r.id == id).firstOrNull;
    if (report != null && mounted) showReportSheet(context, report);
  }

  Future<void> _report() async {
    final sent = await Navigator.push<Report>(
      context,
      MaterialPageRoute(builder: (_) => const ReportScreen()),
    );
    if (sent == null || !mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(sent.isSos ? 'SOS sent. The city has your video and location.' : 'Report sent. Thanks!')),
    );
    _loadReports(); // the new pin
  }

  // Re-applies the congestion layer after any state change or refresh.
  void _apply() {
    _queue = _queue.then((_) => _run());
  }

  Future<void> _run() async {
    final map = _map;
    if (map == null) return;
    try {
      if (!await map.isStyleLoaded()) return; // _ready() comes back here once it has
      final key = Env.tomtomKey;
      if (_layers.congestionOn && key.isNotEmpty) {
        await addCongestion(map, key, _layers.stamp);
      } else {
        await removeCongestion(map);
      }
      if (_layers.hubsOn && _hubs.isNotEmpty) {
        await showHubs(map, _hubs);
      } else {
        await hideHubs(map);
      }
    } catch (e) {
      debugPrint('map layers: $e'); // a failed refresh must not take the app down
    }
    try {
      final threeD = _layers.threeD;
      if (threeD != _threeDShown) {
        _threeDShown = threeD;
        await map.easeTo(CameraOptions(pitch: _pitch), MapAnimationOptions(duration: 600));
      }
      if (threeD) {
        await addBuildings(map); // no-op once there
      } else {
        await removeBuildings(map);
      }
    } catch (e) {
      debugPrint('buildings layer: $e'); // a flat map is fine
    }
  }

  Future<void> _onMapCreated(MapboxMap map) async {
    _map = map;
    // The user took hold of the map (dragging or turning it): let go of it.
    _gestures
      ..forEach((s) => s.cancel())
      ..clear()
      ..addAll([
        map.gestures.pan.gestureEvents.listen((_) => _stopFollowing()),
        map.gestures.rotate.gestureEvents.listen((_) => _stopFollowing()),
      ]);
    onReportTap(map, _openReport);
    onHubTap(map, _openHub);
    // Edge to edge: the map runs under the gesture bar. Lift the Mapbox logo and the attribution
    // button above it, into the strip the chips leave free. Margins are logical pixels.
    final lift = MediaQuery.paddingOf(context).bottom + 8;
    await Future.wait([
      map.logo.updateSettings(LogoSettings(marginBottom: lift)),
      map.attribution.updateSettings(AttributionSettings(marginBottom: lift)),
      map.compass.updateSettings(CompassSettings(enabled: false)), // under the status bar
      map.scaleBar.updateSettings(ScaleBarSettings(enabled: false)),
    ]);
    await _ready();
  }

  // Runs from both onMapCreated and the style-loaded callback, whichever comes last does the work.
  Future<void> _ready() async {
    final map = _map;
    if (map == null || !await map.isStyleLoaded()) return;
    _apply(); // also redraws the buildings a new style dropped
    _loadReports();
    _loadHubs();
    _puckOn = false; // a new style drops the puck
    _syncPuck();
    _pinsFor = null; // a new style dropped the pins
    if (_trip.destination != null) _onTrip(); // and the destination pin and route line
    try {
      // Mercator, whatever the style asks for: the lock below is worked out for it.
      await map.setProjection(StyleProjection(name: StyleProjectionName.mercator));
      if (!_framed) {
        _framed = true;
        await _frame(map);
        _startNearUser(); // the fix may have arrived first
      }
    } catch (e) {
      debugPrint('camera lock: $e');
    }
  }

  // Frames the whole city and locks the camera to it: the camera centre stays inside the city plus
  // lockMargin, and the zoom between the zoom that fits it on this screen and Makati.maxZoom.
  // ponytail: native bounds constrain the camera CENTRE only (unlike GL JS maxBounds), so near an
  // edge the view can overhang the city by up to half a screen. Upgrade: on camera idle, shrink the
  // bounds by half the visible span (coordinateBoundsForCamera) and call setBounds again.
  // Also worked out only on load: redo it on window resize if the app gets split screen.
  Future<void> _frame(MapboxMap map) async {
    final fit = await map.cameraForCoordinateBounds(
      _home,
      MbxEdgeInsets(top: 0, left: 0, bottom: 0, right: 0),
      0,
      0,
      null,
      null,
    );
    final zoom = fit.zoom ?? double.nan;
    final fits = zoom.isFinite; // not when the native view has no size yet
    await map.setBounds(
      CameraBoundsOptions(
        bounds: _home,
        minZoom: fits ? math.min(math.max(zoom, Makati.minZoom), Makati.maxZoom) : Makati.zoom,
        maxZoom: Makati.maxZoom,
      ),
    );
    final camera = fits ? CameraOptions(center: fit.center, zoom: fit.zoom, bearing: 0, pitch: _pitch) : _fallback;
    await map.setCamera(camera);
  }

  @override
  Widget build(BuildContext context) {
    if (widget.mapboxToken.isEmpty) return const _NoToken();
    // The keyboard is up: the search suggestions need the room the chips would take.
    final typing = MediaQuery.viewInsetsOf(context).bottom > 0;
    return Scaffold(
      resizeToAvoidBottomInset: false, // the keyboard covers the page; the map is not squeezed under it
      body: Stack(
        children: [
          Positioned.fill(
            child: MapWidget(
              key: const ValueKey('map'),
              styleUri: MapStyles.map,
              viewport: _opening,
              viewportController: _viewport,
              onMapCreated: _onMapCreated,
              onStyleLoadedListener: (_) => _ready(),
              onCameraChangeListener: (_) => _readBearing(),
            ),
          ),
          // Chips sit inside the system bars and the display cutout, with at least 14px around.
          SafeArea(
            minimum: const EdgeInsets.all(14),
            child: Stack(
              children: [
                Align(
                  alignment: Alignment.topCenter,
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          const _Brand(),
                          // Shrinks a little rather than overflow, at 320 dp and large text.
                          Flexible(
                            child: FittedBox(
                              fit: BoxFit.scaleDown,
                              child: CompassChip(bearing: _bearing, following: _following),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 10),
                      PlaceSearchBar(search: _search, trip: _trip, near: _near),
                    ],
                  ),
                ),
                Offstage(
                  offstage: typing,
                  child: Align(
                    alignment: Alignment.bottomCenter,
                    child: Padding(
                      padding: const EdgeInsets.only(bottom: _ornamentBand),
                      child: ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 420),
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          crossAxisAlignment: CrossAxisAlignment.end,
                          children: [
                            _LocateRow(location: _location, onLocate: _locate, onMenu: () => showMapMenu(context, _layers)),
                            const SizedBox(height: 10),
                            _ReportButton(onPressed: _report),
                            const SizedBox(height: 10),
                            // With a trip on, the card takes the traffic panel's place: the report button
                            // and the locate row stay. On a short screen or at large text it scrolls.
                            Flexible(
                              child: SingleChildScrollView(
                                clipBehavior: Clip.none, // keeps the chip's soft shadow
                                child: ListenableBuilder(
                                  listenable: _trip,
                                  builder: (context, _) =>
                                      _trip.destination == null
                                      ? const SizedBox.shrink()
                                      : _trip.started
                                      ? NavBar(trip: _trip)
                                      : RouteCard(trip: _trip),
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// The GPS accuracy (or why there is no pin) next to the locate button.
class _LocateRow extends StatelessWidget {
  const _LocateRow({required this.location, required this.onLocate, required this.onMenu});

  final LocationState location;
  final VoidCallback onLocate;
  final VoidCallback onMenu;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: location,
      builder: (context, _) {
        final fix = location.fix;
        final (text, action, onAction) = switch (location.status) {
          Gps.starting => ('Finding you…', null, null),
          Gps.off => ('Location is off.', 'Turn on', Geolocator.openLocationSettings),
          Gps.denied => ('Lakad needs your location.', 'Allow', location.start),
          Gps.blocked => ('Location is blocked for Lakad.', 'Settings', Geolocator.openAppSettings),
          Gps.ok when fix == null => ('Finding you…', null, null),
          Gps.ok => (_fixText(fix!.latitude, fix.longitude, fix.accuracy), null, null),
        };
        final weak = location.status == Gps.ok && fix != null && fix.accuracy > weakAccuracyM;
        return Row(
          mainAxisAlignment: MainAxisAlignment.end,
          children: [
            Flexible(
              child: ChipCard(
                padding: EdgeInsets.only(left: 14, right: action == null ? 14 : 4),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Flexible(
                      child: Text(
                        text,
                        style: TextStyle(fontSize: 12, color: weak ? warn : ink),
                      ),
                    ),
                    if (action != null) TextButton(onPressed: onAction, child: Text(action)),
                  ],
                ),
              ),
            ),
            const SizedBox(width: 10),
            ChipCard(
              padding: EdgeInsets.zero,
              child: IconButton(
                tooltip: 'Show my location',
                onPressed: onLocate,
                icon: const Icon(Icons.my_location, size: 22, color: navy),
              ),
            ),
            const SizedBox(width: 10),
            ChipCard(
              padding: EdgeInsets.zero,
              child: IconButton(
                tooltip: 'Map menu',
                onPressed: onMenu,
                icon: const Icon(Icons.menu, size: 22, color: navy),
              ),
            ),
          ],
        );
      },
    );
  }

  static String _fixText(double lat, double lng, double accuracy) {
    final a = accuracyLabel(accuracy);
    final where = inMakati(lat, lng) ? '' : "You're outside Makati";
    final weak = accuracy > weakAccuracyM ? 'Weak signal' : '';
    final parts = [where, a.isEmpty ? '' : (weak.isEmpty ? a : '$a, $weak')].where((s) => s.isNotEmpty);
    return parts.isEmpty ? 'Located' : parts.join(' · ');
  }
}

class _Brand extends StatelessWidget {
  const _Brand();

  @override
  Widget build(BuildContext context) {
    return const ChipCard(
      padding: EdgeInsets.fromLTRB(14, 9, 14, 10),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Lakad',
            style: TextStyle(
              fontFamily: serif,
              fontSize: 25,
              height: 1,
              fontWeight: FontWeight.w500,
              letterSpacing: -0.25,
            ),
          ),
          SizedBox(height: 4),
          Text('MAKATI · LGU OPS', style: TextStyle(fontSize: 11, letterSpacing: 1.3)),
        ],
      ),
    );
  }
}

// The primary action: navy, with the floating chips' shadow. It sits in the chips' SafeArea, so it
// stays above the gesture bar.
class _ReportButton extends StatelessWidget {
  const _ReportButton({required this.onPressed});

  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: const BoxDecoration(
        borderRadius: radiusChip,
        boxShadow: [BoxShadow(color: Color(0x2959534E), blurRadius: 18, offset: Offset(0, 4))],
      ),
      child: FilledButton.icon(
        onPressed: onPressed,
        icon: const Icon(Icons.photo_camera_outlined, size: 20),
        label: const Text('Report'),
        style: FilledButton.styleFrom(
          minimumSize: const Size(0, 48),
          padding: const EdgeInsets.symmetric(horizontal: 18),
          shape: const RoundedRectangleBorder(borderRadius: radiusChip),
          textStyle: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
        ),
      ),
    );
  }
}

class _NoToken extends StatelessWidget {
  const _NoToken();

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      body: SafeArea(
        child: Center(
          child: Padding(
            padding: EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text('No Mapbox token.'),
                SizedBox(height: 6),
                Text(
                  'Copy env.example.json to env.json and set MAPBOX_TOKEN, '
                  'then run flutter run --dart-define-from-file=env.json.',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: muted),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
