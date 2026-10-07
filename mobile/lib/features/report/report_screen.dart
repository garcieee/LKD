// Report a hazard: point the back camera at it, snap, tag, send. The live view carries a
// location-based AR overlay (no ARCore): a reticle, GPS accuracy and compass heading, and chips for
// reports already filed nearby, placed by bearing and distance, so people see a hazard is reported
// before they file it twice. The shot springs into a corner thumbnail, iPhone-screenshot style, then
// opens into the tag sheet. Pops with the new Report once the server has it.
//
// SOS: hold the shutter instead of tapping it. It records a silent video while the screen slowly reddens,
// arrows point up to a cancel target, and letting go anywhere else sends the clip to the city at once as an
// urgent ticket (sos_hold.dart has the rules, sos_overlay.dart the look). The clip is kept in memory until
// the server has it, so a bad connection offers a retry instead of losing it.
import 'dart:async';
import 'dart:io';
import 'dart:math' as math;

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:geolocator/geolocator.dart';
import 'package:sensors_plus/sensors_plus.dart';

import '../../api/api_client.dart';
import '../../layers/reports_layer.dart';
import '../../theme.dart';
import 'ar_math.dart';
import 'category_picker.dart';
import 'sos_hold.dart';
import 'sos_overlay.dart';

class ReportScreen extends StatefulWidget {
  const ReportScreen({super.key});

  @override
  State<ReportScreen> createState() => _ReportScreenState();
}

enum _Gps { starting, ok, off, denied, blocked }

class _ReportScreenState extends State<ReportScreen>
    with WidgetsBindingObserver, TickerProviderStateMixin {
  CameraController? _camera;
  CameraException? _cameraError;
  bool _cameraStarting = false;

  _Gps _gps = _Gps.starting;
  Position? _fix;
  StreamSubscription<Position>? _fixes;

  // Where the back camera points, 0..360 from magnetic north (a degree or so off true north here,
  // small next to the field of view). Null without a compass, or with the camera near vertical.
  final _heading = ValueNotifier<double?>(null);
  late final List<StreamSubscription<Object>> _sensors;
  final _gravity = [0.0, 0.0, 0.0], _field = [0.0, 0.0, 0.0]; // smoothed readings, device axes

  List<Report> _filed = const []; // reports already filed, fixed ones left out

  // The shot: a flash, then it springs into a thumbnail, then the tag sheet opens.
  bool _shooting = false;
  ({Uint8List photo, Position fix, double? heading})? _shot;
  late final _snap = AnimationController(vsync: this, duration: const Duration(milliseconds: 550));
  Timer? _autoOpen;
  bool _tagging = false;

  // SOS: recording while the shutter is held.
  bool _sos = false;
  CameraController? _sosCamera; // the one recording, kept so letting go can stop it even if _camera is freed
  Future<void>? _sosStarting; // startVideoRecording, in flight: a very short hold may end before it resolves
  Position? _sosFix; // where the hold began
  double? _sosHeading;
  final _clock = Stopwatch();
  Timer? _ticker;
  final _recorded = ValueNotifier<Duration>(Duration.zero);
  final _slide = ValueNotifier<double>(0); // 0..1: how far the finger has slid toward cancel
  late final _ramp = AnimationController(vsync: this, duration: sosVignetteRamp); // the red creeping in
  // Recorded and not yet delivered. Kept until the server has it (or the user discards it).
  ({Uint8List video, Position fix, double? heading})? _sosClip;
  bool _sosSending = false;
  double? _sosProgress; // share of the video uploaded; null once the server has all of it
  String? _sosError;
  bool _sosSent = false;

  // The tag sheet.
  String? _category;
  final _note = TextEditingController();
  bool _sending = false;
  double? _progress; // share of the photo uploaded; null once the server has all of it
  String? _error;
  bool _sent = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _sensors = [
      accelerometerEventStream(samplingPeriod: SensorInterval.gameInterval).listen(
        (e) => _smooth(_gravity, e.x, e.y, e.z),
        onError: (_) {}, // NO_SENSOR: no heading, the readout says so
      ),
      magnetometerEventStream(samplingPeriod: SensorInterval.gameInterval).listen((e) {
        _smooth(_field, e.x, e.y, e.z);
        _heading.value = cameraHeading(_gravity[0], _gravity[1], _gravity[2], _field[0], _field[1], _field[2]);
      }, onError: (_) {}),
    ];
    _start();
  }

  // ponytail: raw accelerometer and magnetometer through a fixed low-pass, no gyroscope, so the
  // heading lags ~0.1 s and can wobble a degree or two. Tune the 0.2 on a device; if the chips still
  // swim, read Android's fused rotation-vector sensor through a platform channel instead.
  static void _smooth(List<double> v, double x, double y, double z) {
    v[0] += (x - v[0]) * 0.2;
    v[1] += (y - v[1]) * 0.2;
    v[2] += (z - v[2]) * 0.2;
  }

  // One permission prompt at a time: Android drops a request made while another one shows.
  Future<void> _start() async {
    await _startCamera();
    await _startGps();
    try {
      final all = await api.reports();
      if (mounted) setState(() => _filed = [for (final r in all) if (r.status != 'fixed' && r.status != 'rejected') r]);
    } catch (e) {
      debugPrint('nearby reports: $e'); // only a hint: reporting works without them
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _camera?.dispose();
    _fixes?.cancel();
    for (final s in _sensors) {
      s.cancel();
    }
    _heading.dispose();
    _snap.dispose();
    _autoOpen?.cancel();
    _ticker?.cancel();
    _ramp.dispose();
    _slide.dispose();
    _recorded.dispose();
    _note.dispose();
    // Dark bar icons again for the map (main.dart): this screen's AnnotatedRegion leaves with it.
    SystemChrome.setSystemUIOverlayStyle(
      const SystemUiOverlayStyle(
        statusBarIconBrightness: Brightness.dark,
        systemNavigationBarIconBrightness: Brightness.dark,
      ),
    );
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // Free the camera in the background, and look again on return: the user may have allowed a
    // permission or switched location on. Not on `inactive`: permission dialogs cause that.
    if (state == AppLifecycleState.hidden) {
      final camera = _camera;
      if (camera == null) return;
      if (_sos) {
        // A call or the lock key in the middle of an SOS is not a cancel: finish as if the finger had lifted
        // (what was recorded still goes), then free the camera.
        _sosFinish(cancel: false).whenComplete(() {
          if (mounted && _camera == camera) setState(() => _camera = null);
          camera.dispose();
          // The upload outlasted the call and they are back: nothing else would bring the camera up again.
          if (mounted && WidgetsBinding.instance.lifecycleState == AppLifecycleState.resumed) _startCamera();
        });
        return;
      }
      setState(() => _camera = null);
      camera.dispose();
    } else if (state == AppLifecycleState.resumed) {
      _resume();
    }
  }

  Future<void> _resume() async {
    await _startCamera();
    if (_gps != _Gps.ok) await _startGps();
  }

  Future<void> _startCamera() async {
    if (_camera != null || _cameraStarting) return;
    _cameraStarting = true;
    CameraController? camera;
    try {
      final cameras = await availableCameras();
      final back =
          cameras.where((c) => c.lensDirection == CameraLensDirection.back).firstOrNull ?? cameras.firstOrNull;
      if (back == null) throw CameraException('NoCamera', 'This phone has no camera.');
      // JPEG stills either way on CameraX: the format group only sets the image-stream format. No audio: an SOS
      // is video only (the manifest strips the microphone permission), so no one's conversation is recorded.
      // 2.5 Mbit/s keeps a 30 s clip under 10 MB for the upload.
      camera = CameraController(
        back,
        ResolutionPreset.high,
        enableAudio: false,
        videoBitrate: 2500000,
        imageFormatGroup: ImageFormatGroup.jpeg,
      );
      await camera.initialize(); // asks for the camera permission the first time
      if (!mounted) {
        await camera.dispose();
        return;
      }
      setState(() {
        _camera = camera;
        _cameraError = null;
      });
    } on CameraException catch (e) {
      await camera?.dispose();
      if (mounted) setState(() => _cameraError = e);
    } finally {
      _cameraStarting = false;
    }
  }

  Future<void> _startGps() async {
    await _fixes?.cancel();
    _fixes = null;
    var gps = _Gps.off;
    if (await Geolocator.isLocationServiceEnabled()) {
      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) permission = await Geolocator.requestPermission();
      gps = switch (permission) {
        LocationPermission.whileInUse || LocationPermission.always => _Gps.ok,
        LocationPermission.deniedForever => _Gps.blocked,
        _ => _Gps.denied,
      };
    }
    if (!mounted) return;
    setState(() => _gps = gps);
    if (gps != _Gps.ok) return;
    _fixes =
        Geolocator.getPositionStream(
          locationSettings: AndroidSettings(
            accuracy: LocationAccuracy.best,
            intervalDuration: const Duration(seconds: 1), // the default is 5 s
          ),
        ).listen(
          (fix) => setState(() => _fix = fix),
          onError: (Object e) => setState(() {
            _fix = null;
            _gps = e is LocationServiceDisabledException ? _Gps.off : _Gps.denied;
          }),
        );
  }

  // The server rejects a report from outside Makati, so the shutter waits for a fix inside it.
  bool get _canShoot {
    final fix = _fix;
    return _camera != null &&
        !_shooting &&
        !_sos &&
        _sosClip == null &&
        _shot == null &&
        fix != null &&
        inMakati(fix.latitude, fix.longitude);
  }

  Future<void> _shoot() async {
    final camera = _camera!, fix = _fix!, heading = _heading.value;
    final reduceMotion = MediaQuery.disableAnimationsOf(context);
    setState(() => _shooting = true);
    try {
      final file = await camera.takePicture();
      final photo = await file.readAsBytes();
      File(file.path).delete().ignore(); // the server keeps the copy that matters
      if (!mounted) return;
      setState(() => _shot = (photo: photo, fix: fix, heading: heading));
      if (reduceMotion) {
        _snap.value = 1; // no flash, no spring: straight to the sheet
        _openSheet();
      } else {
        _snap.forward(from: 0);
        _autoOpen = Timer(_snap.duration! + const Duration(milliseconds: 700), _openSheet);
      }
    } on CameraException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('No photo: ${e.description ?? e.code}')));
      }
    } finally {
      if (mounted) setState(() => _shooting = false);
    }
  }

  // ---- SOS: hold the shutter to record, slide up to cancel, let go to send ----

  void _say(String text) {
    if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  // The hold is long enough to be an SOS: record, and let the screen redden.
  Future<void> _sosStart() async {
    if (!_canShoot) return; // the GPS fix may have gone since the finger went down
    final camera = _camera!;
    HapticFeedback.heavyImpact();
    _sosCamera = camera;
    _sosFix = _fix;
    _sosHeading = _heading.value;
    _slide.value = 0;
    _recorded.value = Duration.zero;
    _clock
      ..reset()
      ..start();
    if (MediaQuery.disableAnimationsOf(context)) {
      _ramp.value = 0.6; // no creep for people who turned animations off: a steady red
    } else {
      _ramp.forward(from: 0);
    }
    setState(() => _sos = true);
    _ticker = Timer.periodic(const Duration(milliseconds: 200), (_) {
      _recorded.value = _clock.elapsed;
      if (_clock.elapsed >= sosMaxRecording) _sosFinish(cancel: false); // the limit: sent as if let go
    });
    _sosStarting = camera.startVideoRecording();
    try {
      await _sosStarting;
    } on CameraException catch (e) {
      _sosStopped();
      _say('SOS did not start: ${e.description ?? e.code}');
    }
  }

  // Back to the plain camera: the clock stopped, the red fading out.
  void _sosStopped() {
    _ticker?.cancel();
    _ticker = null;
    _clock.stop();
    _sosCamera = null;
    _sosStarting = null;
    if (!mounted) return;
    setState(() => _sos = false);
    _ramp.animateBack(0, duration: const Duration(milliseconds: 250));
    _slide.value = 0;
  }

  void _sosMove(double dy) {
    final onTarget = _slide.value >= 1;
    _slide.value = cancelProgress(dy);
    if (!onTarget && _slide.value >= 1) HapticFeedback.selectionClick(); // on the X: letting go cancels
  }

  // The finger lifted, on the X or not.
  Future<void> _sosEnd(double dy) => _sosFinish(cancel: inCancelZone(dy));

  // Everything but an explicit slide to the X sends: lifting the finger, the 30 s limit, the system taking the
  // touch away, the app leaving the screen. Only a clip under a second is dropped, with a hint.
  Future<void> _sosFinish({required bool cancel}) async {
    final camera = _sosCamera;
    if (!_sos || camera == null) return; // already finishing
    final recorded = _clock.elapsed, fix = _sosFix, heading = _sosHeading, starting = _sosStarting;
    _sosStopped();
    XFile? file;
    try {
      await starting; // a very short hold can end before the recorder is up
      if (camera.value.isRecordingVideo) file = await camera.stopVideoRecording();
    } on CameraException catch (e) {
      debugPrint('SOS stop: ${e.code} ${e.description}');
    }
    final outcome = sosOutcome(recorded: recorded, cancelZone: cancel);
    if (outcome != SosOutcome.send || file == null || fix == null) {
      if (file != null) File(file.path).delete().ignore(); // thrown away: no copy is kept on the phone
      HapticFeedback.mediumImpact();
      _say(switch (outcome) {
        SosOutcome.cancel => 'SOS cancelled. Nothing was sent.',
        SosOutcome.tooShort => 'Keep holding to send an SOS.',
        SosOutcome.send => 'The SOS video could not be saved. Hold the button to try again.',
      });
      return;
    }
    final video = await file.readAsBytes();
    File(file.path).delete().ignore(); // the server keeps the copy that matters; the bytes stay here until it has them
    if (!mounted) return;
    setState(() => _sosClip = (video: video, fix: fix, heading: heading));
    await _sosSend();
  }

  Future<void> _sosSend() async {
    final clip = _sosClip!;
    setState(() {
      _sosSending = true;
      _sosProgress = 0;
      _sosError = null;
    });
    try {
      final report = await api.sendSos(
        video: clip.video,
        lat: clip.fix.latitude,
        lng: clip.fix.longitude,
        heading: clip.heading,
        onProgress: (sent) {
          if (mounted) setState(() => _sosProgress = sent < 1 ? sent : null);
        },
      );
      if (!mounted) return;
      HapticFeedback.heavyImpact();
      setState(() => _sosSent = true);
      await Future<void>.delayed(const Duration(milliseconds: 1500)); // let the tick show
      if (mounted) Navigator.pop(context, report);
    } catch (e) {
      if (mounted) setState(() => _sosError = '$e'); // an ApiException prints as its message
    } finally {
      if (mounted) setState(() => _sosSending = false);
    }
  }

  void _sosDiscard() => setState(() {
    _sosClip = null;
    _sosError = null;
  });

  void _openSheet() {
    _autoOpen?.cancel();
    if (mounted && _shot != null) setState(() => _tagging = true);
  }

  void _retake() {
    _autoOpen?.cancel();
    _snap.reset();
    setState(() {
      _shot = null;
      _tagging = false;
      _error = null;
    });
  }

  Future<void> _send() async {
    final shot = _shot!;
    FocusManager.instance.primaryFocus?.unfocus(); // the keyboard away, the button in view
    setState(() {
      _sending = true;
      _progress = 0;
      _error = null;
    });
    try {
      final report = await api.sendReport(
        photo: shot.photo,
        category: _category!,
        lat: shot.fix.latitude,
        lng: shot.fix.longitude,
        heading: shot.heading,
        note: _note.text.trim(),
        onProgress: (sent) {
          if (mounted) setState(() => _progress = sent < 1 ? sent : null);
        },
      );
      if (!mounted) return;
      setState(() => _sent = true);
      await Future<void>.delayed(const Duration(milliseconds: 800)); // let the tick show
      if (mounted) Navigator.pop(context, report);
    } catch (e) {
      if (mounted) setState(() => _error = '$e'); // an ApiException prints as its message
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final camera = _camera;
    final motion = MediaQuery.disableAnimationsOf(context) ? Duration.zero : const Duration(milliseconds: 250);
    return PopScope<Object?>(
      // Not while an SOS records or waits to be delivered: leaving would lose it.
      canPop: _shot == null && _sosClip == null && !_sos,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop && !_sending && !_sent && _sosClip == null && !_sos) _retake(); // back drops the shot, not the screen
      },
      child: AnnotatedRegion<SystemUiOverlayStyle>(
        value: SystemUiOverlayStyle(
          statusBarColor: Colors.transparent,
          statusBarIconBrightness: Brightness.light, // over the camera
          systemNavigationBarColor: Colors.transparent,
          systemNavigationBarIconBrightness: _tagging ? Brightness.dark : Brightness.light,
          systemNavigationBarContrastEnforced: false,
        ),
        child: Scaffold(
          backgroundColor: Colors.black,
          resizeToAvoidBottomInset: false, // the sheet rises over the keyboard by itself
          body: Stack(
            fit: StackFit.expand,
            children: [
              if (camera != null) _Preview(camera) else _NoCamera(error: _cameraError, onRetry: _startCamera),
              SosVignette(ramp: _ramp, cancel: _slide),
              if (!_tagging) ...[if (!_sos) ...[const _Reticle(), _nearbyChips()], _controls()],
              if (_shot != null) ...[_scrim(motion), _shotCard(motion), _sheet(motion)],
              if (_sosClip != null) _sosCard(),
            ],
          ),
        ),
      ),
    );
  }

  // Filed reports within nearbyM, placed across the screen by bearing when inside the camera's view,
  // lower and bigger the closer they are.
  Widget _nearbyChips() => ValueListenableBuilder<double?>(
    valueListenable: _heading,
    builder: (context, heading, _) {
      final fix = _fix;
      if (fix == null || heading == null) return const SizedBox.shrink();
      final size = MediaQuery.sizeOf(context);
      final chips = <(double, Widget)>[];
      for (final r in _filed) {
        final d = distanceM(fix.latitude, fix.longitude, r.lat, r.lng);
        final rel = relativeDeg(bearingDeg(fix.latitude, fix.longitude, r.lat, r.lng), heading);
        final x = d > nearbyM ? null : screenX(rel, size.width);
        if (x == null) continue;
        final far = d / nearbyM; // 0 underfoot .. 1 at the edge of the circle
        final chip = Positioned(
          left: x,
          top: size.height * (0.72 - 0.3 * far),
          child: FractionalTranslation(
            translation: const Offset(-0.5, -0.5),
            child: Transform.scale(scale: 1 - 0.35 * far, child: _NearbyChip(r, d)),
          ),
        );
        chips.add((d, chip));
      }
      chips.sort((a, b) => b.$1.compareTo(a.$1)); // far ones first, so near ones draw on top
      return IgnorePointer(child: Stack(children: [for (final (_, chip) in chips) chip]));
    },
  );

  Widget _controls() {
    return SafeArea(
      minimum: const EdgeInsets.all(14),
      child: Stack(
        children: [
          if (!_sos)
            Align(
              alignment: Alignment.topLeft,
              child: IconButton.filled(
                onPressed: () => Navigator.maybePop(context),
                tooltip: 'Close',
                style: IconButton.styleFrom(
                  backgroundColor: const Color(0x66000000),
                  foregroundColor: Colors.white,
                ),
                icon: const Icon(Icons.close),
              ),
            ),
          Align(
            alignment: Alignment.topCenter,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 52), // clear of the close button
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (_sos) ...[SosBanner(cancel: _slide, recorded: _recorded), const SizedBox(height: 8)],
                  _readout(),
                  if (_problem() case final problem?) ...[const SizedBox(height: 8), problem],
                ],
              ),
            ),
          ),
          if (_shot == null)
            Align(
              alignment: Alignment.bottomCenter,
              // The shutter at the bottom; while an SOS records, the arrows and the X above it, in the same box.
              child: SizedBox(
                width: 240,
                height: sosGuideHeight,
                child: Stack(
                  alignment: Alignment.bottomCenter,
                  children: [
                    if (_sos)
                      Positioned.fill(
                        child: SosGuide(cancel: _slide, reduceMotion: MediaQuery.disableAnimationsOf(context)),
                      ),
                    ValueListenableBuilder<double>(
                      valueListenable: _slide,
                      builder: (context, slid, _) => SosShutter(
                        enabled: _canShoot,
                        busy: _shooting,
                        armed: _sos,
                        cancelling: _sos && slid >= 1,
                        onTap: () {
                          if (_canShoot) _shoot();
                        },
                        onSosStart: _sosStart,
                        onSosMove: _sosMove,
                        onSosEnd: _sosEnd,
                        onSosAbort: () => _sosFinish(cancel: false),
                      ),
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }

  // "±8 m · NE 42°", and how many reports are already filed nearby.
  Widget _readout() => ValueListenableBuilder<double?>(
    valueListenable: _heading,
    builder: (context, heading, _) {
      final fix = _fix;
      final nearby = fix == null
          ? 0
          : _filed.where((r) => distanceM(fix.latitude, fix.longitude, r.lat, r.lng) <= nearbyM).length;
      return ChipCard(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              [
                fix == null ? 'Finding GPS…' : '±${fix.accuracy.round()} m',
                heading == null ? 'no compass' : '${compassPoint(heading)} ${heading.round() % 360}°',
              ].join(' · '),
              style: const TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w600,
                fontFeatures: [FontFeature.tabularFigures()],
              ),
            ),
            if (nearby > 0)
              Text(
                '$nearby already reported within ${nearbyM.round()} m',
                style: const TextStyle(fontSize: 11, color: muted),
              ),
          ],
        ),
      );
    },
  );

  // Why the shutter is off, and what to do about it.
  Widget? _problem() {
    final fix = _fix;
    final (String, String?, VoidCallback?)? problem = switch (_gps) {
      _Gps.off => ('Location is off.', 'Turn on', Geolocator.openLocationSettings),
      _Gps.denied => ('Lakad needs your location to pin the report.', 'Allow', _startGps),
      _Gps.blocked => ('Location is blocked for Lakad.', 'Settings', Geolocator.openAppSettings),
      _ when fix != null && !inMakati(fix.latitude, fix.longitude) => (
        'You are outside Makati. Reports are for Makati streets only.',
        null,
        null,
      ),
      _ => null,
    };
    if (problem == null) return null;
    final (text, action, onPressed) = problem;
    return ChipCard(
      padding: EdgeInsets.fromLTRB(12, 4, action == null ? 12 : 4, 4),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Flexible(
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 6),
              child: Text(text, style: const TextStyle(fontSize: 12, color: warn)),
            ),
          ),
          if (action != null) TextButton(onPressed: onPressed, child: Text(action)),
        ],
      ),
    );
  }

  // An SOS on its way: sending, sent, or not sent with the clip still held for another try.
  Widget _sosCard() {
    final error = _sosError;
    final icon = _sosSent ? Icons.check_circle : (error != null ? Icons.error_outline : Icons.sos);
    final title = _sosSent ? 'SOS sent' : (error != null ? 'SOS not sent' : 'Sending SOS');
    return Positioned.fill(
      child: ColoredBox(
        color: const Color(0xCC000000),
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(28),
            child: Semantics(
              liveRegion: true,
              child: ChipCard(
                padding: const EdgeInsets.fromLTRB(22, 22, 22, 18),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    if (_sosSending && !_sosSent)
                      SizedBox.square(
                        dimension: 44,
                        child: CircularProgressIndicator(value: _sosProgress, strokeWidth: 4, color: sosRed),
                      )
                    else
                      Icon(icon, color: sosRed, size: 44),
                    const SizedBox(height: 12),
                    Text(title, style: const TextStyle(fontFamily: serif, fontSize: 22, fontWeight: FontWeight.w500)),
                    const SizedBox(height: 6),
                    Text(
                      _sosSent
                          ? 'The city has your video and your location.'
                          : error ??
                                (_sosProgress == null ? 'Saving…' : 'Uploading ${(_sosProgress! * 100).round()}%'),
                      textAlign: TextAlign.center,
                      style: TextStyle(fontSize: 13, color: error != null ? warn : muted),
                    ),
                    if (error != null) ...[
                      const SizedBox(height: 14),
                      FilledButton(
                        onPressed: _sosSending ? null : _sosSend,
                        style: FilledButton.styleFrom(backgroundColor: sosRed),
                        child: const Text('Try again'),
                      ),
                      TextButton(onPressed: _sosSending ? null : _sosDiscard, child: const Text('Discard the video')),
                    ],
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _scrim(Duration motion) => IgnorePointer(
    child: AnimatedOpacity(
      opacity: _tagging ? 1 : 0,
      duration: motion,
      child: const ColoredBox(color: Color(0x99000000)),
    ),
  );

  // The shot fills the screen under a white flash, then springs into a thumbnail card at the bottom
  // left (easeOutBack overshoots, then settles). A tap on it, or a short wait, opens the sheet.
  Widget _shotCard(Duration motion) {
    final photo = _shot!.photo;
    final size = MediaQuery.sizeOf(context);
    final pad = MediaQuery.paddingOf(context);
    const width = 76.0;
    final height = width * size.height / size.width; // the screen's shape, so the crop holds still
    final thumb = Rect.fromLTWH(
      math.max(pad.left, 14.0) + 2,
      size.height - math.max(pad.bottom, 14.0) - height,
      width,
      height,
    );
    return AnimatedBuilder(
      animation: _snap,
      builder: (context, _) {
        final t = _snap.value;
        final card = const Interval(0.27, 1, curve: Curves.easeOutBack).transform(t);
        final k = card.clamp(0.0, 1.0); // how far it has become a card
        final radius = BorderRadius.circular(14 * k);
        return Stack(
          children: [
            Positioned.fromRect(
              rect: Rect.lerp(Offset.zero & size, thumb, card)!,
              child: AnimatedOpacity(
                opacity: _tagging ? 0 : 1,
                duration: motion,
                child: AnimatedScale(
                  scale: _tagging ? 1.25 : 1,
                  duration: motion,
                  child: Semantics(
                    button: true,
                    label: 'Photo taken. Tag it',
                    child: GestureDetector(
                      onTap: _openSheet,
                      child: Container(
                        decoration: BoxDecoration(
                          borderRadius: radius,
                          boxShadow: [
                            BoxShadow(color: Colors.black.withValues(alpha: 0.4 * k), blurRadius: 18),
                          ],
                        ),
                        foregroundDecoration: BoxDecoration(
                          borderRadius: radius,
                          border: Border.all(color: Colors.white.withValues(alpha: k), width: 3),
                        ),
                        child: ClipRRect(
                          borderRadius: radius,
                          child: Image.memory(photo, fit: BoxFit.cover, gaplessPlayback: true),
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ),
            if (t < 0.27)
              Positioned.fill(
                child: IgnorePointer(
                  child: ColoredBox(color: Colors.white.withValues(alpha: 1 - t / 0.27)),
                ),
              ),
          ],
        );
      },
    );
  }

  Widget _sheet(Duration motion) {
    final shot = _shot!;
    final size = MediaQuery.sizeOf(context);
    final pad = MediaQuery.paddingOf(context);
    final keyboard = MediaQuery.viewInsetsOf(context).bottom;
    return Positioned(
      left: 0,
      right: 0,
      bottom: keyboard,
      child: AnimatedSlide(
        offset: _tagging ? Offset.zero : const Offset(0, 1.1),
        duration: motion,
        curve: Curves.easeOutCubic,
        child: Material(
          color: Colors.white,
          shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: radiusSheet)),
          clipBehavior: Clip.antiAlias,
          child: ConstrainedBox(
            constraints: BoxConstraints(maxHeight: size.height - keyboard - pad.top - 8),
            // The form scrolls; the Send button stays under it, in view, on a short phone or with the keyboard up.
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Flexible(
                  child: SingleChildScrollView(
                    padding: const EdgeInsets.fromLTRB(20, 18, 20, 0),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Row(
                          children: [
                            const Expanded(
                              child: Text(
                                'New report',
                                style: TextStyle(fontFamily: serif, fontSize: 22, fontWeight: FontWeight.w500),
                              ),
                            ),
                            TextButton.icon(
                              onPressed: _sending || _sent ? null : _retake,
                              icon: const Icon(Icons.refresh, size: 16),
                              label: const Text('Retake'),
                            ),
                          ],
                        ),
                        const SizedBox(height: 12),
                        ClipRRect(
                          borderRadius: radiusChip,
                          child: Image.memory(
                            shot.photo,
                            height: 190,
                            fit: BoxFit.cover,
                            gaplessPlayback: true,
                            semanticLabel: 'The photo to send',
                          ),
                        ),
                        const SizedBox(height: 16),
                        const Text('What is it?', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
                        const SizedBox(height: 8),
                        CategoryPicker(value: _category, onChanged: (c) => setState(() => _category = c)),
                        const SizedBox(height: 16),
                        TextField(
                          controller: _note,
                          maxLength: 280,
                          minLines: 1,
                          maxLines: 4,
                          enabled: !_sending && !_sent,
                          textCapitalization: TextCapitalization.sentences,
                          decoration: const InputDecoration(
                            labelText: 'Note (optional)',
                            hintText: 'e.g. deep, by the jeepney stop',
                            border: OutlineInputBorder(borderRadius: radiusButton),
                          ),
                        ),
                        Row(
                          children: [
                            const Icon(Icons.place_outlined, size: 16, color: muted),
                            const SizedBox(width: 6),
                            Expanded(
                              child: Text(
                                _where(shot.fix, shot.heading),
                                style: const TextStyle(fontSize: 12, color: muted),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
                Padding(
                  padding: EdgeInsets.fromLTRB(20, 14, 20, 16 + pad.bottom),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      if (_error case final error?)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 10),
                          child: Text(error, style: const TextStyle(fontSize: 12, color: warn)),
                        ),
                      SizedBox(height: 48, child: _sendButton(motion)),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  // Send report -> a ring filling with the upload, then spinning while the server saves it -> a tick.
  Widget _sendButton(Duration motion) {
    final busy = _sending || _sent;
    return FilledButton(
      onPressed: _category == null || busy ? null : _send,
      // While busy it stays navy: disabled, but not greyed out.
      style: busy
          ? FilledButton.styleFrom(disabledBackgroundColor: navy, disabledForegroundColor: paper)
          : null,
      child: AnimatedSwitcher(
        duration: motion,
        transitionBuilder: (child, animation) => ScaleTransition(scale: animation, child: child),
        child: _sent
            ? const Row(
                key: ValueKey('sent'),
                mainAxisSize: MainAxisSize.min,
                children: [Icon(Icons.check_circle, size: 20), SizedBox(width: 8), Text('Sent')],
              )
            : _sending
            ? Row(
                key: const ValueKey('sending'),
                mainAxisSize: MainAxisSize.min,
                children: [
                  SizedBox.square(
                    dimension: 18,
                    child: CircularProgressIndicator(value: _progress, strokeWidth: 2.5, color: paper),
                  ),
                  const SizedBox(width: 10),
                  Text(_progress == null ? 'Saving…' : 'Uploading ${(_progress! * 100).round()}%'),
                ],
              )
            : const Text('Send report', key: ValueKey('send')),
      ),
    );
  }

  String _where(Position fix, double? heading) => [
    '${fix.latitude.toStringAsFixed(5)}, ${fix.longitude.toStringAsFixed(5)}',
    '±${fix.accuracy.round()} m',
    if (heading != null) 'facing ${compassPoint(heading)} ${heading.round() % 360}°',
  ].join(' · ');
}

class _Preview extends StatelessWidget {
  const _Preview(this.camera);

  final CameraController camera;

  @override
  Widget build(BuildContext context) {
    // CameraPreview keeps the camera's shape: scale it up to cover the screen and crop the rest.
    final size = camera.value.previewSize!; // landscape, e.g. 1280x720
    final portrait = MediaQuery.orientationOf(context) == Orientation.portrait;
    return FittedBox(
      fit: BoxFit.cover,
      clipBehavior: Clip.hardEdge,
      child: SizedBox(
        width: portrait ? size.height : size.width,
        height: portrait ? size.width : size.height,
        child: CameraPreview(camera),
      ),
    );
  }
}

class _NoCamera extends StatelessWidget {
  const _NoCamera({required this.error, required this.onRetry});

  final CameraException? error; // null while the camera starts
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final error = this.error;
    if (error == null) return const Center(child: CircularProgressIndicator(color: Colors.white));
    final denied = error.code == 'CameraAccessDenied';
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.no_photography_outlined, color: Colors.white, size: 40),
            const SizedBox(height: 12),
            Text(
              denied ? 'Camera access is off for Lakad.' : 'The camera did not start.',
              textAlign: TextAlign.center,
              style: const TextStyle(color: Colors.white, fontSize: 16),
            ),
            if (!denied && error.description != null)
              Text(
                error.description!,
                textAlign: TextAlign.center,
                style: const TextStyle(color: Colors.white70, fontSize: 12),
              ),
            const SizedBox(height: 16),
            FilledButton(
              // The app's settings page holds every permission, the camera's included.
              onPressed: denied ? Geolocator.openAppSettings : onRetry,
              child: Text(denied ? 'Open settings' : 'Try again'),
            ),
          ],
        ),
      ),
    );
  }
}

class _Reticle extends StatelessWidget {
  const _Reticle();

  @override
  Widget build(BuildContext context) {
    const side = BorderSide(color: Colors.white, width: 3);
    Widget corner(Alignment at, Border border) => Align(
      alignment: at,
      child: SizedBox.square(dimension: 30, child: DecoratedBox(decoration: BoxDecoration(border: border))),
    );
    return IgnorePointer(
      child: Center(
        child: SizedBox.square(
          dimension: 220,
          child: Stack(
            children: [
              corner(Alignment.topLeft, const Border(top: side, left: side)),
              corner(Alignment.topRight, const Border(top: side, right: side)),
              corner(Alignment.bottomLeft, const Border(bottom: side, left: side)),
              corner(Alignment.bottomRight, const Border(bottom: side, right: side)),
            ],
          ),
        ),
      ),
    );
  }
}

class _NearbyChip extends StatelessWidget {
  const _NearbyChip(this.report, this.distance);

  final Report report;
  final double distance;

  @override
  Widget build(BuildContext context) {
    return ChipCard(
      padding: const EdgeInsets.fromLTRB(10, 7, 12, 7),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          DecoratedBox(
            decoration: BoxDecoration(color: statusColors[report.status], shape: BoxShape.circle),
            child: const SizedBox.square(dimension: 8),
          ),
          const SizedBox(width: 7),
          Text(
            '${report.label} · ${distance.round()} m',
            style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
          ),
        ],
      ),
    );
  }
}
