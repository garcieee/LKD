// Lakad mobile entry. `flutter create` writes a counter demo here: keep this file (see SETUP.md).
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:mapbox_maps_flutter/mapbox_maps_flutter.dart' show MapboxOptions;

import 'config/env.dart';
import 'features/tickets/local_ticket_notifier.dart';
import 'features/tickets/ticket_notifier.dart';
import 'map/map_view.dart';
import 'theme.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  // Android 15 draws apps edge to edge once targetSdk is 35: transparent system bars, with dark
  // icons because the basemap is light. The map runs under them; the chips use SafeArea.
  SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
  SystemChrome.setSystemUIOverlayStyle(
    const SystemUiOverlayStyle(
      statusBarColor: Colors.transparent,
      statusBarIconBrightness: Brightness.dark,
      systemNavigationBarColor: Colors.transparent,
      systemNavigationBarIconBrightness: Brightness.dark,
      systemNavigationBarContrastEnforced: false, // no scrim behind 3-button navigation
    ),
  );
  // Before any MapWidget exists. A missing token shows a message on the map page instead.
  if (Env.mapboxToken.isNotEmpty) MapboxOptions.setAccessToken(Env.mapboxToken);
  runApp(LakadApp(notifier: LocalTicketNotifier()));
}

class LakadApp extends StatelessWidget {
  const LakadApp({super.key, this.notifier});

  final TicketNotifier? notifier; // how the map page tells the person the city changed a ticket

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Lakad',
      debugShowCheckedModeBanner: false,
      theme: origamiTheme(),
      home: MapView(notifier: notifier),
    );
  }
}
