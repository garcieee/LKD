// Shared by the layout and screen tests: Roboto's real glyph widths (the test font is about twice as wide, so
// everything overflows at 1x), and stand-ins for the camera, GPS, compass, screen-lock and map plugins, so a whole
// screen can be pumped on the host.
//
// The plugins' platform interfaces are only transitive dependencies, and Mapbox's hosting mode is marked experimental.
// ignore_for_file: depend_on_referenced_packages, experimental_member_use
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:camera_platform_interface/camera_platform_interface.dart';
import 'package:flutter/foundation.dart' show Factory;
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geolocator/geolocator.dart';
import 'package:lakad/api/api_client.dart';
import 'package:lakad/theme.dart';
import 'package:mapbox_maps_flutter_platform_interface/mapbox_maps_flutter_platform_interface_internal.dart' hide Size;
import 'package:sensors_plus/sensors_plus.dart';
import 'package:wakelock_plus/wakelock_plus.dart' show wakelockPlusPlatformInstance;
import 'package:wakelock_plus_platform_interface/wakelock_plus_platform_interface.dart';

// ---- text and screen sizes ----

/// Loads Roboto from the Flutter SDK, for `setUpAll`. Without it every label is drawn in the test font, which is
/// about twice as wide as what a phone shows.
Future<void> loadRoboto() async {
  TestWidgetsFlutterBinding.ensureInitialized();
  final root = Platform.environment['FLUTTER_ROOT'];
  final dir = '$root/bin/cache/artifacts/material_fonts';
  if (!File('$dir/Roboto-Regular.ttf').existsSync()) {
    throw StateError('Roboto not found under FLUTTER_ROOT ($root): run these tests with `flutter test`.');
  }
  Future<ByteData> bytes(String file) async => ByteData.sublistView(await File('$dir/$file').readAsBytes());
  for (final family in ['Roboto', 'serif']) {
    // 'serif' is Android's generic serif on a phone; Roboto is close enough in width.
    await (FontLoader(family)
          ..addFont(bytes('Roboto-Regular.ttf'))
          ..addFont(bytes('Roboto-Medium.ttf'))
          ..addFont(bytes('Roboto-Bold.ttf')))
        .load();
  }
}

/// The app's theme, with Roboto on the button labels too: their style names no family, so the test font would win.
ThemeData testTheme() {
  final theme = origamiTheme();
  ButtonStyle roboto(ButtonStyle style) =>
      style.copyWith(textStyle: WidgetStatePropertyAll(style.textStyle!.resolve({})!.copyWith(fontFamily: 'Roboto')));
  return theme.copyWith(
    textButtonTheme: TextButtonThemeData(style: roboto(theme.textButtonTheme.style!)),
    outlinedButtonTheme: OutlinedButtonThemeData(style: roboto(theme.outlinedButtonTheme.style!)),
  );
}

/// A small and a common Android phone, in logical pixels.
const phones = [Size(320, 640), Size(360, 740)];

/// 1x, and the large-text settings people with low vision use.
const textScales = [1.0, 1.5, 2.0];

/// Pumps the page [build] makes on each of [phones] at each of [textScales], and fails on the first exception: a
/// RenderFlex overflow is one. [after] runs once the page is up (open a sheet, say).
Future<void> fitsEveryPhone(
  WidgetTester tester,
  Widget Function() build, {
  Future<void> Function(WidgetTester tester)? after,
}) async {
  addTearDown(() {
    tester.view.reset();
    tester.platformDispatcher.clearAllTestValues();
  });
  for (final phone in phones) {
    for (final scale in textScales) {
      tester.view.physicalSize = phone;
      tester.view.devicePixelRatio = 1;
      tester.platformDispatcher.textScaleFactorTestValue = scale;
      await tester.pumpWidget(const SizedBox());
      await tester.pumpWidget(MaterialApp(theme: testTheme(), home: build()));
      await tester.pump(const Duration(milliseconds: 100));
      await after?.call(tester);
      expect(tester.takeException(), isNull, reason: '${phone.width.toInt()}x${phone.height.toInt()} at $scale x text');
    }
  }
}

// ---- a trip, as the server would answer it ----

/// The user, in the middle of Makati.
const here = (lat: 14.5547, lng: 121.0244);

/// Where they are going: a name long enough to want two lines.
const destination = Place(
  label: 'Greenbelt 5, Ayala Center, Legazpi Village, Makati, Metro Manila, Philippines',
  lat: 14.553,
  lng: 121.021,
);

/// What the server names a terminal, at its longest.
const terminal = 'MRT3-Ayala/BGC Bus Terminal';
const farTerminal = 'Mandaluyong City Hall Terminal';

/// A walking route from [here] to the [destination], 4.8 km and 65 minutes (it passes [hazards]).
WalkRoute walkRoute(String mode, {List<String> hazards = const [], bool avoids = true}) => WalkRoute.fromJson({
  'mode': mode,
  'distance_m': 4800,
  'duration_s': 3900,
  'geometry': [
    [121.0244, 14.5547],
    [121.021, 14.553],
  ],
  'hazard_ids': hazards,
  'avoids_hazards': avoids,
});

Map<String, dynamic> _leg(String kind, num seconds, String label) => {
  'kind': kind,
  'duration_s': seconds,
  'distance_m': 800,
  'label': label,
  'geometry': [
    [121.0244, 14.5547],
    [121.0230, 14.5540],
    [121.021, 14.553],
  ],
};

/// A way to get there: walk to [terminal], ride [kind] to [farTerminal], walk on. [walk] of [total] seconds is walking.
CommuteOption commuteOption(
  String id, {
  required num total,
  required num walk,
  String kind = 'city_bus',
  bool earliest = false,
}) => CommuteOption.fromJson({
  'id': id,
  'total_s': total,
  'walk_s': walk,
  'tags': [if (earliest) 'earliest'],
  'legs': [
    _leg('walk', walk / 2, 'Walk to $terminal'),
    _leg(kind, total - walk, '$terminal to $farTerminal'),
    _leg('walk', walk / 2, 'Walk from $farTerminal'),
  ],
});

// ---- plugins ----

/// A GPS fix at ([lat], [lng]).
Position fixAt(double lat, double lng, {double accuracy = 8}) => Position(
  latitude: lat,
  longitude: lng,
  timestamp: DateTime.now(),
  accuracy: accuracy,
  altitude: 0,
  altitudeAccuracy: 0,
  heading: 0,
  headingAccuracy: 0,
  speed: 0,
  speedAccuracy: 0,
);

class FakeGeolocator extends GeolocatorPlatform {
  bool serviceOn = true;
  LocationPermission permission = LocationPermission.whileInUse;
  Duration promptTime = Duration.zero; // how long the permission prompt stays up
  int prompts = 0, streamsOpened = 0;
  final _streams = <StreamController<Position>>[];

  /// Position streams somebody still listens to.
  int get listening => _streams.where((c) => c.hasListener).length;

  void emit(Position fix) {
    for (final c in _streams) {
      if (c.hasListener) c.add(fix);
    }
  }

  @override
  Future<bool> isLocationServiceEnabled() async => serviceOn;

  @override
  Future<LocationPermission> checkPermission() async => permission;

  @override
  Future<LocationPermission> requestPermission() async {
    prompts++;
    await Future<void>.delayed(promptTime);
    return permission;
  }

  @override
  Stream<Position> getPositionStream({LocationSettings? locationSettings}) {
    streamsOpened++;
    final c = StreamController<Position>.broadcast();
    _streams.add(c);
    return c.stream;
  }

  @override
  Future<bool> openAppSettings() async => true;

  @override
  Future<bool> openLocationSettings() async => true;
}

class FakeSensors extends SensorsPlatform {
  final _quiet = StreamController<AccelerometerEvent>.broadcast();
  final _quietMag = StreamController<MagnetometerEvent>.broadcast();

  @override
  Stream<AccelerometerEvent> accelerometerEventStream({Duration samplingPeriod = SensorInterval.normalInterval}) =>
      _quiet.stream;

  @override
  Stream<MagnetometerEvent> magnetometerEventStream({Duration samplingPeriod = SensorInterval.normalInterval}) =>
      _quietMag.stream;
}

/// Records what the app asked of the screen lock.
class FakeWakelock extends WakelockPlusPlatformInterface {
  final calls = <bool>[];

  bool get on => calls.isNotEmpty && calls.last;

  @override
  Future<void> toggle({required bool enable}) async => calls.add(enable);

  @override
  Future<bool> get enabled async => on;
}

/// The map as a blank box: the page's chips and cards draw over it as usual, and nothing reaches the native map.
base class FakeMapbox extends MapboxMapsFlutterPlatform {
  @override
  Widget buildView({
    required String styleUri,
    PlatformMapCreatedCallback? onMapCreated,
    ViewportState? viewport,
    ViewportTransition? viewportTransition,
    void Function(bool)? viewportTransitionCompletion,
    void Function(MapEvent)? onMapEvent,
    MapOptions? mapOptions,
    bool? textureView,
    required AndroidPlatformViewHostingMode androidHostingMode,
    Set<Factory<OneSequenceGestureRecognizer>>? gestureRecognizers,
    bool? isOpaque = true,
  }) => const SizedBox.expand();

  @override
  dynamic noSuchMethod(Invocation invocation) => throw UnimplementedError('${invocation.memberName}');
}

/// A back camera that records what it was asked, and can be made slow or broken.
class FakeCamera extends CameraPlatform {
  final log = <String>[];
  Object? initError; // the camera does not open
  Completer<void>? startGate; // startVideoRecording waits for this
  Object? startError;
  final _ready = <int, StreamController<CameraInitializedEvent>>{};
  var _next = 1;

  // What a shutter press hands back: a real 1x1 JPEG (the contract test's), and a clip that starts like an MP4.
  final photo = base64Decode(
    '/9j/2wBDAAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQH/wAALCAAB'
    'AAEBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAAAP/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AP//Z',
  );
  final clip = Uint8List.fromList([0, 0, 0, 0x18, ...'ftypmp42'.codeUnits, ...List.filled(2048, 0)]);

  @override
  Future<List<CameraDescription>> availableCameras() async => const [
    CameraDescription(name: 'back', lensDirection: CameraLensDirection.back, sensorOrientation: 90),
  ];

  @override
  Future<int> createCameraWithSettings(CameraDescription description, MediaSettings settings) async {
    log.add('create');
    return _next++;
  }

  @override
  Future<void> initializeCamera(int cameraId, {ImageFormatGroup imageFormatGroup = ImageFormatGroup.unknown}) async {
    log.add('initialize');
    if (initError != null) throw initError!;
    _ready
        .putIfAbsent(cameraId, StreamController.broadcast)
        .add(CameraInitializedEvent(cameraId, 1280, 720, ExposureMode.auto, false, FocusMode.auto, false));
  }

  @override
  Stream<CameraInitializedEvent> onCameraInitialized(int cameraId) =>
      _ready.putIfAbsent(cameraId, StreamController.broadcast).stream;

  // These never end or fire, like the real ones.
  @override
  Stream<CameraErrorEvent> onCameraError(int cameraId) => StreamController<CameraErrorEvent>.broadcast().stream;

  @override
  Stream<DeviceOrientationChangedEvent> onDeviceOrientationChanged() =>
      StreamController<DeviceOrientationChangedEvent>.broadcast().stream;

  @override
  Widget buildPreview(int cameraId) => const ColoredBox(color: Color(0xFF445566));

  @override
  Future<XFile> takePicture(int cameraId) async {
    log.add('takePicture');
    return XFile.fromData(photo, path: 'photo.jpg');
  }

  @override
  Future<void> startVideoRecording(int cameraId, {Duration? maxVideoDuration}) async {
    log.add('startVideo');
    await startGate?.future;
    if (startError != null) throw startError!;
  }

  @override
  Future<void> startVideoCapturing(VideoCaptureOptions options) => startVideoRecording(options.cameraId);

  @override
  Future<XFile> stopVideoRecording(int cameraId) async {
    log.add('stopVideo');
    return XFile.fromData(clip, path: 'sos.mp4');
  }

  @override
  Future<void> dispose(int cameraId) async => log.add('dispose');
}

/// Installs a fake for every plugin the map page and the report screen use, and keeps the phone's haptics quiet.
/// Call from a test or `setUp`.
class Plugins {
  Plugins() {
    GeolocatorPlatform.instance = geo;
    SensorsPlatform.instance = sensors;
    wakelockPlusPlatformInstance = wakelock; // the plugin reads its platform once, so setting `instance` is too late
    MapboxMapsFlutterPlatform.instance = mapbox;
    CameraPlatform.instance = camera;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      SystemChannels.platform,
      (call) async => null,
    );
  }

  final geo = FakeGeolocator();
  final sensors = FakeSensors();
  final wakelock = FakeWakelock();
  final mapbox = FakeMapbox();
  final camera = FakeCamera();
}

/// The app's ApiClient leaves a timer running for each call until its deadline; let them all run out.
Future<void> leave(WidgetTester tester) async {
  await tester.pumpWidget(const SizedBox());
  await tester.pump(const Duration(seconds: 100));
}
