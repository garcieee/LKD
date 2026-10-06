// The map page: a full-bleed Mapbox map pinned on Makati, with floating chips over it.
// Mirrors dashboard/src/map/MapCanvas.tsx and App.tsx.
import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:mapbox_maps_flutter/mapbox_maps_flutter.dart';

import '../config/env.dart';
import '../config/makati.dart';
import '../config/map_styles.dart';
import '../layers/congestion_layer.dart';
import '../state/layers_state.dart';
import '../theme.dart';
import '../widgets/layer_sheet.dart';

// Strip at the bottom kept free of chips for the Mapbox logo and the attribution button.
const _ornamentBand = 40.0;

class MapView extends StatefulWidget {
  const MapView({super.key});

  @override
  State<MapView> createState() => _MapViewState();
}

class _MapViewState extends State<MapView> {
  final _layers = LayersState();
  MapboxMap? _map;
  Timer? _timer;
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
    _layers.addListener(_apply);
    _timer = Timer.periodic(congestionRefresh, (_) {
      if (_layers.congestionOn) _layers.refresh();
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    _layers.dispose();
    super.dispose();
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
    } catch (e) {
      debugPrint('congestion layer: $e'); // a failed refresh must not take the app down
    }
  }

  Future<void> _onMapCreated(MapboxMap map) async {
    _map = map;
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
                const Align(alignment: Alignment.topLeft, child: _Brand()),
                Align(alignment: Alignment.topRight, child: _ResetChip(onPressed: _reset)),
                Align(
                  alignment: Alignment.bottomCenter,
                  child: Padding(
                    padding: const EdgeInsets.only(bottom: _ornamentBand),
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 420),
                      child: LayerSheet(layers: _layers),
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
