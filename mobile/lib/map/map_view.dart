// The map page: a full-bleed Mapbox map pinned on Makati, with floating chips over it.
// Mirrors dashboard/src/map/MapCanvas.tsx and App.tsx.
import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart' show Geolocator;
import 'package:mapbox_maps_flutter/mapbox_maps_flutter.dart' hide Size; // Flutter's Size here

import '../api/api_client.dart';
import '../config/env.dart';
import '../config/makati.dart';
import '../config/map_styles.dart';
import '../features/report/ar_math.dart' show inMakati;
import '../features/report/report_screen.dart';
import '../features/search/place_search.dart';
import '../features/search/search_bar.dart';
import '../features/transfer_walk/hub_picker.dart';
import '../features/transfer_walk/route_card.dart';
import '../layers/congestion_layer.dart';
import '../layers/destination_layer.dart';
import '../layers/hubs_layer.dart';
import '../layers/reports_layer.dart';
import '../layers/route_layer.dart';
import '../state/layers_state.dart';
import '../state/location_state.dart';
import '../state/trip_state.dart';
import '../theme.dart';
import '../widgets/layer_sheet.dart';
import 'pin_chip.dart';

// Strip at the bottom kept free of chips for the Mapbox logo and the attribution button.
const _ornamentBand = 40.0;

class MapView extends StatefulWidget {
  const MapView({super.key});

  @override
  State<MapView> createState() => _MapViewState();
}

class _MapViewState extends State<MapView> with WidgetsBindingObserver {
  final _layers = LayersState();
  final _location = LocationState();
  final _trip = TripState((from, to, mode) => api.route(from: from, to: to, mode: mode));
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

  // Where the camera is when the whole city cannot be fitted: Makati.zoom frames it on a ~390px phone.
  static final _fallback = CameraOptions(
    center: Point(coordinates: Position(Makati.lng, Makati.lat)),
    zoom: Makati.zoom,
    bearing: 0,
    pitch: 0,
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
    _location.start();
    _trip.addListener(_onTrip);
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
      await map.location.updateSettings(
        LocationComponentSettings(
          enabled: want,
          pulsingEnabled: want,
          pulsingColor: navy.toARGB32(),
          showAccuracyRing: true,
          puckBearingEnabled: true,
          puckBearing: PuckBearing.HEADING,
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

  // The destination was picked, cleared, or a route arrived or changed mode: redraw the pin and the line.
  // The camera moves twice per destination: to the user and the pin at once, then to the whole route when
  // the first one lands. Changing mode leaves the camera alone.
  Place? _framedTrip;
  bool _routeFramed = false;

  void _onTrip() {
    _queue = _queue.then((_) async {
      final map = _map, place = _trip.destination, route = _trip.route;
      if (map == null) return;
      try {
        if (!await map.isStyleLoaded()) return; // _ready() draws it once the style is up
        await showDestination(map, place);
        await showRoute(map, route);
        if (place != _framedTrip) {
          _framedTrip = place;
          _routeFramed = false;
          if (place != null) await _frameTrip(map, place);
        }
        if (place != null && route != null && !_routeFramed) {
          _routeFramed = true;
          await _fit(map, [for (final p in route.line) Point(coordinates: Position(p[0], p[1]))]);
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

  // Both pins on screen; just the destination when we do not know where the user is (or they are
  // outside the city).
  Future<void> _frameTrip(MapboxMap map, Place place) async {
    final fix = _location.fix;
    final dest = Point(coordinates: Position(place.lng, place.lat));
    if (fix == null || !inMakati(fix.latitude, fix.longitude)) {
      await map.flyTo(CameraOptions(center: dest, zoom: 16, bearing: 0, pitch: 0), MapAnimationOptions(duration: 1000));
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
    final camera = zoom != null && zoom.isFinite ? CameraOptions(center: fit.center, zoom: math.min(zoom, 17), bearing: 0, pitch: 0) : fit;
    await map.flyTo(camera, MapAnimationOptions(duration: 1000));
  }

  // The locate button: fly to the pin. Outside Makati the camera is locked to the city, so say so.
  void _locate() {
    final map = _map, fix = _location.fix;
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
    map?.flyTo(
      CameraOptions(
        center: Point(coordinates: Position(fix.longitude, fix.latitude)),
        zoom: 17,
        bearing: 0,
        pitch: 0,
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

  void _nearbyHubs() {
    _loadHubs(); // if the first try failed
    showNearbyHubs(context, _hubs, from: _near(), onWalk: _walkTo);
  }

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
  }

  Future<void> _onMapCreated(MapboxMap map) async {
    _map = map;
    onReportTap(map, _openReport);
    onHubTap(map, _openHub);
    // Edge to edge: the map runs under the gesture bar. Lift the Mapbox logo and the attribution
    // button above it, into the strip the chips leave free. Margins are logical pixels.
    final lift = MediaQuery.paddingOf(context).bottom + 8;
    await Future.wait([
      map.logo.updateSettings(LogoSettings(marginBottom: lift)),
      map.attribution.updateSettings(AttributionSettings(marginBottom: lift)),
      map.compass.updateSettings(CompassSettings(enabled: false)), // under the status bar; Reset squares the map up
      map.scaleBar.updateSettings(ScaleBarSettings(enabled: false)),
    ]);
    await _ready();
  }

  // Runs from both onMapCreated and the style-loaded callback, whichever comes last does the work.
  Future<void> _ready() async {
    final map = _map;
    if (map == null || !await map.isStyleLoaded()) return;
    _apply();
    _loadReports();
    _loadHubs();
    _puckOn = false; // a new style drops the puck
    _syncPuck();
    if (_trip.destination != null) _onTrip(); // and the destination pin and route line
    try {
      // Mercator, whatever the style asks for: the lock below is worked out for it.
      await map.setProjection(StyleProjection(name: StyleProjectionName.mercator));
      if (!_framed) {
        _framed = true;
        await _frame(map, animate: false);
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
  // Also worked out only on load and on Reset: redo it on window resize if the app gets split screen.
  Future<void> _frame(MapboxMap map, {required bool animate}) async {
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
    final camera = fits ? fit : _fallback;
    if (animate) {
      await map.flyTo(camera, MapAnimationOptions(duration: 1200));
    } else {
      await map.setCamera(camera);
    }
  }

  void _reset() {
    final map = _map;
    if (map != null) _frame(map, animate: true);
  }

  @override
  Widget build(BuildContext context) {
    if (Env.mapboxToken.isEmpty) return const _NoToken();
    return Scaffold(
      body: Stack(
        children: [
          Positioned.fill(
            child: MapWidget(
              key: const ValueKey('map'),
              styleUri: MapStyles.map,
              viewport: _opening,
              onMapCreated: _onMapCreated,
              onStyleLoadedListener: (_) => _ready(),
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
                        children: [const _Brand(), _ResetChip(onPressed: _reset)],
                      ),
                      const SizedBox(height: 10),
                      PlaceSearchBar(search: _search, trip: _trip, near: _near),
                    ],
                  ),
                ),
                Align(
                  alignment: Alignment.bottomCenter,
                  child: Padding(
                    padding: const EdgeInsets.only(bottom: _ornamentBand),
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 420),
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          _LocateRow(location: _location, onLocate: _locate, onTransit: _nearbyHubs),
                          const SizedBox(height: 10),
                          _ReportButton(onPressed: _report),
                          const SizedBox(height: 10),
                          // With a trip on, the card takes the traffic panel's place: the report button
                          // and the locate row stay.
                          ListenableBuilder(
                            listenable: _trip,
                            builder: (context, _) =>
                                _trip.destination == null
                                ? LayerSheet(layers: _layers, legend: hubLegend(_hubs))
                                : RouteCard(trip: _trip),
                          ),
                        ],
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
  const _LocateRow({required this.location, required this.onLocate, required this.onTransit});

  final LocationState location;
  final VoidCallback onLocate;
  final VoidCallback onTransit;

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
                tooltip: 'Transit near me',
                onPressed: onTransit,
                icon: const Icon(Icons.directions_bus_outlined, size: 22, color: navy),
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

class _ResetChip extends StatelessWidget {
  const _ResetChip({required this.onPressed});

  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return ChipCard(
      padding: EdgeInsets.zero,
      child: TextButton(onPressed: onPressed, child: const Text('Reset to Makati')),
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
